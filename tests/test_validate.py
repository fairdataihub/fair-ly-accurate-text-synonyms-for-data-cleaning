import numpy as np
import pytest

import fairly.validate as V


def test_load_gold_tsv(tmp_path):
    p = tmp_path / "gold.tsv"
    p.write_text("surface_variant\ttrue_canonical\n"
                 "Stanford Univ.\tStanford University\n"
                 "MIT\tMassachusetts Institute of Technology\n", encoding="utf-8")
    gold = V.load_gold(str(p))
    assert gold == {"Stanford Univ.": "Stanford University",
                    "MIT": "Massachusetts Institute of Technology"}


def test_explode_noise():
    labels = np.array([0, 0, -1, 1, -1])
    out = V._explode_noise(labels)
    assert out[0] == 0 and out[1] == 0 and out[3] == 1
    assert out[2] != out[4] and out[2] >= 2 and out[4] >= 2   # distinct new labels


def test_sweep_perfect_clustering(monkeypatch):
    pytest.importorskip("sklearn")
    gold = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    emb = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    # perfect predicted clustering: {a1,a2}=0, {b1,b2}=1
    monkeypatch.setattr(V, "sweep_eps", V.sweep_eps)  # no-op, keep real fn

    def fake_labels(e, *a, **k):
        return np.array([0, 0, 1, 1])
    import fairly.cluster as cl
    monkeypatch.setattr(cl, "hdbscan_labels", fake_labels)
    rows = V.sweep_eps(gold, eps_list=[0.2], holdout=False, emb=emb)
    assert rows[0]["v_measure"] == pytest.approx(1.0)
    assert V.best_eps(rows)["eps"] == 0.2
