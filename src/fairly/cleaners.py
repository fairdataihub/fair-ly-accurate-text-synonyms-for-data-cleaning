"""Deterministic pre-clustering cleaners.

These run BEFORE any embedding: they normalize surface form and drop values that
are not real entities at all (placeholders, hedge phrases, citations, bare
generics, URLs, single characters). A cleaner returns a cleaned string, or
``None`` to signal "this is junk, drop it" (callers typically replace a dropped
value with a field-level fallback such as the source repository).

Compose them with :class:`Cleaner`, or use the field presets in
:mod:`fairly.presets`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Optional

# --- primitive predicates ---------------------------------------------------

_URL_RE = re.compile(r"https?://|www\.", re.I)
_CITATION_RE = re.compile(r"\bet\s+al\b", re.I)
_PREAMBLE_RE = re.compile(
    r"^(the\s+)?(publisher|publishing organization|organization|organisation|"
    r"institution|host|hosting institution|host organization|affiliation|name)\s*"
    r"(is|was|:|=|-)\s*",
    re.I,
)
_HEDGE_RE = re.compile(
    r"(not specified|not provided|not mentioned|not clearly|not clear|not available|"
    r"not found|not indicated|not stated|not listed|cannot be|could not be|can't be|"
    r"unable to|no publisher|no explicit|no clear|based on the|appears to be|"
    r"the poster\b|this poster\b|the authors\b|the text\b|the document\b|the image\b|"
    r"the abstract\b|i cannot|i could not|unclear|unknown|would need|is not )",
    re.I,
)
_PLACEHOLDER = frozenset({
    "n/a", "na", "none", "null", "unknown", "not available", "not provided",
    "not specified", "tbd", "todo", "xxx", "test", "sample", "example",
    "location", "venue", "city, country", "institution name", "organization name",
    "publisher", "affiliation", "name", "value", "string",
})
_GENERIC = frozenset({
    "a university", "the university", "university", "a research institution",
    "research institution", "research institute", "institute", "research center",
    "research centre", "the institute", "conference", "poster", "academic institution",
    "the organization", "the organisation", "organization", "organisation", "company",
    "a company", "the company", "a research center", "various", "multiple", "n a",
    "the publisher", "publisher", "author", "the author", "the authors",
})


def has_letter(s: str) -> bool:
    return any(ch.isalpha() for ch in str(s))


def is_placeholder(s: str) -> bool:
    key = re.sub(r"\s+", " ", str(s).lower()).strip(" .")
    return key in _PLACEHOLDER


def _unwrap(s: str) -> str:
    """Strip surrounding quotes/asterisks/backticks only when BALANCED, so an
    internal-quote name like ``University of Campania "Luigi Vanvitelli"`` is kept."""
    s = s.strip()
    prev = None
    while prev != s:
        prev = s
        for q in ('"', "'", "`", "*"):
            if len(s) >= 2 and s[0] == q and s[-1] == q:
                s = s[1:-1].strip()
    return s


# --- cleaner steps ----------------------------------------------------------
# Each step takes a string and returns a string (transform) or None (drop).

def normalize_space(s: str) -> Optional[str]:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def unwrap(s: str) -> Optional[str]:
    return _unwrap(s)


def strip_preamble(s: str) -> Optional[str]:
    return _unwrap(_PREAMBLE_RE.sub("", s))


def require_letter(s: str) -> Optional[str]:
    return s if has_letter(s) else None


def require_min_len(min_len: int = 3) -> Callable[[str], Optional[str]]:
    def step(s: str) -> Optional[str]:
        return s if len(s.strip()) >= min_len else None
    return step


def drop_url(s: str) -> Optional[str]:
    return None if _URL_RE.search(s) else s


def drop_placeholder(s: str) -> Optional[str]:
    return None if is_placeholder(s) else s


def drop_generic(s: str) -> Optional[str]:
    key = re.sub(r"\s+", " ", s.lower()).strip(" .")
    return None if key in _GENERIC else s


def drop_hedge(s: str) -> Optional[str]:
    return None if _HEDGE_RE.search(s) else s


def drop_citation(s: str) -> Optional[str]:
    return None if _CITATION_RE.search(s) else s


def max_words(limit: int = 15) -> Callable[[str], Optional[str]]:
    """Drop values longer than ``limit`` words (a sentence / multi-entity list,
    not a single name). Skip this for fields with legitimately long names."""
    def step(s: str) -> Optional[str]:
        return None if len(s.split()) > limit else s
    return step


class Cleaner:
    """An ordered pipeline of cleaner steps.

    ``clean(value)`` runs each step in turn; the first step that returns ``None``
    drops the value (``clean`` returns ``None``). Otherwise the transformed string
    is returned.
    """

    def __init__(self, steps: List[Callable[[str], Optional[str]]]):
        self.steps = steps

    def clean(self, value) -> Optional[str]:
        if not isinstance(value, str):
            return None
        s = value
        for step in self.steps:
            s = step(s)
            if s is None or s == "":
                return None
        return s

    __call__ = clean
