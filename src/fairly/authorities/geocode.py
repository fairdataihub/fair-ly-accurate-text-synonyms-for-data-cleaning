"""Geocoding-based normalization for place fields.

Location fields (DataCite ``geoLocationPlace``, conference locations) must NOT be
clustered by embedding: "Graz, Austria" and "Vienna, Austria" embed as near
neighbours ("city in Austria") and would merge. Instead we geocode each distinct
string and group by the resolved ``(country, city)``, canonicalizing to
``"City, Country"``. This unifies spelling/format variants of one place while
keeping genuinely different places apart -- the place analogue of the ROR split.

Geocoding uses geopy's Nominatim (optional ``geo`` extra) with a caching, rate-
limited resolver; you can inject any ``resolve(str) -> dict|None`` function.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Callable, Dict, Optional

from ..synonyms import SynonymMap


def _norm_q(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s))).strip()


def nominatim_resolver(user_agent: str = "fairly-synonyms/0.1",
                       min_delay_seconds: float = 1.1,
                       cache_path: Optional[str] = None) -> Callable[[str], Optional[dict]]:
    """A cached, rate-limited Nominatim resolver. Requires the ``geo`` extra.

    Returns a function ``resolve(place) -> {country, cc, city} | None``. Results
    are cached in-memory and, if ``cache_path`` is given, persisted to JSON so
    re-runs are cheap and stay within Nominatim's 1 req/sec usage policy.
    """
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError("Geocoding needs the 'geo' extra: pip install fairly-synonyms[geo]") from exc

    cache: Dict[str, Optional[dict]] = {}
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    geo = Nominatim(user_agent=user_agent, timeout=10)
    query = RateLimiter(geo.geocode, min_delay_seconds=min_delay_seconds, swallow_exceptions=True)

    def resolve(place: str) -> Optional[dict]:
        key = _norm_q(place)
        if key in cache:
            return cache[key]
        r = query(key, addressdetails=True, language="en")
        out = None
        if r and getattr(r, "raw", None):
            a = r.raw.get("address", {})
            city = (a.get("city") or a.get("town") or a.get("village")
                    or a.get("municipality") or a.get("state") or a.get("county"))
            out = {"country": a.get("country"), "cc": a.get("country_code"), "city": city}
        cache[key] = out
        if cache_path:
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False)
        return out

    return resolve


def geocode_synonyms(counts: Dict[str, int], resolve: Callable[[str], Optional[dict]],
                     field: Optional[str] = None) -> SynonymMap:
    """Build a :class:`SynonymMap` grouping place strings by resolved (country, city).

    Canonical form is ``"City, Country"``. Strings that do not resolve to both a
    city and a country are left unmapped (kept as-is).
    """
    groups: Dict[tuple, dict] = {}
    for term in counts:
        g = resolve(term)
        if not g or not g.get("city") or not g.get("country"):
            continue
        key = (g.get("cc"), g["city"].lower())
        grp = groups.setdefault(key, {"canon": f"{g['city']}, {g['country']}", "members": []})
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
