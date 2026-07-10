"""The variant -> canonical map produced by a Normalizer."""
from __future__ import annotations

import json
import pickle
from typing import Dict, List, Optional


class SynonymMap:
    """A resolved ``variant -> canonical`` mapping for one field.

    Only real remaps are stored (a term that is its own canonical is absent), so
    ``apply`` is a cheap dict lookup that leaves unknown / already-canonical values
    untouched.
    """

    def __init__(self, mapping: Dict[str, str], clusters: Optional[Dict[str, List[str]]] = None,
                 field: Optional[str] = None, meta: Optional[dict] = None):
        self.mapping = dict(mapping)
        self.clusters = clusters or {}
        self.field = field
        self.meta = meta or {}

    def apply(self, value):
        """Return the canonical for ``value`` (unchanged if not remapped)."""
        if isinstance(value, str):
            return self.mapping.get(value.strip(), value)
        return value

    def __len__(self) -> int:
        return len(self.mapping)

    def __contains__(self, value) -> bool:
        return isinstance(value, str) and value.strip() in self.mapping

    # --- persistence --------------------------------------------------------
    def save(self, path: str) -> None:
        with open(path, "wb") as fh:
            pickle.dump({"mapping": self.mapping, "clusters": self.clusters,
                         "field": self.field, "meta": self.meta}, fh)

    @classmethod
    def load(cls, path: str) -> "SynonymMap":
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        return cls(d["mapping"], d.get("clusters"), d.get("field"), d.get("meta"))

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.mapping, fh, ensure_ascii=False, indent=2)

    def write_review(self, path: str, counts: Optional[Dict[str, int]] = None) -> None:
        """Write a human-review TSV: ``canonical<TAB>freq<TAB>merged_variants``.

        This is the review gate: eyeball it before applying, especially for
        homogeneous fields (funders) where over-merge is easy.
        """
        counts = counts or {}

        def freq(t):
            return counts.get(t, 0)

        rows = sorted(self.clusters.items(),
                      key=lambda kv: -sum(freq(m) for m in kv[1]))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("canonical\tfreq\tmerged_variants\n")
            for canon, members in rows:
                variants = " | ".join(f"{m}({freq(m)})" for m in members if m != canon)
                fh.write(f"{canon}\t{freq(canon)}\t{variants}\n")
