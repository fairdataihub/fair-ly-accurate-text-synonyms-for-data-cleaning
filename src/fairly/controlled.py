"""Controlled-vocabulary normalization.

Some fields are NOT free text with fuzzy synonyms -- they are a *controlled
vocabulary* with a fixed set of canonical ids and many surface spellings: license
ids (SPDX / Creative Commons), country codes, units, funder ids, resource types.
For these, embedding clustering is the wrong tool: two canonical ids can be nearly
identical strings but semantically opposite (``CC-BY-SA-4.0`` vs ``CC-BY-NC-4.0``),
so an embedding merges them. The V-measure sweep in ``docs/methods.md`` shows this
directly -- ``rights`` scores far lower under clustering than the entity fields.

The right tool is deterministic: fold each surface string to a key (strip case,
whitespace, punctuation, diacritics) and resolve it to a canonical id via the
folded canonical set plus an explicit alias map. This never merges two different
canonical ids, and resolves arbitrarily messy spellings (``CC BY 4.0``,
``cc-by-4.0``, ``CC_BY_4.0``) to one canonical.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional

# strip a trailing region/port code after a version number (cc-by-3.0-us -> cc-by-3.0)
_REGION_RE = re.compile(r"(\d)(us|uk|scotland|de|es|fr|it|nl|jp|au|ca|pt|br|igo|int|nz|za)$")


def fold_key(s: str) -> str:
    """Fold a string to a comparison key: strip diacritics, lowercase, and drop every
    non-alphanumeric character. ``CC BY 4.0`` / ``cc-by-4.0`` / ``CC_BY_4.0`` -> ``ccby40``.
    Unicode letters are kept (so non-Latin canonical ids survive)."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c.lower() for c in s if c.isalnum())


class ControlledVocabulary:
    """Resolve surface strings to canonical ids in a fixed vocabulary.

    Parameters
    ----------
    canonicals : the canonical ids (their own folded key maps to themselves).
    aliases    : ``{alias_string: canonical_id}`` for vernacular / version-less /
                 alternate forms not reachable by folding a canonical (e.g. ``cc0`` ->
                 ``CC0-1.0``, ``cc-by`` -> ``CC-BY-4.0``).
    region_strip : also try the key with a trailing region/port code removed.
    """

    def __init__(self, canonicals: Iterable[str], aliases: Optional[Dict[str, str]] = None,
                 region_strip: bool = True):
        self.canonicals: List[str] = list(canonicals)
        self._by_key = {fold_key(c): c for c in self.canonicals}
        self._aliases = {fold_key(a): canon for a, canon in (aliases or {}).items()}
        self.region_strip = region_strip

    def normalize(self, value) -> Optional[str]:
        """Return the canonical id for ``value``, or None if it is not in the vocabulary."""
        if not isinstance(value, str) or not value.strip():
            return None
        k = fold_key(value)
        keys = [k]
        if self.region_strip:
            rk = _REGION_RE.sub(r"\1", k)
            if rk != k:
                keys.append(rk)
        for key in keys:
            if key in self._by_key:
                return self._by_key[key]
            if key in self._aliases:
                return self._aliases[key]
        return None

    def __contains__(self, value) -> bool:
        return self.normalize(value) is not None

    def synonym_map(self, counts):
        """Build a :class:`fairly.synonyms.SynonymMap` mapping every surface variant in
        ``counts`` to its canonical id (deterministic; no embeddings)."""
        from .synonyms import SynonymMap
        mapping, clusters = {}, {}
        for term in counts:
            canon = self.normalize(term)
            if canon and canon != term:
                mapping[term] = canon
                clusters.setdefault(canon, []).append(term)
        for canon, members in clusters.items():
            clusters[canon] = sorted(set(members + [canon]), key=lambda m: -counts.get(m, 0))
        return SynonymMap(mapping, clusters, meta={"strategy": "controlled",
                                                   "n_canonical": len(self.canonicals)})
