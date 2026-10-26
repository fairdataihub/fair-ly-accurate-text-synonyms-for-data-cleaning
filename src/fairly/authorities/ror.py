"""ROR (Research Organization Registry) authority.

Builds a normalized ``name -> ROR id`` index from a ROR v2 data dump
(https://ror.org/data / Zenodo community ``ror-data``) and uses it to split
semantic clusters that span more than one real institution.

A normalized name that maps to >=2 different RORs is AMBIGUOUS and dropped from
the index, so it never triggers a false split. Each org also carries its ROR
display name and GeoNames location for downstream disambiguation.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import unicodedata
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import numpy as np

# Newest ROR v2 data dump on Zenodo (community ``ror-data``). ROR publishes a
# fresh dump ~monthly; sorting newest and taking the top record gives the latest.
LATEST_ROR_RECORDS_API = "https://zenodo.org/api/communities/ror-data/records?sort=newest&size=1"
DEFAULT_ROR_CACHE = ".ror_cache"


def norm(s: str) -> str:
    """NFKD -> ASCII -> lowercase -> keep [a-z0-9 ] -> collapse whitespace."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


class RorIndex:
    """A resolved ``name -> ROR id`` lookup plus display names, locations, and the
    place and generic words of the identity guard (:mod:`fairly.identity`). Pickles
    from before 0.5.0 load with both word sets empty."""

    def __init__(self, name2ror: Dict[str, str], display: Dict[str, str],
                 loc: Dict[str, Tuple[Optional[str], Optional[str]]],
                 place_words: Optional[FrozenSet[str]] = None,
                 generic_words: Optional[FrozenSet[str]] = None):
        self.name2ror = name2ror
        self.display = display
        self.loc = loc
        self.place_words = frozenset(place_words or ())
        self.generic_words = frozenset(generic_words or ())

    def resolve(self, name: str) -> Optional[str]:
        return self.name2ror.get(norm(name))

    def __len__(self) -> int:
        return len(self.name2ror)

    def save(self, path: str) -> None:
        with open(path, "wb") as fh:
            pickle.dump({"name2ror": self.name2ror, "display": self.display, "loc": self.loc,
                         "place_words": self.place_words, "generic_words": self.generic_words}, fh)

    @classmethod
    def load(cls, path: str) -> "RorIndex":
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        return cls(d["name2ror"], d["display"], d["loc"], d.get("place_words"),
                   d.get("generic_words"))

    @classmethod
    def from_latest(cls, cache_dir: str = DEFAULT_ROR_CACHE, force: bool = False) -> "RorIndex":
        """Download the newest ROR v2 dump from Zenodo and build an index from it."""
        return build_ror_index(fetch_latest_ror_dump(cache_dir=cache_dir, force=force))


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _http_get_json(url: str, timeout: int = 30) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "fair-ly-accurate/ror-fetch"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: str, timeout: int = 120) -> None:
    """Stream ``url`` to ``dest``. Uses ``requests`` (the ``[ror]`` extra) when
    available for retries/streaming, else falls back to the stdlib."""
    def _progress(done: int, total: int) -> None:
        if total:
            sys.stderr.write(f"\r  downloading {done / 1e6:6.1f} / {total / 1e6:.1f} MB")
            sys.stderr.flush()

    tmp = dest + ".part"
    try:
        import requests  # type: ignore
    except ImportError:
        requests = None
    if requests is not None:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    _progress(done, total)
    else:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "fair-ly-accurate/ror-fetch"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                _progress(done, total)
    _log("")
    os.replace(tmp, dest)


def _pick_zip_file(record: dict) -> Tuple[str, str]:
    """Return ``(filename, download_url)`` for the data-dump zip in a Zenodo record."""
    files = record.get("files") or []
    zips = [f for f in files if str(f.get("key", "")).endswith(".zip")]
    if not zips:
        raise RuntimeError("no .zip asset found on the latest ROR Zenodo record")
    f = zips[0]
    url = (f.get("links") or {}).get("self") or (f.get("links") or {}).get("download")
    if not url:
        raise RuntimeError(f"ROR zip {f.get('key')!r} has no download link")
    return f["key"], url


def _extract_v2_json(zip_path: str, out_dir: str) -> str:
    """Extract the ``*_schema_v2.json`` member from a ROR dump zip; return its path."""
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        v2 = [n for n in names if n.endswith("_schema_v2.json")]
        if not v2:
            v2 = [n for n in names if "schema_v2" in n and n.endswith(".json")]
        if not v2:
            v2 = [n for n in names if n.endswith(".json")]
        if not v2:
            raise RuntimeError(f"no JSON member found in {zip_path}")
        member = v2[0]
        out_path = os.path.join(out_dir, os.path.basename(member))
        with zf.open(member) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
    return out_path


def fetch_latest_ror_dump(cache_dir: str = DEFAULT_ROR_CACHE, url: str = LATEST_ROR_RECORDS_API,
                          force: bool = False) -> str:
    """Download the newest ROR v2 JSON dump from Zenodo and return its local path.

    The extracted JSON is cached in ``cache_dir`` (default ``.ror_cache/``); a
    subsequent call reuses it unless ``force`` is set. Uses ``requests`` when the
    ``[ror]`` extra is installed, otherwise the standard library.
    """
    os.makedirs(cache_dir, exist_ok=True)
    _log(f"resolving latest ROR dump: {url}")
    record = (_http_get_json(url).get("hits") or {}).get("hits") or []
    if not record:
        raise RuntimeError("Zenodo returned no ROR data records")
    zip_name, zip_url = _pick_zip_file(record[0])

    # Cache key: the extracted-JSON name derived from the zip's version stem.
    stem = zip_name[:-4] if zip_name.endswith(".zip") else zip_name
    cached = os.path.join(cache_dir, stem + "_schema_v2.json")
    if os.path.exists(cached) and not force:
        _log(f"using cached ROR dump: {cached}")
        return cached

    zip_path = os.path.join(cache_dir, zip_name)
    _log(f"fetching {zip_name}")
    _download(zip_url, zip_path)
    out_path = _extract_v2_json(zip_path, cache_dir)
    try:
        os.remove(zip_path)  # keep only the (smaller) extracted JSON
    except OSError:
        pass
    # Normalize to the deterministic cache-key name so future runs hit the cache.
    if os.path.abspath(out_path) != os.path.abspath(cached):
        os.replace(out_path, cached)
    _log(f"ROR dump ready: {cached}")
    return cached


#: Identity-word cutoffs, calibrated on ROR v2.15 (see docs/methods.md). A place
#: word must be in fewer than ``MAX_PLACE_FREQ`` organization names, and at least
#: ``MIN_PLACE_SHARE`` of the organizations named with it must be located in a place
#: of that name ("Antwerp" yes, "Harvard" and "National" no). A country word located
#: at least ``COUNTRY_PLACE_SHARE`` of the time has no frequency cap ("China",
#: "Japan", "United States"). A generic word is in at least ``GENERIC_SHARE`` of all
#: organization names ("University", "Hospital").
MAX_PLACE_FREQ = 500
MIN_PLACE_SHARE = 0.3
COUNTRY_PLACE_SHARE = 0.8
GENERIC_SHARE = 0.005


def identity_words_from_orgs(orgs: Iterable[dict], max_place_freq: int = MAX_PLACE_FREQ,
                             min_place_share: float = MIN_PLACE_SHARE,
                             country_place_share: float = COUNTRY_PLACE_SHARE,
                             generic_share: float = GENERIC_SHARE
                             ) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """``(place_words, generic_words)`` for the identity guard (:mod:`fairly.identity`)
    from parsed ROR v2 records.

    Place words are the words of each organization's city, region and country names
    that, where they appear in organization names, mostly name the organization's own
    location (at least ``min_place_share`` of those organizations are located there:
    "Antwerp" yes, "Harvard" and "National" no), and that are in fewer than
    ``max_place_freq`` organization names. A country word located at least
    ``country_place_share`` of the time has no frequency cap, since country suffixes
    are common in affiliations ("China", "Japan", "United States"; not "New" or
    "South"). Word counts skip text in parentheses ("Pfizer (United States)"). Generic
    words are words found in at least ``generic_share`` of all organization names; a
    generic word is never a place word, except such a country word.
    """
    from ..identity import LEGAL_SUFFIXES, STOPWORDS, ADDRESS_WORDS, tokens
    named: Dict[str, int] = {}
    located: Dict[str, int] = {}
    country, local = set(), set()
    n_orgs = 0
    for org in orgs:
        n_orgs += 1
        words = set()
        for n in org.get("names") or []:
            words.update(tokens(re.sub(r"\([^)]*\)", " ", str(n.get("value") or ""))))
        here = set()
        for lc in org.get("locations") or []:
            g = lc.get("geonames_details") or {}
            c = tokens(g.get("country_name"))
            r = tokens(g.get("name")) + tokens(g.get("country_subdivision_name"))
            country.update(c)
            local.update(r)
            here.update(c + r)
        for t in words:
            named[t] = named.get(t, 0) + 1
            if t in here:
                located[t] = located.get(t, 0) + 1
    def share(t):
        return located.get(t, 0) / named[t] if named.get(t) else 1.0

    countries = {t for t in country if share(t) >= country_place_share}
    place = countries | {t for t in country | local
                         if share(t) >= min_place_share and named.get(t, 0) < max_place_freq}
    skip = STOPWORDS | LEGAL_SUFFIXES | ADDRESS_WORDS
    generic = {t for t, k in named.items()
               if k >= generic_share * n_orgs and len(t) > 2 and not t.isdigit()
               and t not in skip and t not in countries}
    return frozenset(place - generic), frozenset(generic)


def identity_words_from_dump(dump_path: str, **kwargs) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """``(place_words, generic_words)`` straight from a ROR v2 JSON dump, for
    :func:`fairly.identity.changes_identity`. Keyword arguments go to
    :func:`identity_words_from_orgs`."""
    with open(dump_path, encoding="utf-8") as fh:
        return identity_words_from_orgs(json.load(fh), **kwargs)


def build_ror_index(dump_path: str, max_place_freq: int = MAX_PLACE_FREQ,
                    min_place_share: float = MIN_PLACE_SHARE,
                    country_place_share: float = COUNTRY_PLACE_SHARE,
                    generic_share: float = GENERIC_SHARE) -> RorIndex:
    """Build a :class:`RorIndex` from a ROR v2 JSON dump.

    Names shorter than 3 chars or with no letter are skipped; a name mapping to
    two different RORs is dropped as ambiguous. ``place_words`` and
    ``generic_words`` come from :func:`identity_words_from_orgs`.
    """
    with open(dump_path, encoding="utf-8") as fh:
        orgs = json.load(fh)
    name2ror: Dict[str, str] = {}
    ambiguous = set()
    display: Dict[str, str] = {}
    loc: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for org in orgs:
        rid = org["id"]
        disp = None
        for n in org.get("names") or []:
            if "ror_display" in (n.get("types") or []):
                disp = n.get("value")
        display[rid] = disp or ((org.get("names") or [{}])[0].get("value") or rid)
        locs = org.get("locations") or []
        if locs:
            g = locs[0].get("geonames_details") or {}
            loc[rid] = (g.get("country_code"), g.get("name") or g.get("country_name"))
        for n in org.get("names") or []:
            nn = norm(n.get("value"))
            if len(nn) < 3 or not re.search(r"[a-z]", nn):
                continue
            if nn in name2ror and name2ror[nn] != rid:
                ambiguous.add(nn)
            else:
                name2ror[nn] = rid
    for nn in ambiguous:
        name2ror.pop(nn, None)
    place_words, generic_words = identity_words_from_orgs(
        orgs, max_place_freq=max_place_freq, min_place_share=min_place_share,
        country_place_share=country_place_share, generic_share=generic_share)
    return RorIndex(name2ror, display, loc, place_words, generic_words)


class RorAuthority:
    """Splits a semantic cluster into per-ROR sub-clusters."""

    def __init__(self, index: RorIndex):
        self.index = index

    def split(self, idxs: Sequence[int], phrases: Sequence[str], emb: np.ndarray) -> List[List[int]]:
        idxs = list(idxs)
        rors = [self.index.resolve(phrases[i]) for i in idxs]
        if len({r for r in rors if r}) <= 1:
            return [idxs]
        groups: Dict[str, List[int]] = {}
        for k, i in enumerate(idxs):
            if rors[k]:
                groups.setdefault(rors[k], []).append(i)
        cents = {r: emb[g].mean(0) for r, g in groups.items()}
        for k, i in enumerate(idxs):
            if not rors[k]:
                best = min(cents, key=lambda rr: float(((emb[i] - cents[rr]) ** 2).sum()))
                groups[best].append(i)
        return list(groups.values())
