"""Identity guard: does a remap still name the same entity?

Choosing a cluster's most frequent variant as its canonical has a failure mode the
holdout and the authority split do not cover: a short, generic name that is common in
the corpus absorbs longer, specific ones. In a poster corpus "Library & Researcher
Information Services" (a department of UL Research Institutes) became "Library",
"The Hockaday School" became "The Hotchkiss School", and "Wroclaw University" became
"Wroclaw University of Economics and Business".

Every word of a name falls in one of four classes:

* **ignorable**: stopwords (several languages), legal suffixes, address words, and an
  acronym in parentheses ("(UCLA)"). A remap may drop or add them freely.
* **place**: a city, region or country word (see
  :attr:`fairly.authorities.ror.RorIndex.place_words`). A remap may drop or add place
  words, but never swap them: "Ohio State University" -> "Iowa State University" and
  "University of California, Berkeley" -> "University of California, Los Angeles"
  change identity.
* **marker**: a number or a single letter. Same no-swap rule: dropping a street number
  is fine, "Universite Paris 1" -> "Universite Paris 8" is not.
* **content**: everything else. A remap changes identity when it drops or adds a
  content word.

On top of that a name may never reduce to only generic words (``generic_words``:
"University", "Hospital", "State", ...) while the other side has an identifying word
or a place word: "Columbia University" -> "University" changes identity even when
"Columbia" is a place word.

Names that are equal letter for letter, ignoring spacing, punctuation and case, are the
same ("PolitecnicodiTorino" = "Politecnico di Torino", "Smith-Jones Lab" = "SmithJones
Lab"). Content words match when they are the same after folding spelling variants (ae/oe/ue,
-re/-er, plurals, -ical/-ics/-ic/-ine/-al/-y endings, generic org words across
languages: "Universitat" = "University", "Centre" = "Center"), through a contraction
("Dept." = "Department", "Lab" = "Laboratory"), or as a prefix abbreviation. A prefix
abbreviation is written with a period ("Inst.") or is at least 4 letters, ends in a
consonant, is cut before a vowel and is not itself a generic word ("Univ", "Calif").
Ignorable and place words never act as abbreviations. Word order is free
("University of Heidelberg" -> "Heidelberg University" is fine).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

#: Words a remap may drop or add without changing which organization is meant.
STOPWORDS: FrozenSet[str] = frozenset({
    # English
    "the", "of", "and", "for", "in", "at", "on", "a", "an", "to", "by", "with",
    # German, Dutch, Scandinavian
    "und", "der", "den", "die", "das", "dem", "des", "zu", "zur", "zum", "fur", "im", "am",
    "an", "von", "vom", "van", "voor", "het", "en", "op", "och", "og", "i", "pa", "af",
    # Romance
    "y", "e", "et", "de", "del", "della", "delle", "dello", "dei", "degli", "di", "da",
    "do", "dos", "das", "du", "des", "la", "le", "les", "lo", "el", "los", "las", "al",
    "au", "aux", "pour", "sur", "per", "par", "por", "con", "em", "na", "no",
})

#: Legal suffixes: "Siemens AG" and "Siemens" are one company.
LEGAL_SUFFIXES: FrozenSet[str] = frozenset({
    "inc", "incorporated", "ltd", "limited", "llc", "llp", "lp", "plc", "co", "corp",
    "corporation", "company", "gmbh", "mbh", "ag", "kg", "ev", "sa", "sas", "sarl", "srl",
    "spa", "bv", "nv", "ab", "oy", "oyj", "aps", "pty", "pvt", "pte", "bhd",
    "sdn", "ltda", "sro", "kft", "kk",
})

#: Address words: an affiliation may lose its street address and stay the same place.
ADDRESS_WORDS: FrozenSet[str] = frozenset({
    "street", "st", "str", "strasse", "avenue", "ave", "road", "rd", "drive", "dr", "blvd",
    "boulevard", "lane", "way", "box", "po", "suite", "floor", "building", "bldg", "campus",
    "room", "cedex", "usa", "us", "uk", "eu",
})

#: Contractions: abbreviations that are not a prefix of the word they stand for, or
#: too short to pass as a prefix abbreviation.
CONTRACTIONS: Dict[str, str] = {
    "dept": "department", "depts": "department", "ctr": "center", "cntr": "center",
    "natl": "national", "govt": "government", "intl": "international",
    "assn": "association", "hosp": "hospital", "lab": "laboratory", "labs": "laboratory",
    "sci": "science", "tech": "technology", "sch": "school", "fac": "faculty",
    "med": "medicine", "mgmt": "management", "engr": "engineering", "hlth": "health",
    "univ": "university", "inst": "institute",
}

#: Generic organization words across languages, folded to one English form.
TRANSLATIONS: Dict[str, str] = {
    **dict.fromkeys(["universitat", "universidad", "universidade", "universite", "universita",
                     "universiteit", "universitet", "universitetet", "uniwersytet",
                     "universitas", "universiti", "univerzita", "universitatea"], "university"),
    **dict.fromkeys(["institut", "instituto", "istituto", "instytut", "institutet",
                     "instituut", "institutt"], "institute"),
    **dict.fromkeys(["centre", "centro", "zentrum", "centrum"], "center"),
    **dict.fromkeys(["hopital", "ospedale", "krankenhaus"], "hospital"),
    **dict.fromkeys(["klinik", "clinica", "clinique", "klinika"], "clinic"),
    **dict.fromkeys(["laboratorio", "laboratoire", "laboratorium"], "laboratory"),
    **dict.fromkeys(["facultad", "faculte", "facolta", "faculdade", "fakultat"], "faculty"),
    **dict.fromkeys(["departamento", "departement", "dipartimento", "departament"],
                    "department"),
    **dict.fromkeys(["escuela", "ecole", "escola", "scuola", "schule"], "school"),
    **dict.fromkeys(["academia", "akademie", "academie", "akademia"], "academy"),
    **dict.fromkeys(["biblioteca", "bibliotheque", "bibliothek"], "library"),
    **dict.fromkeys(["fundacion", "fundacao", "fondation", "fondazione", "stiftung"],
                    "foundation"),
    **dict.fromkeys(["sociedad", "sociedade", "societe", "societa", "gesellschaft"], "society"),
    **dict.fromkeys(["museo", "musee"], "museum"),
    **dict.fromkeys(["ministerio", "ministere", "ministero", "ministerium"], "ministry"),
    **dict.fromkeys(["nacional", "nazionale", "nationale"], "national"),
    **dict.fromkeys(["medicina", "medizin", "medecine"], "medicine"),
    **dict.fromkeys(["ciencia", "scienza"], "science"),
    **dict.fromkeys(["tecnologia", "technologie"], "technology"),
    **dict.fromkeys(["recherche", "ricerca", "forschung"], "research"),
    **dict.fromkeys(["biologia", "biologie"], "biology"),
    **dict.fromkeys(["chimie", "chemie", "chimica", "quimica"], "chemistry"),
    **dict.fromkeys(["fisica", "physique", "physik"], "physics"),
    **dict.fromkeys(["matematica", "mathematique", "mathematik"], "mathematics"),
}

#: Fallback generic words, used with (not instead of) the data-derived
#: :attr:`fairly.authorities.ror.RorIndex.generic_words`.
GENERIC_WORDS: FrozenSet[str] = frozenset({
    "university", "college", "institute", "school", "hospital", "center", "department",
    "faculty", "laboratory", "library", "academy", "foundation", "society", "association",
    "museum", "clinic", "agency", "council", "ministry", "office", "unit", "division",
    "program", "group", "service", "research", "science", "national", "international",
    "state", "federal", "general", "medical", "technology", "health", "community",
    "regional", "central", "public", "royal",
})

#: Compound street names ("Musterstrasse", "Kalverstraat").
STREET_SUFFIXES = ("strasse", "gasse", "straat", "gatan", "gade", "vej")

#: Stem endings, longest first, stripped when at least ``_MIN_STEM`` letters remain.
_STEM_SUFFIXES = ("ical", "ics", "ic", "ine", "al", "y")
_MIN_STEM = 4
_VOWELS = frozenset("aeiouy")
_TOKEN = re.compile(r"[a-z0-9]+")
_PAREN = re.compile(r"\(([^)]*)\)")
_SEGMENT_END = frozenset(",;:|")


def _ascii(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return s.lower()


def tokens(text) -> list:
    """Lower-case ASCII word tokens (accents folded)."""
    return _TOKEN.findall(_ascii(text))


@lru_cache(maxsize=1 << 16)
def _base(t: str) -> str:
    """Spelling fold that keeps a word's length class: ae/oe/ue -> a/o/u, contractions
    and generic words in other languages to their English form."""
    t = CONTRACTIONS.get(t, t)
    if t in TRANSLATIONS:
        return TRANSLATIONS[t]
    if len(t) > 3:
        t = re.sub(r"([aou])e", r"\1", t)
    return TRANSLATIONS.get(t, t)


@lru_cache(maxsize=1 << 16)
def _norm(t: str) -> str:
    """The form two words must share to count as the same word: :func:`_base`, then a
    plural, -re -> -er, and one stem ending folded."""
    b = _base(t)
    if len(b) > 4 and b.endswith("ies"):
        b = b[:-3] + "y"
    elif len(b) > 3 and b.endswith("s") and not b.endswith("ss"):
        b = b[:-1]
    b = TRANSLATIONS.get(b, b)
    if len(b) > 4 and b.endswith(("tre", "bre")):
        b = b[:-2] + "er"
    for suf in _STEM_SUFFIXES:
        if b.endswith(suf) and len(b) - len(suf) >= _MIN_STEM:
            return b[:-len(suf)]
    return b


def _is_marker(t: str, at_end: bool) -> bool:
    if t.isdigit() or re.fullmatch(r"\d+(st|nd|rd|th)", t):
        return True
    # A lone letter that is also a stopword ("y", "e") is a designation only at the
    # end of a segment ("Hospital A").
    return len(t) == 1 and (t not in STOPWORDS or at_end)


def _is_ignorable(t: str) -> bool:
    return (t in STOPWORDS or t in LEGAL_SUFFIXES or t in ADDRESS_WORDS
            or (len(t) > 6 and t.endswith(STREET_SUFFIXES)))


class _Seg:
    """The classified words of one segment of a name (the main text, or the text in
    one pair of parentheses)."""
    __slots__ = ("content", "places", "markers", "words", "n_tokens", "joined")

    def __init__(self):
        self.content: List[Tuple[str, str, bool, bool]] = []   # (base, norm, period, can_abbreviate)
        self.places: Set[str] = set()
        self.markers: Set[str] = set()
        self.words: List[Tuple[str, str, bool, bool]] = []     # every non-marker word
        self.n_tokens = 0
        self.joined = ""


class _Profile:
    """One phrase, tokenized and classified once (place and generic words fixed)."""
    __slots__ = ("main", "parens", "norms", "words", "initials", "cmask", "amask", "key")

    def __init__(self, text, place: FrozenSet[str], generic: FrozenSet[str]):
        s = _ascii(text)
        # letters and digits only: names equal in this form differ only in spacing,
        # punctuation or case ("PolitecnicodiTorino" = "Politecnico di Torino")
        self.key = "".join(_TOKEN.findall(s))
        self.main = self._segment(_PAREN.sub(" , ", s), place, generic)
        self.parens = [self._segment(inner, place, generic) for inner in _PAREN.findall(s)]
        segs = [self.main] + self.parens
        self.norms = frozenset(w[1] for g in segs for w in g.words)
        self.words = [w for g in segs for w in g.words]
        main_words = [w for w in self.main.words if w[0] not in STOPWORDS]
        self.initials = ("".join(w[0][0] for w in self.main.words),
                         "".join(w[0][0] for w in main_words))
        # Bit masks over the first two letters of each word, a cheap necessary
        # condition: every content word shares its first two letters with some word on
        # the other side (abbreviations are >= 3 letters). A word whose base and folded
        # forms start differently ("escuelas" -> "school") sets no content bit.
        self.cmask = 0
        for w in self.main.content:
            if w[0][:2] == w[1][:2]:
                self.cmask |= 1 << (hash(w[0][:2]) & 63)
        self.amask = 0
        for w in self.words:
            self.amask |= (1 << (hash(w[0][:2]) & 63)) | (1 << (hash(w[1][:2]) & 63))

    @staticmethod
    def _segment(s: str, place: FrozenSet[str], generic: FrozenSet[str]) -> _Seg:
        seg = _Seg()
        toks = []
        for m in _TOKEN.finditer(s):
            rest = s[m.end():]
            nxt = rest.lstrip(" .")[:1]
            toks.append((m.group(), rest.startswith("."), nxt == "" or nxt in _SEGMENT_END))
        seg.n_tokens = len(toks)
        seg.joined = "".join(t for t, _, _ in toks)
        for t, period, at_end in toks:
            if _is_marker(t, at_end):
                seg.markers.add(t)
                continue
            b, n = _base(t), _norm(t)
            ignorable = _is_ignorable(t)
            # A word that is itself a place word is one ("States" in "United States",
            # though "state" is generic); a folded form only when it is not generic.
            is_place = not ignorable and (t in place or (b in place and n not in generic))
            can_abbr = (not ignorable and not is_place and n not in generic
                        and ((period and len(b) >= 3)
                             or (len(b) >= 4 and b[-1] not in _VOWELS)))
            w = (b, n, period, can_abbr)
            seg.words.append(w)
            if is_place:
                seg.places.add(b)
            elif not ignorable:
                seg.content.append(w)
        return seg


def _abbreviates(a: Tuple[str, str, bool, bool], full: Tuple[str, str, bool, bool]) -> bool:
    """Is word ``a`` a prefix abbreviation of word ``full``? Without a period the cut
    must fall before a vowel ("Calif|ornia"), which rules out "Gene" -> "General"."""
    ab = a[0]
    if not a[3]:
        return False
    for f in (full[0], full[1]):
        if len(f) > len(ab) and f.startswith(ab) and (a[2] or f[len(ab)] in _VOWELS):
            return True
    return False


def _kept(w: Tuple[str, str, bool, bool], other: _Profile) -> bool:
    """Is content word ``w`` present on the other side (same folded form, or an
    abbreviation either way)?"""
    if w[1] in other.norms:
        return True
    return any(_abbreviates(w, k) or _abbreviates(k, w) for k in other.words)


def _active_segments(p: _Profile, other: _Profile) -> List[_Seg]:
    """``p``'s main segment plus each parenthesized segment that is not an acronym. An
    acronym is a single token that is not a place word ("(UCLA)", not "(France)"), or
    matches the initials of the other side."""
    segs = [p.main]
    for g in p.parens:
        if (g.n_tokens <= 1 and not g.places) or g.joined in other.initials:
            continue
        segs.append(g)
    return segs


def _no_swap(a: Set[str], b: Set[str]) -> bool:
    """Words of one kind may be dropped or added, never swapped."""
    return not a or not b or a <= b or b <= a


def _changes(a: _Profile, b: _Profile, generic: FrozenSet[str]) -> bool:
    if a.key and a.key == b.key:
        return False                                       # spacing, punctuation, case only
    if (a.cmask & ~b.amask) or (b.cmask & ~a.amask):
        return True                                        # a content word has no partner
    sa, sb = _active_segments(a, b), _active_segments(b, a)
    ca = [w for g in sa for w in g.content]
    cb = [w for g in sb for w in g.content]
    if not all(_kept(w, b) for w in ca) or not all(_kept(w, a) for w in cb):
        return True
    pa = set().union(*(g.places for g in sa))
    pb = set().union(*(g.places for g in sb))
    if not _no_swap(pa, pb):
        return True
    if not _no_swap(set().union(*(g.markers for g in sa)), set().union(*(g.markers for g in sb))):
        return True
    # Never reduce to generic words only while the other side names something.
    ga = all(w[1] in generic for w in ca) and not pa
    gb = all(w[1] in generic for w in cb) and not pb
    if ga and not gb:
        return bool(pb) or any(w[1] not in generic for w in cb)
    if gb and not ga:
        return bool(pa) or any(w[1] not in generic for w in ca)
    return False


def _generic_set(generic_words: Optional[Iterable[str]]) -> FrozenSet[str]:
    return frozenset(_norm(w) for w in GENERIC_WORDS.union(generic_words or ()))


def _place_set(place_words: Iterable[str]) -> FrozenSet[str]:
    return place_words if isinstance(place_words, frozenset) else frozenset(place_words)


def changes_identity(variant, canonical, place_words: Iterable[str] = (),
                     generic_words: Optional[Iterable[str]] = None) -> bool:
    """True when remapping ``variant`` to ``canonical`` would name a different entity.

    ``place_words`` are droppable place words, ``generic_words`` words that do not name
    an organization on their own (added to :data:`GENERIC_WORDS`). Both usually come
    from a ROR index or :func:`fairly.authorities.ror.identity_words_from_dump`. See the
    module docstring for the rules."""
    place, generic = _place_set(place_words), _generic_set(generic_words)
    return _changes(_Profile(variant, place, generic), _Profile(canonical, place, generic),
                    generic)


class IdentityGuard:
    """A ``(variant, canonical) -> bool`` callable for :func:`fairly.cluster.synonym_lustre`.

    Each phrase is tokenized once, and results are cached per (variant, canonical) pair,
    so a large cluster of mutually incompatible members stays fast. :meth:`blocked`
    checks many variants against one canonical in one call."""

    def __init__(self, place_words: Iterable[str] = (),
                 generic_words: Optional[Iterable[str]] = None, cache_size: int = 1 << 16):
        self.place_words = _place_set(place_words)
        self.generic_words = _generic_set(generic_words)
        self._profiles: Dict[str, _Profile] = {}
        self._pair = lru_cache(maxsize=cache_size)(self._uncached)

    def profile(self, text) -> _Profile:
        p = self._profiles.get(text)
        if p is None:
            p = self._profiles[text] = _Profile(text, self.place_words, self.generic_words)
        return p

    def _uncached(self, variant, canonical) -> bool:
        return _changes(self.profile(variant), self.profile(canonical), self.generic_words)

    def __call__(self, variant, canonical) -> bool:
        a, b = self.profile(variant), self.profile(canonical)
        if a.key and a.key == b.key:
            return False
        if (a.cmask & ~b.amask) or (b.cmask & ~a.amask):
            return True
        return self._pair(variant, canonical)

    def blocked(self, variants: Sequence[str], canonical) -> List[bool]:
        """``[self(v, canonical) for v in variants]``, with the cheap mask test inlined."""
        b = self.profile(canonical)
        bc, ba = b.cmask, ~b.amask
        profiles = self._profiles
        for v in variants:
            if v not in profiles:
                self.profile(v)
        quick = [bool(p.key != b.key and ((p.cmask & ba) or (bc & ~p.amask)))
                 for p in map(profiles.__getitem__, variants)]
        return [q or self._pair(v, canonical) for q, v in zip(quick, variants)]


def identity_guard(place_words: Iterable[str] = (),
                   generic_words: Optional[Iterable[str]] = None) -> IdentityGuard:
    """A ``(variant, canonical) -> bool`` callable for :func:`fairly.cluster.synonym_lustre`."""
    return IdentityGuard(place_words, generic_words)
