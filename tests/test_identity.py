from collections import Counter

import numpy as np

import fairly.cluster as cl
from fairly.cluster import synonym_lustre
from fairly.identity import changes_identity, identity_guard

PLACES = {"antwerp", "belgium", "stockholm", "sweden", "los", "angeles", "california"}


def test_identity_changing_remaps():
    for variant, canonical in [
        ("Library & Researcher Information Services", "Library"),
        ("University Library", "Library"),
        ("Department of Microbiology, University of California", "Department of Microbiology"),
        ("The Hockaday School", "The Hotchkiss School"),
        ("Eurofins (France)", "Euro-Funding"),
        ("Key Laboratory of Crop Physiology", "Kay Laboratory of Crop Physiology"),
        ("Wroclaw University", "Wroclaw University of Economics and Business"),
    ]:
        assert changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_same_entity_remaps():
    for variant, canonical in [
        ("University of Antwerp, Antwerp, Belgium", "University of Antwerp"),
        ("University of Heidelberg", "Heidelberg University"),
        ("The University of Manchester", "University of Manchester"),
        ("University of California, Los Angeles (UCLA)", "University of California, Los Angeles"),
        ("Wageningen University and Research", "Wageningen University & Research"),
        ("Stanford Univ.", "Stanford University"),
        ("Dept. of Physics, Example Inst.", "Department of Physics, Example Institute"),
        ("University Libraries", "University Library"),
        ("Example GmbH, Musterstrasse 12, 10115", "Example GmbH"),
    ]:
        assert not changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_guarded_cluster_keeps_specific_names(monkeypatch):
    counts = Counter({"Library": 50, "Library & Researcher Information Services": 3,
                      "University Library": 10, "University Libraries": 4, "Library.": 2})
    emb = np.array([[1.0, 0.0], [0.9, 0.1], [0.95, 0.05], [0.94, 0.06], [0.99, 0.01]])
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    smap = synonym_lustre(counts, emb, eps=0.3, holdout=False, identity_guard=identity_guard())
    assert smap.apply("Library.") == "Library"                               # true variant merges
    assert smap.apply("Library & Researcher Information Services") == \
        "Library & Researcher Information Services"                         # never absorbed
    assert smap.apply("University Libraries") == "University Library"       # its own sub-group
    assert smap.meta["n_guarded"] == 3


def test_unguarded_cluster_is_unchanged(monkeypatch):
    counts = Counter({"Library": 50, "University Library": 10})
    emb = np.array([[1.0, 0.0], [0.95, 0.05]])
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    smap = synonym_lustre(counts, emb, eps=0.3, holdout=False)
    assert smap.apply("University Library") == "Library"
