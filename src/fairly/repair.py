"""Repairs for text a PDF extraction damaged. No model is involved: every repair
either copies the letters of a reference text that holds the same words (the
record's own deposit title or description) or completes a word from a vocabulary
of words people typed.

Three kinds of damage are handled:

* **undecodable ligatures**: a font that draws "ti", "tt" or "ft" as one glyph
  without a Unicode mapping comes out as U+FFFD ("es\\ufffdma\\ufffdon");
* **lost accents and scrambled capitals**: "Analise" for "Análise", "SÃo" for
  "São";
* **text extracted twice**: bold type drawn twice in the PDF
  ("OBSTRUCAO OBSTRUCAO DE DE VIAS VIAS").

Each repair changes only the damaged words and keeps the extracted text's own
case, punctuation and spacing, so clean text is never restyled after a reference.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
from collections import Counter
from typing import Iterable, Mapping, Optional, Sequence

FFFD = "\ufffd"

# Letters a PDF font draws as one glyph; an undecodable one comes out as U+FFFD.
LIGATURE_FILLS = ("ti", "tt", "ft", "fi", "fl", "ff", "ffi", "ffl", "st", "tf", "th")

_WORD_RE = re.compile(r"[^\W\d_]+")
_FFFD_WORD_RE = re.compile(r"[\w\ufffd]*\ufffd[\w\ufffd]*")
# Scripts written without spaces between syllables (Han, Kana, Hangul): one
# character is a syllable, so two of them make a word.
_SYLLABIC_RE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")


def strip_accents(s: str) -> str:
    """`s` without combining marks ("Análise" -> "Analise")."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def has_word(s) -> bool:
    """True when `s` holds a real word in any script: a token of two or more
    letters (Latin "Ng", Cyrillic "Попова", Devanagari letters joined by vowel
    signs) or two syllabic characters ("李, 杰"). Bare Latin initials ("M., A",
    "D") hold none."""
    s = str(s or "")
    if any(sum(ch.isalpha() for ch in tok) >= 2 for tok in re.split(r"[\s,.;:()/]+", s)):
        return True
    return len(_SYLLABIC_RE.findall(s)) >= 2


def word_counts(texts: Iterable[str]) -> Counter:
    """Case-folded word counts of `texts`: the vocabulary for :func:`repair_ligatures`.
    Build it from text people typed (repository titles, descriptions, keywords,
    authority names), not from the damaged extraction."""
    out = Counter()
    for t in texts:
        if isinstance(t, str):
            out.update(w.casefold() for w in _WORD_RE.findall(re.sub(r"<[^>]+>", " ", t)))
    return out


def repair_ligatures(text, vocab: Mapping[str, int]):
    """Fill each U+FFFD inside a word with the ligature letters that make a known
    word, the most frequent in `vocab`, in the case of the word around it
    ("Federa\\ufffdon" -> "Federation", "MEE\\ufffdNG" -> "MEETING"). A glyph at the end
    of a word may be a word split across a line ("Ins\\ufffd tu\\ufffd on"), so it is
    filled only when that makes a known word of six or more letters or a very
    common one ("multi" in "multi-band"), and a word of two letters only when it
    makes a very common one ("soft"); a lone glyph (in a formula) is left alone, and
    so is a word no fill makes known. Returns the new text."""
    if not isinstance(text, str) or FFFD not in text:
        return text

    def fix(m):
        word = m.group(0)
        n = word.count(FFFD)
        letters = sum(ch.isalpha() for ch in word)
        if n > 3 or letters < 2:              # a lone glyph in a formula is no word
            return word
        edge = word.endswith(FFFD)
        upper = sum(ch.isupper() for ch in word) >= 2 and not any(ch.islower() for ch in word)
        best = None
        for combo in itertools.product(LIGATURE_FILLS, repeat=n):
            it = iter(combo)
            cand = "".join(next(it) if ch == FFFD else ch for ch in word)
            f = vocab.get(cand.casefold(), 0)
            if (edge or letters < 3) and not ((len(cand) >= 6 and f >= 3) or f >= 25):
                continue
            if f and (best is None or f > best[0]):
                best = (f, combo)
        if not best:
            return word
        it = iter(c.upper() if upper else c for c in best[1])
        return "".join(next(it) if ch == FFFD else ch for ch in word)

    return _FFFD_WORD_RE.sub(fix, text)


def undouble(text: str) -> str:
    """Words extracted twice ("OBSTRUCAO OBSTRUCAO DE DE VIAS VIAS (OVACE)") once,
    when at least three repeats make up most of the text; anything else unchanged."""
    w, out, pairs, i = text.split(), [], 0, 0
    while i < len(w):
        if i + 1 < len(w) and w[i] == w[i + 1]:
            pairs += 1
            i += 1
        out.append(w[i])
        i += 1
    return " ".join(out) if pairs >= 3 and 2 * pairs >= 0.6 * len(w) else text


def _tokens(s):
    """Word tokens of `s` with their spans; a U+FFFD inside or next to a word joins it."""
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"(?:[^\W_]|\ufffd)+", s)]


def _token_pattern(tok):
    """The reference word a damaged word stands for: accents and case free, each
    U+FFFD 1-3 letters."""
    return re.compile("".join(r"[^\W\d_]{1,3}" if ch == FFFD else re.escape(strip_accents(ch).casefold())
                              for ch in tok))


def _diacritics(s):
    return sum(1 for c in unicodedata.normalize("NFKD", s) if unicodedata.combining(c))


def _in_case_of(new, old):
    """`new` in the letter case of `old`: letter for letter when the lengths agree;
    else all capitals for an all-capital word, else the first letter's case."""
    if len(new) == len(old):
        return "".join(n.upper() if o.isupper() else n.lower() if o.islower() else n for n, o in zip(new, old))
    letters = [c for c in old if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return new.upper()
    if letters:
        return (new[0].upper() if old[0].isupper() else new[0].lower()) + new[1:]
    return new


def _odd_case(tok):
    """Capitals an extraction scrambled: an accented capital after a small letter
    ("EpidemiolÓgica", "SÃo"), or a final capital after three small letters
    ("AnalisE")."""
    for k in range(1, len(tok)):
        if tok[k].isupper() and tok[k - 1].islower():
            if _diacritics(tok[k]) or (k == len(tok) - 1 and k >= 3 and tok[k - 3:k].islower()):
                return True
    return False


def repair_from_reference(text, references: Sequence[str], min_letters: int = 12) -> Optional[str]:
    """Repair an extracted text with a reference's own words. When a reference holds
    the same words in the same order, ignoring case and accents, with each U+FFFD
    standing for 1-3 letters and a text extracted twice read once, only the damaged
    words change: a word that lost its accents takes the reference's ("Analise" ->
    "Análise", "Baden-Wurttemberg" -> "Baden-Württemberg") and a word with an
    undecodable ligature takes the reference's letters ("es\\ufffdma\\ufffdon" ->
    "estimation"), each in the text's own letter case. Punctuation, spacing and every
    other word stay as extracted. A text matching the whole reference whose capitals
    are scrambled in two or more words ("AnalisE EpidemiolÓgica ... SÃo Paulo") takes
    the reference as it is.

    Returns the repaired text, or None when no reference matches, a match is
    ambiguous, the text has fewer than `min_letters` letters, or nothing would
    change."""
    if not isinstance(text, str) or not text.strip():
        return None
    flat = " ".join(text.split())
    base = undouble(flat)
    toks = _tokens(base)
    if len(toks) < 2 or sum(len(t[2].replace(FFFD, "")) for t in toks) < min_letters:
        return None
    pats = [_token_pattern(t[2]) for t in toks]
    for ref in references or []:
        if not isinstance(ref, str) or not ref.strip():
            continue
        ref = " ".join(ref.split())
        rtoks = _tokens(ref)
        rfold = [strip_accents(t[2]).casefold() for t in rtoks]
        hits = [k for k in range(len(rtoks) - len(toks) + 1)
                if all(pats[n].fullmatch(rfold[k + n]) for n in range(len(toks)))]
        if len(hits) != 1:
            continue
        k = hits[0]
        if k == 0 and len(toks) == len(rtoks) and sum(_odd_case(t[2]) for t in toks) >= 2:
            return ref if ref != flat else None
        out, pos = [], 0
        for n, (a, b, tok) in enumerate(toks):
            rtok = rtoks[k + n][2]
            new = tok
            if FFFD in tok or (_diacritics(rtok) > _diacritics(tok)
                               and strip_accents(rtok).casefold() == strip_accents(tok).casefold()):
                new = _in_case_of(rtok, tok)
            out.append(base[pos:a] + new)
            pos = b
        out.append(base[pos:])
        res = "".join(out)
        return res if res != flat else None
    return None
