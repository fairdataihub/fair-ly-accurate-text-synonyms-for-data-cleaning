"""Per-field normalization configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .embeddings import DEFAULT_MODEL


@dataclass
class FieldConfig:
    """How to normalize one metadata field.

    strategy   "semantic" (embed + HDBSCAN synonym-lustre), "geocode" (place lookup +
               group by City, Country), or "controlled" (fold to a fixed vocabulary of
               canonical ids -- for license/rights, country codes, resource types).
    eps        HDBSCAN ``cluster_selection_epsilon`` (semantic only). Larger =
               more aggressive merging. Tune with :mod:`fairly.validate`.
    holdout    hold acronyms / short tokens out of clustering (semantic only).
    authority  ``None`` or ``"ror"`` -- split clusters spanning >=2 RORs.
    cleaner    a :class:`fairly.cleaners.Cleaner` run before clustering; values it
               drops are replaced with ``fallback`` (or removed if ``fallback`` is None).
    """

    name: str
    strategy: str = "semantic"
    eps: float = 0.15
    holdout: bool = True
    authority: Optional[str] = None
    min_cluster_size: int = 2
    min_samples: int = 1
    cluster_method: str = "leaf"
    embedding_model: str = DEFAULT_MODEL
    cleaner: object = None  # fairly.cleaners.Cleaner | None
    fallback: Optional[str] = None
    vocab: object = None  # fairly.controlled.ControlledVocabulary | None (strategy="controlled")
    description: str = ""

    def __post_init__(self):
        if self.strategy not in ("semantic", "geocode", "controlled"):
            raise ValueError(f"unknown strategy {self.strategy!r}")
        if self.authority not in (None, "ror"):
            raise ValueError(f"unknown authority {self.authority!r}")
        if self.strategy == "controlled" and self.vocab is None:
            raise ValueError("strategy 'controlled' requires a `vocab` (ControlledVocabulary)")
