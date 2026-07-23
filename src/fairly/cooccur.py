"""Lexicon TF-IDF co-occurrence synonym collapse (``strategy="cooccur"``).

For COMPLEX terms where embed-cluster synonym-lustre under-merges (an acronym and its expansion, a term and
its context-defined equivalents), represent each term by its distribution over DOCUMENTS (a TF-IDF context
profile), link terms with similar document profiles, and take the graph's Louvain communities as synonym
clusters. Optionally fold in a synonym LEXICON (e.g. a UMLS dump, list-of-synonym-groups): terms that share a
lexicon group are merged even when their document contexts differ. Adapted from J. O'Neill's CarDT
co-occurrence collapse; returns a fairly :class:`SynonymMap`, so it composes with the deterministic cleaners.

Memory-safe by construction: the term x term similarity is never materialized dense -- edges are extracted in
row-blocks and thresholded to a sparse graph, so a 25k-term vocabulary stays well within RAM.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence

import numpy as np

from .synonyms import SynonymMap


def _term_doc_profiles(terms: Sequence[str], docs: Sequence[str]):
    """Each term -> its L2-normalized TF-IDF affinity over the document corpus (sparse T x D)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
    vec = TfidfVectorizer()
    dtm = normalize(vec.fit_transform(docs), axis=1, norm="l2")        # docs x vocab
    tvec = normalize(vec.transform(list(terms)), axis=1, norm="l2")     # terms x vocab (term as mini-query)
    return normalize(tvec @ dtm.T, axis=1, norm="l2").tocsr().astype(np.float32)  # terms x docs, row-normalized (f32)


def _graph_edges(profiles, threshold: float, block: int = 2000, top_k: int = 0):
    """(i, j, weight) edges with cosine(profile_i, profile_j) > threshold. Three compression levers, so this
    scales past the O(N^2) blow-up (the impact-matrix-v2 technique) to a 1-3M-term vocabulary:
      * row-BLOCKED: at most `block` rows processed at a time.
      * SPARSE: the block product profiles[s:e] @ profiles.T is kept sparse (only co-occurring pairs are
        nonzero) and is NEVER densified -- so a block is O(nnz), not O(block*N).
      * TOP-K per node (when top_k>0): keep only each node's strongest `top_k` neighbours, bounding the graph
        to O(N*top_k) edges regardless of N (as pub_rank_incremental does for the impact matrix). Set it for a
        large vocabulary; leave 0 (unbounded) for a small, well-separated set.
    """
    T = profiles.shape[0]
    edges = []
    pt = profiles.T.tocsr()
    for s in range(0, T, block):
        e = min(s + block, T)
        sb = (profiles[s:e] @ pt).tocsr()            # sparse (<=block) x T; nonzeros = co-occurring pairs only
        for r in range(e - s):
            i = s + r
            lo, hi = sb.indptr[r], sb.indptr[r + 1]
            cols = sb.indices[lo:hi]
            vals = sb.data[lo:hi]
            m = (vals > threshold) & (cols != i)     # above threshold, no self-edge
            cols, vals = cols[m], vals[m]
            if top_k and cols.size > top_k:          # keep only the strongest top_k neighbours
                keep = np.argpartition(vals, -top_k)[-top_k:]
                cols, vals = cols[keep], vals[keep]
            for j, w in zip(cols.tolist(), vals.tolist()):
                a, b = (i, j) if i < j else (j, i)
                if a != b:
                    edges.append((a, b, float(w)))
    return edges


def _louvain(n: int, edges) -> List[List[int]]:
    import networkx as nx
    import community as community_louvain
    G = nx.Graph()
    G.add_nodes_from(range(n))
    G.add_weighted_edges_from(edges)
    part = community_louvain.best_partition(G, weight="weight", random_state=42)
    groups: Dict[int, List[int]] = defaultdict(list)
    for node, cid in part.items():
        groups[cid].append(node)
    return [g for g in groups.values() if len(g) > 1]


def _lexicon_index(lexicon: Sequence[Sequence[str]], vocab: Optional[set] = None):
    """term (lowercased) -> set of frozenset lexicon groups it belongs to. Cross-matches the corpus terms
    against the lexicon's own surface variants (a UMLS dump already carries spaced / no-space / lc variants).
    When ``vocab`` is given, ONLY groups that touch the vocabulary are indexed -- so a 1.2M-group UMLS dump
    collapses to the few thousand groups relevant to this field, keeping the index small (the OOM guard)."""
    word2groups: Dict[str, set] = defaultdict(set)
    for g in lexicon:
        members = [str(w).strip().lower() for w in g if str(w).strip()]
        if len(members) < 2:
            continue
        if vocab is not None and not any(m in vocab for m in members):
            continue
        key = frozenset(members)
        for w in members:
            if vocab is None or w in vocab:
                word2groups[w].add(key)
    return word2groups


def _merge_by_lexicon(term_clusters: List[List[str]], singletons: List[str], word2groups) -> List[List[str]]:
    """Merge clusters whose members share a lexicon group; then attach singleton terms that share a group
    with a cluster. Union-find over cluster indices."""
    def groups_of(t):
        return word2groups.get(t.lower(), set())
    sets = [set(c) for c in term_clusters]
    parent = list(range(len(sets)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    # cluster-cluster merges via a shared lexicon group
    group_owner: Dict[frozenset, int] = {}
    for ci, members in enumerate(sets):
        seen = set()
        for w in members:
            seen |= groups_of(w)
        for grp in seen:
            if grp in group_owner:
                union(group_owner[grp], ci)
            else:
                group_owner[grp] = ci
    merged: Dict[int, set] = defaultdict(set)
    for ci in range(len(sets)):
        merged[find(ci)] |= sets[ci]
    out = [s for s in merged.values()]
    # attach singletons that co-occur in a lexicon group with any cluster member
    member_groups = [set().union(*[groups_of(w) for w in s]) if s else set() for s in out]
    for t in singletons:
        gt = groups_of(t)
        if not gt:
            continue
        for k, mg in enumerate(member_groups):
            if gt & mg:
                out[k].add(t); break
    return [list(s) for s in out if len(s) > 1]


def cooccur_synonyms(
    counts: Dict[str, int],
    docs: Optional[Sequence[str]] = None,
    *,
    threshold: float = 0.5,
    lexicon: Optional[Sequence[Sequence[str]]] = None,
    block: int = 2000,
    top_k: int = 0,
    field: Optional[str] = None,
) -> SynonymMap:
    """Build a :class:`SynonymMap` from term counts + a document corpus (TF-IDF co-occurrence graph) and/or a
    synonym ``lexicon`` (list of synonym groups). At least one of ``docs``/``lexicon`` must be given. Canonical
    per cluster = the most frequent member. ``top_k`` bounds each node's neighbours (0 = unbounded); set it for
    a large vocabulary so the graph stays O(N*top_k)."""
    terms = list(counts.keys())
    idx_clusters: List[List[int]] = []
    if docs is not None:
        profiles = _term_doc_profiles(terms, docs)
        idx_clusters = _louvain(len(terms), _graph_edges(profiles, threshold, block, top_k))
    term_clusters = [[terms[i] for i in c] for c in idx_clusters]

    if lexicon is not None:
        word2groups = _lexicon_index(lexicon, vocab={t.lower() for t in terms})
        clustered = {t for c in term_clusters for t in c}
        singletons = [t for t in terms if t not in clustered]
        term_clusters = _merge_by_lexicon(term_clusters, singletons, word2groups) if term_clusters \
            else _merge_by_lexicon([[t] for t in terms], [], word2groups)

    mapping: Dict[str, str] = {}
    clusters: Dict[str, List[str]] = {}
    for members in term_clusters:
        members = sorted(set(members), key=lambda m: -counts.get(m, 0))
        if len(members) < 2:
            continue
        rep = members[0]
        for m in members[1:]:
            mapping[m] = rep
        clusters[rep] = members
    meta = {"strategy": "cooccur", "threshold": threshold, "used_docs": docs is not None,
            "used_lexicon": lexicon is not None, "n_terms": len(terms), "n_clusters": len(clusters)}
    return SynonymMap(mapping, clusters, field=field, meta=meta)
