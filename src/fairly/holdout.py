"""Acronym / short-token holdout.

Short strings and acronyms carry too little signal for a sentence embedding to
place reliably, so they cluster with unrelated short forms and get assigned a
wrong representative (``ZHAW -> Z``, ``LUH -> HU``, ``GTC -> GT``). We therefore
hold them OUT of the clustering step: they are still embedded (so an embedding
cache stays valid) but are masked out of the clusterer and map to themselves.

This is the single most important guard against the short-acronym over-merge
failure mode when normalizing organization / entity names.
"""
from __future__ import annotations

from typing import Iterable, List

DEFAULT_MIN_LEN = 4


def is_holdout(term: str, min_len: int = DEFAULT_MIN_LEN) -> bool:
    """True if ``term`` must NOT be semantically clustered.

    A term is held out when it is shorter than ``min_len`` characters, or when it
    is an all-caps single token (an acronym such as ``ZHAW``, ``MIDAS``, ``UK``).
    Multi-word names, mixed-case names and long names are clusterable.
    """
    t = str(term).strip()
    if len(t) < min_len:
        return True
    if " " not in t and any(c.isalpha() for c in t) and t == t.upper():
        return True
    return False


def clusterable_indices(phrases: Iterable[str], min_len: int = DEFAULT_MIN_LEN) -> List[int]:
    """Indices of ``phrases`` that should go into the clusterer (non-held-out)."""
    return [i for i, p in enumerate(phrases) if not is_holdout(p, min_len)]
