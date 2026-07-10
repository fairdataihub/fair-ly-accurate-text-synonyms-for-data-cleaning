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
import pickle
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def norm(s: str) -> str:
    """NFKD -> ASCII -> lowercase -> keep [a-z0-9 ] -> collapse whitespace."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


class RorIndex:
    """A resolved ``name -> ROR id`` lookup plus display names and locations."""

    def __init__(self, name2ror: Dict[str, str], display: Dict[str, str],
                 loc: Dict[str, Tuple[Optional[str], Optional[str]]]):
        self.name2ror = name2ror
        self.display = display
        self.loc = loc

    def resolve(self, name: str) -> Optional[str]:
        return self.name2ror.get(norm(name))

    def __len__(self) -> int:
        return len(self.name2ror)

    def save(self, path: str) -> None:
        with open(path, "wb") as fh:
            pickle.dump({"name2ror": self.name2ror, "display": self.display, "loc": self.loc}, fh)

    @classmethod
    def load(cls, path: str) -> "RorIndex":
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        return cls(d["name2ror"], d["display"], d["loc"])


def build_ror_index(dump_path: str) -> RorIndex:
    """Build a :class:`RorIndex` from a ROR v2 JSON dump.

    Names shorter than 3 chars or with no letter are skipped; a name mapping to
    two different RORs is dropped as ambiguous.
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
    return RorIndex(name2ror, display, loc)


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
