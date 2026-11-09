"""Acronyms resolved from the text that defines them.

The holdout keeps acronyms out of the embedding (an embedding cannot place ``BTK``),
which leaves ``BTK`` and ``Bruton tyrosine kinase`` as two values. Authors define an
acronym the first time they use it, "Bruton tyrosine kinase (BTK)", so a corpus of
titles, abstracts or descriptions is its own acronym lexicon. This module reads those
definitions (Schwartz & Hearst, 2003) and turns them into a :class:`SynonymMap`, a
deterministic pass that needs no model.

One acronym often stands for several things: across PubMed "AMP" is adenosine
monophosphate, antimicrobial peptide and more, "EGFR" both the EGF receptor and the
estimated glomerular filtration rate. Mapping every definition would chain unrelated
terms together, so an acronym is resolved only when one meaning dominates:

1. Its long forms are grouped first, so spelling variants count together: a long form
   joins the first more frequent one that the identity guard lets it map to: case,
   punctuation, plurals and possessives ("Bruton's / Bruton / Brutons tyrosine kinase").
   British and American spellings stay apart ("leukaemia", "leukemia"); the semantic
   pass merges those.
2. The largest group needs ``min_share`` of all the acronym's definitions.
3. When ``counts`` gives how often the acronym occurs as a value, its definitions must
   cover ``min_coverage`` of those occurrences. This keeps a common word that is also an
   acronym unmapped when case has been lost ("fish" the animal against "FISH" the assay).
4. ``identity_of`` (optional) names an authority id for a term (a ROR id, a MeSH
   descriptor); no mapping joins two terms with different ids.

The acronym and the group's other variants map to the group's most frequent long form.

    from fairly.acronyms import count_definitions, acronym_map

    defs = count_definitions(abstracts)                 # Counter{(short, long): texts}
    amap = acronym_map(defs, counts=value_counts)
    amap.apply("BTK")                                   # 'Bruton tyrosine kinase'
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from .synonyms import SynonymMap

_PAREN_RE = re.compile(r"\(([^()]{1,15})\)")


def _short_ok(sf: str) -> bool:
    return (2 <= len(sf) <= 10 and any(c.isalpha() for c in sf) and sf[0].isalnum()
            and len(sf.split()) <= 2)


def best_long_form(sf: str, candidate: str) -> Optional[str]:
    """The long form of ``sf`` at the end of ``candidate`` (Schwartz & Hearst, 2003): the
    shortest tail whose characters match the short form's from right to left, the first
    one at the start of a word. ``None`` when there is no such tail or it is implausible
    (not longer than the short form, contains it as a word, or has too many words)."""
    s, i = len(sf) - 1, len(candidate) - 1
    while s >= 0:
        c = sf[s].lower()
        if not c.isalnum():
            s -= 1
            continue
        while i >= 0 and (candidate[i].lower() != c
                          or (s == 0 and i > 0 and candidate[i - 1].isalnum())):
            i -= 1
        if i < 0:
            return None
        i -= 1
        s -= 1
    out = candidate[candidate.rfind(" ", 0, i + 1) + 1:].strip()
    words = out.split()
    if (len(out) <= len(sf) or sf.lower() in (w.lower() for w in words)
            or len(words) > min(len(sf) + 5, 2 * len(sf))):
        return None
    return out


def definitions(text: str) -> List[Tuple[str, str]]:
    """``[(short form, long form)]`` defined in ``text`` as "long form (SF)", as written
    (case kept, spacing collapsed, trailing punctuation off the long form)."""
    out = []
    for m in _PAREN_RE.finditer(text):
        sf = " ".join(m.group(1).split())
        if not _short_ok(sf):
            continue
        words = text[:m.start()].split()[-min(len(sf) + 5, 2 * len(sf)):]
        if not words:
            continue
        lf = best_long_form(sf, " ".join(words))
        if lf:
            out.append((sf, lf.strip(" ,;:")))
    return out


def count_definitions(texts: Iterable[str], into: Optional[Counter] = None) -> Counter:
    """``Counter{(short, long): number of texts defining it}``; a text counts once per pair.

    Memory grows with the number of distinct pairs (7.4 million over PubMed titles and
    abstracts). For a corpus that size, count shards in parallel and add the Counters, or
    keep the counts in a database and pass :func:`acronym_map` any mapping. ``into`` adds
    to an existing Counter."""
    counts: Counter = into if into is not None else Counter()
    for text in texts:
        if isinstance(text, str) and "(" in text:
            counts.update(set(definitions(text)))
    return counts


def acronym_map(
    defs: Mapping[Tuple[str, str], int],
    counts: Optional[Mapping[str, int]] = None,
    *,
    min_share: float = 0.6,
    min_coverage: float = 0.1,
    min_texts: int = 3,
    guard: Optional[Callable[[str, str], bool]] = None,
    identity_of: Optional[Callable[[str], Optional[str]]] = None,
    clean: Optional[Callable[[str], Optional[str]]] = None,
    field: Optional[str] = None,
) -> SynonymMap:
    """A :class:`SynonymMap` from acronym definitions (see the module docstring).

    ``defs``        ``{(short, long): texts}``, e.g. from :func:`count_definitions`. Any
                    mapping works, so the counting can live in a database for a large corpus.
    ``counts``      value frequencies of the field. When given, a short form is matched to
                    the field values it stands for (after ``clean``, then ignoring case), the
                    map's keys are those values, and ``min_coverage`` applies to their total.
    ``min_texts``   the dominant meaning must come from at least this many texts. Every
                    definition, however rare, counts toward the share denominator.
    ``guard``       ``(variant, canonical) -> bool``, True when the remap names a different
                    entity; defaults to :class:`fairly.identity.IdentityGuard`.
    ``identity_of`` optional term -> authority id. Long forms with two different ids never
                    share a group, and no value maps across two different ids.
    ``clean``       optional cleaner applied to both forms (and to the ``counts`` keys) first,
                    e.g. :data:`fairly.presets.TERM_CLEANER`; a form it drops is skipped.
    """
    if guard is None:
        from .identity import IdentityGuard
        guard = IdentityGuard()
    by_short: Dict[str, Counter] = {}
    for (sf, lf), n in defs.items():
        if clean is not None:
            sf, lf = clean(sf), clean(lf)
            if not sf or not lf:
                continue
        by_short.setdefault(sf, Counter())[lf] += n

    exact: Dict[str, List[str]] = {}
    folded: Dict[str, List[str]] = {}
    if counts is not None:
        for v in counts:
            k = clean(v) if clean is not None else v
            if k:
                exact.setdefault(k, []).append(v)
                folded.setdefault(k.casefold(), []).append(v)

    def conflict(a: str, b: str) -> bool:
        if identity_of is None:
            return False
        ia, ib = identity_of(a), identity_of(b)
        return bool(ia and ib and ia != ib)

    mapping: Dict[str, str] = {}
    clusters: Dict[str, List[str]] = {}
    n_rare = n_ambiguous = n_uncovered = n_conflict = 0
    for sf in sorted(by_short):
        if counts is None:
            values = [sf]
        else:
            values = sorted(exact.get(sf) or folded.get(sf.casefold()) or [])
            if not values:
                continue
        forms = by_short[sf]
        total = sum(forms.values())
        groups: List[List] = []                       # [head, members, texts]
        for lf, n in sorted(forms.items(), key=lambda x: (-x[1], x[0])):
            for g in groups:
                if not guard(lf, g[0]) and not conflict(lf, g[0]):
                    g[1].append(lf)
                    g[2] += n
                    break
            else:
                groups.append([lf, [lf], n])
        head, members, n = max(groups, key=lambda g: (g[2], -groups.index(g)))
        if n < min_texts:
            n_rare += 1
            continue
        if n < min_share * total:
            n_ambiguous += 1
            continue
        if counts is not None and n < min_coverage * sum(counts[v] for v in values):
            n_uncovered += 1
            continue
        if any(conflict(v, head) for v in [sf] + values):
            n_conflict += 1
            continue
        cluster = clusters.setdefault(head, [head])
        for v in values + [m for m in members if m != head]:
            if v != head:
                mapping.setdefault(v, head)
            if v not in cluster:
                cluster.append(v)
    return SynonymMap(mapping, clusters, field=field,
                      meta={"strategy": "acronyms", "n_rare": n_rare, "n_ambiguous": n_ambiguous,
                            "n_uncovered": n_uncovered, "n_conflict": n_conflict})
