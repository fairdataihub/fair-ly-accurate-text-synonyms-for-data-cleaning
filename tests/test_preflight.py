"""Preflight separability check.

Uses synthetic unit vectors with hand-placed angles so the expected verdict is
arithmetic, not a property of any embedding model.
"""
import numpy as np
import pytest

from fairly.preflight import analyse, format_report


def _unit(*angles_deg):
    """Points on the unit circle: cosine distance between them is exactly known."""
    a = np.radians(np.asarray(angles_deg, dtype=np.float64))
    return np.stack([np.cos(a), np.sin(a)], axis=1).astype(np.float32)


def test_separable_when_groups_are_tight_and_far_apart():
    # Two groups, each pair 5 degrees apart internally, 60 degrees between.
    emb = _unit(0, 5, 60, 65)
    res = analyse(["a1", "a2", "b1", "b2"], ["A", "A", "B", "B"], emb)
    assert res["separable"] is True
    assert res["within"] < res["between"]
    lo, hi = res["eps_window"]
    assert lo < hi
    assert "SEPARABLE" in format_report(res)


def test_not_separable_when_a_must_merge_pair_is_wider_than_a_must_split_pair():
    # A spans 80 degrees internally; A and B are only 10 degrees apart at closest.
    # Any threshold big enough to join A also fuses A with B.
    emb = _unit(0, 80, 90, 95)
    res = analyse(["a1", "a2", "b1", "b2"], ["A", "A", "B", "B"], emb)
    assert res["separable"] is False
    assert res["margin"] < 0
    rep = format_report(res)
    assert "NOT SEPARABLE" in rep
    # The report must name the offending pairs; that is the actionable part.
    assert "a1" in rep and "a2" in rep


def test_reports_the_actual_offending_pairs():
    emb = _unit(0, 80, 90, 95)
    res = analyse(["a1", "a2", "b1", "b2"], ["A", "A", "B", "B"], emb)
    assert {res["worst_within"]["a"], res["worst_within"]["b"]} == {"a1", "a2"}
    assert {res["worst_between"]["a"], res["worst_between"]["b"]} == {"a2", "b1"}


def test_holdout_terms_are_excluded():
    # b1 sits inside A's span and would make the set inseparable, but it is held
    # out, so no threshold is ever applied to it and it must not count.
    emb = _unit(0, 5, 2, 90)
    terms = ["a1", "a2", "b1", "b2"]
    labels = ["A", "A", "B", "B"]
    assert analyse(terms, labels, emb)["separable"] is False
    res = analyse(terms, labels, emb, holdout_mask=[False, False, True, False])
    assert res["separable"] is True
    assert res["n_terms"] == 3


def test_inconclusive_when_nothing_has_to_merge():
    emb = _unit(0, 90)
    res = analyse(["a", "b"], ["A", "B"], emb)
    assert res["separable"] is None
    assert "two members" in res["reason"]


def test_inconclusive_when_only_one_group():
    emb = _unit(0, 10)
    res = analyse(["a1", "a2"], ["A", "A"], emb)
    assert res["separable"] is None
    assert "one true group" in res["reason"]


def test_thin_margin_is_flagged_even_though_separable():
    # Within 10 degrees, between 12 degrees: technically separable, barely.
    emb = _unit(0, 10, 22, 30)
    res = analyse(["a1", "a2", "b1", "b2"], ["A", "A", "B", "B"], emb)
    assert res["separable"] is True
    assert res["margin"] < 0.05
    assert "thin" in format_report(res).lower()


@pytest.mark.parametrize("n", [2, 3, 8])
def test_scales_without_error(n):
    ang = []
    labels = []
    for g in range(n):
        base = g * (360 / n)
        ang += [base, base + 3]
        labels += [f"G{g}", f"G{g}"]
    res = analyse([f"t{i}" for i in range(2 * n)], labels, _unit(*ang))
    assert res["n_groups"] == n
