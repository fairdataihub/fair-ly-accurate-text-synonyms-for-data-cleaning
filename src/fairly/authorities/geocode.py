"""Geocoding-based normalization for place fields.

Location fields (DataCite ``geoLocationPlace``, conference locations) must NOT be
clustered by embedding: "Graz, Austria" and "Vienna, Austria" embed as near
neighbours ("city in Austria") and would merge. Instead we geocode each distinct
string and group by the resolved place, canonicalizing to ``"City, Country"``. This
unifies spelling/format variants of one place while keeping genuinely different places
apart -- the place analogue of the ROR split.

A geocoder returns its best guess for any text, so a result is used only when it
verifiably names the text's place (:func:`verify_place`):

* it is a place (a settlement or an administrative area), not a street, building or
  venue: "Conference Location" is a social centre in Russia, "Ithaca, NY, U.S.A." a road
  in Sydney;
* one of its names appears in the text as whole words: its own, alternative, official or
  English name, or, when the text also names the country, a name in any language ("Wien"
  names Vienna; "CERN" does not name Chern, whose Italian name "Čern'" folds to "cern");
* a country or US state the text names agrees with it: "Venice (Italy)" never becomes a
  place in Austria.

The canonical is the matched place's own English name and country ("Milano" -> "Milan,
Italy"), never a containing region ("Pisa" -> "Tuscany"); an area above a settlement keeps
the name the text used ("Padova" -> "Padova, Italy", not "Province of Padua"). Names match
without administrative wrappers ("City of Rochester", "Arlington County") and in German
transliteration ("Goettingen"). A village, suburb or other small place counts only when the
text also names its country or state ("Mars" alone is not a French village). A purely
virtual location ("Online", "Virtual") is never geocoded. A text that names no country
stays as written when another country has a place of that name ranked nearly as high
("Cambridge", "Valencia"). Anything that fails stays as written.

Geocoding uses geopy's Nominatim (optional ``geo`` extra) with a caching, rate-
limited resolver; you can inject any ``resolve(str) -> dict|None`` function.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

from ..synonyms import SynonymMap
from ._places import COUNTRIES, US_STATE_CODES, US_STATES

#: Nominatim classes that are places; everything else (highway, amenity, building,
#: tourism, ...) is a feature that merely carries the name.
PLACE_CLASSES = frozenset({"place", "boundary"})

#: Name keys of a Nominatim ``namedetails`` record that name the place itself.
_NAME_KEYS = ("name", "alt_name", "old_name", "official_name", "short_name", "int_name",
              "loc_name", "nat_name", "reg_name")

# A PURELY virtual location (no physical city) must not be geocoded to a real place:
# Nominatim fuzzy-matches "Online" -> Montpellier, "Virtual" -> Moscow. A string that
# also names a city ("Berlin / online") is not matched.
_VIRTUAL_RE = re.compile(
    r"^\W*(fully\s+|completely\s+)?(online|virtual|virtually|remote|hybrid|on[\s-]?line|web(inar|"
    r"[\s-]?based)?|zoom|digital|distance|tele[\s-]?conference|e[\s-]?conference)"
    r"([\s,./-]*(only|event|conference|conferences|meeting|format|mode|edition))*\W*$",
    re.I)
_CODE_RE = re.compile(r"(?:^|,)\s*([A-Z]{2})\s*(?=,|$)")


def _norm_q(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s))).strip()


def _fold(s) -> str:
    """Lower-case ASCII words, single-spaced, padded with spaces for whole-word search."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " " + " ".join(re.findall(r"[a-z0-9]+", s)) + " "


def is_virtual(text: str) -> bool:
    """A purely virtual location ("Online", "Virtual conference", "Zoom")."""
    return bool(_VIRTUAL_RE.match(str(text or "").strip()))


# A name that is both a country and a US state ("Georgia") allows either.
_COUNTRY_SETS: List[Tuple[str, FrozenSet[str]]] = sorted(
    [(" " + n + " ", frozenset({cc})) for n, cc in COUNTRIES.items() if n not in US_STATES]
    + [(" " + s + " ", frozenset({"us"}) | (frozenset({COUNTRIES[s]}) if s in COUNTRIES else frozenset()))
       for s in US_STATES],
    key=lambda x: (-len(x[0]), x[0]))


def named_countries(text: str) -> List[FrozenSet[str]]:
    """For each country or US state the text names, the country codes it allows
    ("Georgia" allows ``{"us", "ge"}``). Longer names win ("New Mexico" is a US state,
    not Mexico); a two-letter US state code counts only as a comma-separated part
    ("Ithaca, NY")."""
    f = _fold(text)
    out = []
    for name, ccs in _COUNTRY_SETS:
        if name in f:
            out.append(ccs)
            f = f.replace(name, " ")
    if any(c in US_STATE_CODES for c in _CODE_RE.findall(str(text or ""))):
        out.append(frozenset({"us"}))
    return out


#: Administrative wrappers around a place's name ("City of Rochester", "Arlington County",
#: "Provincia di Pisa"): the bare name also names the place.
_ADMIN_PREFIX_RE = re.compile(
    r"^(city|town|village|county|province|municipality|borough|district|region|department) of\s+"
    r"|^(comune|provincia|citta metropolitana) di\s+|^(landkreis|kreis|stadt|gemeinde)\s+", re.I)
_ADMIN_SUFFIX_RE = re.compile(
    r"\s+(county|province|municipality|district|region|prefecture|oblast|governorate|parish)$", re.I)
_DE_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})

#: Nominatim types of an area above a settlement: its own name is used for the canonical
#: as the text wrote it ("Padova", not "Province of Padua").
AREA_TYPES = frozenset({"county", "state", "province", "region", "state_district", "district",
                        "department", "municipality_district"})
#: Small places: used only when the text also names the country (or US state), since a
#: bare word matches some village somewhere ("Mars").
SMALL_TYPES = frozenset({"village", "hamlet", "suburb", "neighbourhood", "quarter", "isolated_dwelling",
                         "locality", "farm", "city_block", "residential", "square", "croft",
                         "allotments", "borough"})


def _bare(name: str) -> str:
    return _ADMIN_SUFFIX_RE.sub("", _ADMIN_PREFIX_RE.sub("", str(name).strip())).strip()


def _names(raw: dict, languages: bool = True) -> List[str]:
    """The place's names: its own, alternative and English names, and with `languages`
    every other language's; plus their bare forms without an administrative wrapper and
    German transliterations ("Goettingen")."""
    nd = raw.get("namedetails") or {}
    out = [raw.get("name")]
    for k, v in nd.items():
        if k in _NAME_KEYS or k == "name:en" or (languages and k.startswith("name:")):
            out.extend(str(v).split(";"))
    out = [str(n).strip() for n in out if n and str(n).strip()]
    more = [_bare(n) for n in out] + [n.translate(_DE_TRANSLIT) for n in out]
    return list(dict.fromkeys(n for n in out + more if n))


#: A text that names no country is ambiguous when another country has a place it names
#: with an importance at least this close to the best answer's ("Cambridge": England or
#: Massachusetts; "Valencia": Spain or Venezuela).
AMBIGUITY_MARGIN = 0.15


def _importance(raw: dict) -> float:
    try:
        return float(raw.get("importance") or 0)
    except (TypeError, ValueError):
        return 0.0


def verify_place(text: str, raw: Optional[dict], others: Sequence[dict] = ()) -> Optional[dict]:
    """``{"name", "country", "cc", "canonical"}`` when the Nominatim result ``raw``
    (``addressdetails`` and ``namedetails`` on) verifiably names the place of
    ``text``, else None. ``others`` are the geocoder's next answers for the same text
    (``exactly_one=False``); when the text names no country, a place in another country
    that the text also names, ranked within :data:`AMBIGUITY_MARGIN`, makes it ambiguous.
    See the module docstring for the rules."""
    v = _verify_one(text, raw)
    if v is None or named_countries(text):
        return v
    top = _importance(raw)
    for o in others or ():
        w = _verify_one(text, o)
        if w and w["cc"] != v["cc"] and _importance(o) >= top - AMBIGUITY_MARGIN:
            return None
    return v


def _verify_one(text: str, raw: Optional[dict]) -> Optional[dict]:
    if not raw or is_virtual(text):
        return None
    if str(raw.get("class") or raw.get("category") or "") not in PLACE_CLASSES:
        return None
    addr = raw.get("address") or {}
    cc = str(addr.get("country_code") or "").lower()
    country = addr.get("country")
    if not cc or not country:
        return None
    f = _fold(text)
    named = named_countries(text)
    # with no country named, a foreign-language name is too weak a match: Chern's Italian
    # name "Čern'" folds to "cern"
    matched = [n for n in _names(raw, languages=bool(named)) if _fold(n).strip() and _fold(n) in f]
    if not matched:
        return None
    if any(cc not in allowed for allowed in named):
        return None
    kind = str(raw.get("addresstype") or raw.get("type") or "")
    if kind in SMALL_TYPES and not named:
        return None
    nd = raw.get("namedetails") or {}
    if kind in AREA_TYPES:
        name = _bare(max(matched, key=len))          # the area's name as the text wrote it
    else:
        name = _bare(nd.get("name:en") or raw.get("name") or nd.get("name") or "")
    if not name:
        return None
    is_country = kind == "country" or _fold(name) == _fold(country)
    return {"name": name, "country": country, "cc": cc,
            "canonical": country if is_country else f"{name}, {country}"}


def nominatim_resolver(user_agent: str = "fair-ly-accurate",
                       min_delay_seconds: float = 1.1,
                       cache_path: Optional[str] = None) -> Callable[[str], Optional[dict]]:
    """A cached, rate-limited Nominatim resolver. Requires the ``geo`` extra.

    Returns a function ``resolve(place) -> {country, cc, city} | None``, where ``city``
    is the verified place name (:func:`verify_place`); an unverified result is None.
    The raw Nominatim answers are cached in-memory and, if ``cache_path`` is given,
    persisted to JSON so re-runs are cheap and stay within Nominatim's 1 req/sec usage
    policy. Cache entries from before 0.5.0 (no raw answer) are asked again.
    """
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError("Geocoding needs the 'geo' extra: pip install fair-ly-accurate[geo]") from exc

    cache: Dict[str, Optional[dict]] = {}
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            cache = {k: v for k, v in json.load(fh).items() if v is None or "raw" in v}
    geo = Nominatim(user_agent=user_agent, timeout=10)
    query = RateLimiter(geo.geocode, min_delay_seconds=min_delay_seconds, swallow_exceptions=True)

    def resolve(place: str) -> Optional[dict]:
        key = _norm_q(place)
        if is_virtual(key):
            return None
        if key not in cache:
            # a text that names no country: ask for the next answers too (ambiguity check)
            many = not named_countries(key)
            r = query(key, addressdetails=True, namedetails=True, language="en",
                      exactly_one=not many, **({"limit": 5} if many else {}))
            rs = [x for x in (r if many else [r]) or [] if x is not None and getattr(x, "raw", None)]
            cache[key] = {"raw": rs[0].raw, "others": [x.raw for x in rs[1:]]} if rs else None
            if cache_path:
                with open(cache_path, "w", encoding="utf-8") as fh:
                    json.dump(cache, fh, ensure_ascii=False)
        e = cache[key] or {}
        v = verify_place(key, e.get("raw"), e.get("others") or ())
        return {"country": v["country"], "cc": v["cc"], "city": v["name"],
                "canonical": v["canonical"]} if v else None

    return resolve


def geocode_synonyms(counts: Dict[str, int], resolve: Callable[[str], Optional[dict]],
                     field: Optional[str] = None) -> SynonymMap:
    """Build a :class:`SynonymMap` grouping place strings by resolved (country, city).

    Canonical form is ``"City, Country"`` (or the resolver's ``canonical``). Strings
    that do not resolve to both a city and a country, and purely virtual locations, are
    left unmapped (kept as-is).
    """
    groups: Dict[tuple, dict] = {}
    for term in counts:
        if is_virtual(term):
            continue
        g = resolve(term)
        if not g or not g.get("city") or not g.get("country"):
            continue
        key = (g.get("cc"), g["city"].lower())
        canon = g.get("canonical") or f"{g['city']}, {g['country']}"
        grp = groups.setdefault(key, {"canon": canon, "members": []})
        grp["members"].append(term)

    mapping: Dict[str, str] = {}
    clusters: Dict[str, list] = {}
    for grp in groups.values():
        canon, members = grp["canon"], grp["members"]
        for m in members:
            if m != canon:
                mapping[m] = canon
        if len(members) > 1 or (members and members[0] != canon):
            clusters[canon] = sorted(members, key=lambda m: -counts.get(m, 0))
    return SynonymMap(mapping, clusters, field=field,
                      meta={"strategy": "geocode", "n_places": len(groups)})
