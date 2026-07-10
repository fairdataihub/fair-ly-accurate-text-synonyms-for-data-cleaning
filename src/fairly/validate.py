"""V-measure validation of synonym clustering against a gold set.

Given a gold set of ``surface_variant -> true_canonical`` pairs, we embed the
variants exactly as the normalizer would, cluster them across a sweep of
``cluster_selection_epsilon`` values, and score each clustering against the gold
labels with homogeneity, completeness and V-measure
(``sklearn.metrics.homogeneity_completeness_v_measure``).

Noise handling: HDBSCAN labels some points ``-1`` (noise). We explode each noise
point into its own singleton cluster before scoring, so an over-cautious eps that
leaves many points unclustered is penalised on completeness rather than silently
ignored. This matches how the normalizer treats noise (a noise term maps only to
itself).

V-measure is the harmonic mean of:
  * homogeneity  -- each predicted cluster contains only one true entity
    (penalises OVER-merge, the costly failure mode here), and
  * completeness -- all variants of one true entity land in one cluster
    (penalises UNDER-merge).

Use the eps that maximises V-measure as the field's setting.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_EPS_SWEEP = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]


def load_gold(path: str) -> Dict[str, str]:
    """Load a gold set. ``.json`` = ``{variant: canonical}``; else TSV
    ``variant<TAB>canonical`` (a ``...\\tcanonical`` header and blank lines skipped)."""
    import json
    import os
    if os.path.splitext(path)[1].lower() == ".json":
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    gold: Dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            variant, canon = parts[0].strip(), parts[1].strip()
            if variant.lower() == "surface_variant" or canon.lower() == "true_canonical":
                continue
            gold[variant] = canon
    return gold


def _explode_noise(labels: np.ndarray) -> np.ndarray:
    out = labels.copy()
    nxt = int(out.max()) + 1 if len(out) and out.max() >= 0 else 0
    for i in range(len(out)):
        if out[i] < 0:
            out[i] = nxt
            nxt += 1
    return out


def sweep_eps(
    gold: Dict[str, str],
    eps_list: Sequence[float] = DEFAULT_EPS_SWEEP,
    *,
    embedding_model: Optional[str] = None,
    cache_dir: Optional[str] = None,
    holdout: bool = True,
    min_cluster_size: int = 2,
    min_samples: int = 1,
    method: str = "leaf",
    emb: Optional[np.ndarray] = None,
) -> List[dict]:
    """Return one row per eps: ``{eps, homogeneity, completeness, v_measure, n_clusters}``.

    ``emb`` may be supplied to avoid recomputation; otherwise variants are embedded
    with :func:`fairly.embeddings.embed`.
    """
    from sklearn.metrics import homogeneity_completeness_v_measure

    from .cluster import hdbscan_labels
    from .embeddings import DEFAULT_MODEL, embed
    from .holdout import clusterable_indices

    variants = list(gold.keys())
    true = np.array([gold[v] for v in variants])
    if emb is None:
        emb = embed(variants, embedding_model or DEFAULT_MODEL, cache_dir, show_progress=False)

    clusterable = clusterable_indices(variants) if holdout else list(range(len(variants)))

    rows = []
    for eps in eps_list:
        labels = np.full(len(variants), -1, dtype=int)
        if clusterable:
            labels[np.asarray(clusterable)] = hdbscan_labels(
                emb[clusterable], eps, min_cluster_size, min_samples, method)
        pred = _explode_noise(labels)
        h, c, v = homogeneity_completeness_v_measure(true, pred)
        rows.append({"eps": eps, "homogeneity": h, "completeness": c,
                     "v_measure": v, "n_clusters": len(set(labels.tolist()) - {-1})})
    return rows


def best_eps(rows: List[dict]) -> dict:
    """The sweep row with the highest V-measure."""
    return max(rows, key=lambda r: r["v_measure"])


def format_table(rows: List[dict]) -> str:
    out = ["   eps   homogeneity  completeness  v_measure  clusters",
           "  ----  -----------  ------------  ---------  --------"]
    for r in rows:
        out.append(f"  {r['eps']:.2f}      {r['homogeneity']:.3f}         {r['completeness']:.3f}"
                   f"       {r['v_measure']:.3f}     {r['n_clusters']:5d}")
    b = best_eps(rows)
    out.append(f"  best: eps={b['eps']:.2f}  v_measure={b['v_measure']:.3f}")
    return "\n".join(out)
