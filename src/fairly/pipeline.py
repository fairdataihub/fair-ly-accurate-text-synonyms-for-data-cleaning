"""The Normalizer: turn a field's raw value counts into a SynonymMap, and apply it."""
from __future__ import annotations

from collections import Counter
from typing import Dict, Optional

from .cluster import synonym_lustre
from .config import FieldConfig
from .synonyms import SynonymMap


class Normalizer:
    """Builds and applies a :class:`SynonymMap` for one field, per a :class:`FieldConfig`.

    Usage::

        norm = Normalizer(get_preset("affiliation"), cache_dir=".cache")
        smap = norm.build(counts, authority=ror_index)   # RorIndex or None
        value = norm.normalize("Univ. of California, Berkeley", smap)
    """

    def __init__(self, config: FieldConfig, cache_dir: Optional[str] = None):
        self.cfg = config
        self.cache_dir = cache_dir

    # --- cleaning -----------------------------------------------------------
    def clean_counts(self, raw_counts: Dict[str, int]) -> Counter:
        """Apply the field cleaner to each distinct term, aggregating counts under
        the cleaned surface form and dropping junk terms entirely."""
        cleaner = self.cfg.cleaner
        if cleaner is None:
            return Counter(raw_counts)
        out: Counter = Counter()
        for term, n in raw_counts.items():
            c = cleaner.clean(term)
            if c:
                out[c] += n
        return out

    def _authority(self, authority):
        if self.cfg.authority == "ror" and authority is not None:
            from .authorities.ror import RorAuthority, RorIndex
            if isinstance(authority, RorIndex):
                return RorAuthority(authority)
            return authority  # already an Authority-like object
        return None

    def _identity_guard(self, authority, place_words):
        if not self.cfg.identity_guard:
            return None
        from .identity import identity_guard
        if place_words is None:
            index = getattr(authority, "index", authority)   # RorAuthority or RorIndex
            place_words = getattr(index, "place_words", None) or ()
        return identity_guard(place_words)

    # --- build --------------------------------------------------------------
    def build(self, raw_counts: Dict[str, int], *, authority=None, resolve=None, emb=None,
              place_words=None) -> SynonymMap:
        """Build the SynonymMap. ``authority`` is a RorIndex (for ror fields);
        ``resolve`` is a place resolver (for geocode fields); ``emb`` optionally
        supplies precomputed embeddings aligned to the cleaned term list.
        ``place_words`` overrides the place words the identity guard ignores (by
        default the RorIndex's ``place_words``)."""
        counts = self.clean_counts(raw_counts)

        if self.cfg.strategy == "controlled":
            smap = self.cfg.vocab.synonym_map(counts)
            smap.field = self.cfg.name
            return smap

        if self.cfg.strategy == "geocode":
            if resolve is None:
                raise ValueError("geocode strategy requires a `resolve` function")
            from .authorities.geocode import geocode_synonyms
            return geocode_synonyms(counts, resolve, field=self.cfg.name)

        if emb is None:
            from .embeddings import embed
            emb = embed(list(counts.keys()), self.cfg.embedding_model, self.cache_dir)
        return synonym_lustre(
            counts, emb, self.cfg.eps,
            min_cluster_size=self.cfg.min_cluster_size,
            min_samples=self.cfg.min_samples,
            method=self.cfg.cluster_method,
            holdout=self.cfg.holdout,
            authority=self._authority(authority),
            identity_guard=self._identity_guard(authority, place_words),
            field=self.cfg.name,
        )

    # --- apply --------------------------------------------------------------
    def normalize(self, raw_value, smap: SynonymMap):
        """Clean ``raw_value`` then map it to its canonical. If the cleaner drops
        the value, return the field ``fallback`` (or None)."""
        if self.cfg.cleaner is not None and isinstance(raw_value, str):
            cleaned = self.cfg.cleaner.clean(raw_value)
            if cleaned is None:
                return self.cfg.fallback
            return smap.apply(cleaned)
        return smap.apply(raw_value)
