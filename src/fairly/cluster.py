"""The synonym-lustre clustering engine.

Given distinct field terms with frequencies and their embeddings, cluster the
terms with HDBSCAN and map every member of a cluster to a single canonical form
(the most frequent variant; ties broken by closeness to the cluster centroid).
Acronyms / short tokens are held out of the clusterer, and an optional authority
splits clusters that span more than one real entity.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from .holdout import clusterable_indices
from .synonyms import SynonymMap


def hdbscan_labels(emb: np.ndarray, eps: float, min_cluster_size: int = 2,
                   min_samples: int = 1, method: str = "leaf") -> np.ndarray:
    """Cluster labels for ``emb`` (noise = -1). Requires the ``cluster`` extra."""
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError(
            "Semantic clustering needs the 'cluster' extra: "
            "pip install fairly-synonyms[cluster]"
        ) from exc
    return HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_epsilon=eps,
        cluster_selection_method=method,
        metric="euclidean",
    ).fit_predict(emb)


def _centroid_canonical(idxs: Sequence[int], phrases: Sequence[str],
                        emb: np.ndarray, counts: Dict[str, int]) -> int:
    """Index (within ``idxs``) of the canonical: most frequent variant, with the
    centroid-closest variant breaking ties among equally-frequent ones."""
    sub = emb[list(idxs)]
    dists = np.linalg.norm(sub - sub.mean(axis=0), axis=1)
    members = [phrases[i] for i in idxs]
    return max(range(len(idxs)), key=lambda k: (counts[members[k]], -float(dists[k])))


def synonym_lustre(
    counts: Dict[str, int],
    emb: np.ndarray,
    eps: float,
    *,
    min_cluster_size: int = 2,
    min_samples: int = 1,
    method: str = "leaf",
    holdout: bool = True,
    min_holdout_len: int = 4,
    authority=None,
    field: Optional[str] = None,
) -> SynonymMap:
    """Build a :class:`SynonymMap` from term counts + their embeddings.

    ``emb`` rows must align with ``list(counts.keys())``. ``authority`` (optional)
    is anything with a ``.split(idxs, phrases, emb)`` method (e.g. RorAuthority).
    """
    phrases = list(counts.keys())
    if emb.shape[0] != len(phrases):
        raise ValueError("emb rows must align with counts keys")

    clusterable = clusterable_indices(phrases, min_holdout_len) if holdout else list(range(len(phrases)))
    labels = np.full(len(phrases), -1, dtype=int)
    if clusterable:
        sub = hdbscan_labels(emb[clusterable], eps, min_cluster_size, min_samples, method)
        labels[np.asarray(clusterable)] = sub

    mapping: Dict[str, str] = {}
    clusters: Dict[str, List[str]] = {}
    n_split = 0

    def emit(idxs: List[int]) -> None:
        members = [phrases[i] for i in idxs]
        rep = members[_centroid_canonical(idxs, phrases, emb, counts)]
        for m in members:
            if m != rep:
                mapping[m] = rep
        if len(members) > 1:
            clusters[rep] = sorted(members, key=lambda m: -counts[m])

    for lbl in sorted(set(labels.tolist())):
        if lbl < 0:
            continue
        idxs = list(np.where(labels == lbl)[0])
        if authority is not None and len(idxs) > 1:
            parts = authority.split(idxs, phrases, emb)
            if len(parts) > 1:
                n_split += 1
            for part in parts:
                emit(list(part))
        else:
            emit(idxs)

    meta = {"eps": eps, "holdout": holdout, "authority": authority is not None,
            "n_clusters": len(clusters), "n_authority_splits": n_split,
            "n_terms": len(phrases), "n_held_out": len(phrases) - len(clusterable)}
    return SynonymMap(mapping, clusters, field=field, meta=meta)
