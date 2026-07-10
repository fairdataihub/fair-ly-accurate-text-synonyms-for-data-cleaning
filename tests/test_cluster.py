from collections import Counter

import numpy as np

import fairly.cluster as cl
from fairly.cluster import synonym_lustre


def test_canonical_is_most_frequent(monkeypatch):
    counts = Counter({"Stanford University": 10, "Stanford Univ.": 3, "Stanford U": 2})
    emb = np.array([[1.0, 0.0], [0.98, 0.02], [0.97, 0.03]])
    # one cluster of all three
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    smap = synonym_lustre(counts, emb, eps=0.2, holdout=False)
    assert smap.apply("Stanford Univ.") == "Stanford University"
    assert smap.apply("Stanford U") == "Stanford University"
    assert smap.apply("Stanford University") == "Stanford University"  # canonical maps to self


def test_holdout_terms_map_to_self(monkeypatch):
    counts = Counter({"Stanford University": 5, "ZHAW": 4, "Stanford Univ.": 2})
    emb = np.array([[1.0, 0.0], [0.5, 0.5], [0.98, 0.02]])
    # clusterer would lump everything, but ZHAW is held out so it must stay itself
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    smap = synonym_lustre(counts, emb, eps=0.2, holdout=True)
    assert "ZHAW" not in smap                       # never remapped
    assert smap.apply("Stanford Univ.") == "Stanford University"


def test_authority_split_prevents_merge(monkeypatch):
    counts = Counter({"University of Washington": 6, "Washington University": 5})
    emb = np.array([[1.0, 0.0], [0.99, 0.01]])
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))

    class Auth:
        def split(self, idxs, phrases, emb):
            return [[i] for i in idxs]              # every term its own institution

    smap = synonym_lustre(counts, emb, eps=0.3, holdout=False, authority=Auth())
    assert len(smap) == 0                            # nothing merged
    assert smap.meta["n_authority_splits"] == 1
