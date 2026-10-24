"""Identity guard: does a remap still name the same entity?

Choosing a cluster's most frequent variant as its canonical has a failure mode the
holdout and the authority split do not cover: a short, generic name that is common in
the corpus absorbs longer, specific ones. In a poster corpus "Library & Researcher
Information Services" (a department of UL Research Institutes) became "Library",
"The Hockaday School" became "The Hotchkiss School", and "Wroclaw University" became
"Wroclaw University of Economics and Business".

A remap changes identity when the canonical drops a word of the variant, or adds one,
that tells which entity is meant. Words that never identify an organization do not
count: stopwords, legal suffixes, address words, numbers, single letters, acronyms in
parentheses, and place names (cities, regions, countries; see
:attr:`fairly.authorities.ror.RorIndex.place_words`). A plural ending is folded, an
abbreviation matches the word it starts ("Univ." -> "University", plus a few
contractions such as "Dept."), and reordering is free ("University of Heidelberg" ->
"Heidelberg University" is fine).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, FrozenSet, Iterable, Set

#: Words a remap may drop or add without changing which organization is meant.
STOPWORDS: FrozenSet[str] = frozenset({
    "the", "of", "and", "for", "in", "at", "on", "a", "an", "to", "y", "e", "et", "und",
    "de", "del", "della", "di", "du", "des", "der", "den", "la", "le", "les", "da", "do",
    "dos", "das", "van", "von", "inc", "ltd", "llc", "gmbh", "co", "corp",
})

#: Address words: an affiliation may lose its street address and stay the same place.
ADDRESS_WORDS: FrozenSet[str] = frozenset({
    "street", "st", "str", "strasse", "avenue", "ave", "road", "rd", "drive", "dr", "blvd",
    "boulevard", "lane", "way", "box", "po", "suite", "floor", "building", "bldg", "campus",
    "usa", "us", "uk", "eu",
})

#: Contractions that are not a prefix of the word they stand for. Other
#: abbreviations ("Univ", "Inst", "Lab") match any word they start.
CONTRACTIONS = {"dept": "department", "ctr": "center", "natl": "national", "govt": "government",
                "intl": "international", "assn": "association", "hosp": "hospital"}

#: Compound street names ("Musterstrasse", "Kalverstraat").
STREET_SUFFIXES = ("strasse", "gasse", "straat", "gatan", "gade", "vej")


def tokens(text) -> list:
    """Lower-case ASCII word tokens (accents folded)."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", s.lower())


def _fold(t: str) -> str:
    """Fold a plural ending: libraries -> library, institutes -> institute."""
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def _ignorable(t: str, place_words: Set[str], paren: Set[str]) -> bool:
    return (len(t) < 2 or t.isdigit() or t in STOPWORDS or t in ADDRESS_WORDS
            or t in place_words or t in paren
            or (len(t) > 6 and t.endswith(STREET_SUFFIXES)))


def _kept(t: str, kept: Set[str]) -> bool:
    """Is word ``t`` present in ``kept``, allowing for an abbreviation on either side
    ("univ" <-> "university", "dept" <-> "department")?"""
    f = _fold(t)
    if f in kept or CONTRACTIONS.get(t) in kept:
        return True
    if any(CONTRACTIONS.get(k) == t for k in kept):
        return True
    return any((len(t) >= 3 and k.startswith(t)) or (len(k) >= 3 and t.startswith(k)) for k in kept)


def _drops_identifying_word(src, dst, place_words: Set[str], paren: Set[str]) -> bool:
    kept = {_fold(t) for t in tokens(dst)}
    return any(not _kept(t, kept) and not _ignorable(t, place_words, paren) for t in tokens(src))


def changes_identity(variant, canonical, place_words: Iterable[str] = ()) -> bool:
    """True when remapping ``variant`` to ``canonical`` would name a different entity
    (an identifying word dropped or added). See the module docstring."""
    place = place_words if isinstance(place_words, (set, frozenset)) else set(place_words)
    paren: Set[str] = set()
    for inner in re.findall(r"\(([^)]*)\)", f"{variant or ''} {canonical or ''}"):
        paren.update(tokens(inner))
    return (_drops_identifying_word(variant, canonical, place, paren)
            or _drops_identifying_word(canonical, variant, place, paren))


def identity_guard(place_words: Iterable[str] = ()) -> Callable[[str, str], bool]:
    """A ``(variant, canonical) -> bool`` callable for :func:`fairly.cluster.synonym_lustre`."""
    place = frozenset(place_words)
    return lambda variant, canonical: changes_identity(variant, canonical, place)
