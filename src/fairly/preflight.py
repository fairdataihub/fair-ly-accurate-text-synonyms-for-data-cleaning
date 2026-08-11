"""Preflight: can ANY eps satisfy this gold set?

`validate` sweeps eps and reports the best V-measure. It answers "which eps is
least bad". It does not answer the prior question: *is there an eps that works at
all*, or is this field one where clustering cannot separate the cases no matter
how it is tuned, so you need an authority or a controlled vocabulary?

That question has a closed-form answer and it costs one embedding pass.

A single distance threshold can satisfy a gold set only if every pair that must
merge is closer than every pair that must not. Concretely, with `within` the
largest distance inside any true group and `between` the smallest distance across
two different groups, a workable eps exists exactly when

    within < between

When `within >= between` the requirements interleave: the thing that must merge is
more spread out than the thing that must not, so any eps loose enough to join the
first is loose enough to fuse the second. No sweep can find a good value because
none exists, and a sweep run anyway produces a flat or noisy curve that is easy to
misread as "the field is insensitive to eps".

This was found on a real funder-name corpus. The NIH institute strings that had to
stay apart spanned 0.342 to 0.740, while the funder-name variants that had to merge
spanned 0.000 to 0.707. Every eps from 0.03 to 0.30 gave an identical V-measure,
and the flat curve looked like robustness rather than the impossibility it was. The
fix was not a better eps; it was the controlled vocabulary that §3 and §7 already
recommend for acronym-bearing fields.

Reported quantities:

  separable        whether within < between
  margin           between - within; negative means impossible, near zero means fragile
  worst_within     the must-merge pair that is furthest apart, with its group
  worst_between    the must-not-merge pair that is closest, with its two groups
  eps_window       the usable (within, between) interval when separable

The offending pairs are the actionable part: they name the two strings to look at,
which is usually enough to see whether the gold set is wrong or the field genuinely
needs an authority.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence

import numpy as np


def _pairwise_cosine(mat: np.ndarray) -> np.ndarray:
    """Cosine DISTANCE matrix. Rows are assumed L2-normalised by the embedder."""
    sim = mat @ mat.T
    np.clip(sim, -1.0, 1.0, out=sim)
    return 1.0 - sim


def analyse(terms: Sequence[str],
            labels: Sequence[str],
            embeddings: np.ndarray,
            holdout_mask: Optional[Sequence[bool]] = None) -> Dict:
    """Decide whether a single distance threshold can satisfy this gold set.

    terms      the surface variants
    labels     the true canonical each variant belongs to
    embeddings one row per term, L2-normalised, same order as `terms`
    holdout_mask optional; True where a term is held out of clustering. Held-out
               terms are excluded, because a threshold is never applied to them
               and including them would report an impossibility the clusterer
               never actually faces.
    """
    if holdout_mask is not None:
        keep = [i for i, h in enumerate(holdout_mask) if not h]
        terms = [terms[i] for i in keep]
        labels = [labels[i] for i in keep]
        embeddings = embeddings[keep]

    n = len(terms)
    if n < 2:
        return {"separable": None, "reason": "fewer than two clusterable terms"}

    groups: Dict[str, List[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        groups[lab].append(i)

    multi = {k: v for k, v in groups.items() if len(v) > 1}
    if not multi:
        return {"separable": None,
                "reason": "no true group has two members, so nothing has to merge"}
    if len(groups) < 2:
        return {"separable": None,
                "reason": "only one true group, so nothing has to stay apart"}

    dist = _pairwise_cosine(np.asarray(embeddings, dtype=np.float32))

    worst_within = {"distance": -1.0}
    for lab, idx in multi.items():
        sub = dist[np.ix_(idx, idx)]
        k = int(np.argmax(sub))
        a, b = divmod(k, len(idx))
        d = float(sub[a, b])
        if d > worst_within["distance"]:
            worst_within = {"distance": d, "group": lab,
                            "a": terms[idx[a]], "b": terms[idx[b]]}

    labs = np.array(labels)
    worst_between = {"distance": float("inf")}
    for lab, idx in groups.items():
        other = np.where(labs != lab)[0]
        if not len(other):
            continue
        sub = dist[np.ix_(idx, other)]
        k = int(np.argmin(sub))
        a, b = divmod(k, len(other))
        d = float(sub[a, b])
        if d < worst_between["distance"]:
            worst_between = {"distance": d, "group_a": lab, "group_b": labels[other[b]],
                             "a": terms[idx[a]], "b": terms[other[b]]}

    within = worst_within["distance"]
    between = worst_between["distance"]
    separable = within < between
    out = {
        "separable": bool(separable),
        "n_terms": n,
        "n_groups": len(groups),
        "n_groups_needing_merge": len(multi),
        "within": within,
        "between": between,
        "margin": between - within,
        "worst_within": worst_within,
        "worst_between": worst_between,
    }
    if separable:
        out["eps_window"] = (within, between)
    return out


def format_report(res: Dict, field: str = "") -> str:
    """Human-readable verdict. Leads with the decision, then the evidence."""
    if res.get("separable") is None:
        return f"preflight: inconclusive ({res.get('reason')})"

    head = f"preflight{' for ' + field if field else ''}: "
    lines = []
    if res["separable"]:
        lo, hi = res["eps_window"]
        lines.append(head + f"SEPARABLE. Some eps in ({lo:.3f}, {hi:.3f}) can satisfy "
                            f"this gold set; margin {res['margin']:.3f}.")
        if res["margin"] < 0.05:
            lines.append("  Margin is thin, so the working window is narrow and a "
                         "corpus slightly denser than the gold set may close it. "
                         "Consider an authority as well.")
    else:
        lines.append(head + f"NOT SEPARABLE. No eps can satisfy this gold set; "
                            f"margin {res['margin']:.3f}.")
        lines.append("  The requirements interleave: something that must merge is "
                     "further apart than something that must not. Tuning eps trades "
                     "one error for the other. Use an authority (ROR) or a "
                     "controlled vocabulary for this field.")

    w, b = res["worst_within"], res["worst_between"]
    lines.append(f"  furthest must-merge pair   {w['distance']:.3f}  "
                 f"[{w['group']}]  {w['a']!r} vs {w['b']!r}")
    lines.append(f"  closest must-separate pair {b['distance']:.3f}  "
                 f"[{b['group_a']}] vs [{b['group_b']}]  {b['a']!r} vs {b['b']!r}")
    lines.append(f"  {res['n_terms']} clusterable terms, {res['n_groups']} groups, "
                 f"{res['n_groups_needing_merge']} of which must merge")
    return "\n".join(lines)
