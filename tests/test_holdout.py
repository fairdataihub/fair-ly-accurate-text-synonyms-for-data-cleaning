from fairly.holdout import clusterable_indices, is_holdout


def test_short_and_acronyms_held_out():
    assert is_holdout("ZHAW")          # all-caps single token
    assert is_holdout("UK")            # short
    assert is_holdout("GTC")
    assert is_holdout("MIDAS")         # all-caps acronym, len >= 4
    assert is_holdout("e")             # single char


def test_real_names_clusterable():
    assert not is_holdout("Ghent University")   # multi-word
    assert not is_holdout("Zenodo")             # mixed case, len >= 4
    assert not is_holdout("arXiv")


def test_clusterable_indices_masks_holdouts():
    phrases = ["Ghent University", "ZHAW", "Stanford University", "UK"]
    assert clusterable_indices(phrases) == [0, 2]
