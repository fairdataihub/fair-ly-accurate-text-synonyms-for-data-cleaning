from fairly import cleaners as C
from fairly.presets import MINIMAL_CLEANER, ORG_CLEANER, SUBJECT_CLEANER, TERM_CLEANER


def test_org_keeps_real_entities():
    for name in ["U.S. Environmental Protection Agency", "U.S. Geological Survey",
                 "Guy's and St. Thomas' NHS Foundation Trust", "Ghent University",
                 'University of Campania "Luigi Vanvitelli"', "The IMAGEN Consortium"]:
        assert ORG_CLEANER.clean(name) == name.strip()


def test_org_drops_junk():
    for junk in ["The authors", "This poster", "University", "Haselman et al.",
                 "not specified in the text", "n/a", "University of [Unknown]"]:
        assert ORG_CLEANER.clean(junk) is None


def test_balanced_unwrap_only():
    # fully wrapped -> unwrapped
    assert C._unwrap('"Stanford University"') == "Stanford University"
    # internal trailing quote -> left intact
    assert C._unwrap('University of Campania "Luigi Vanvitelli"') == 'University of Campania "Luigi Vanvitelli"'


def test_preamble_strip():
    assert ORG_CLEANER.clean("The publisher is Stanford University") == "Stanford University"


def test_hedge_word_boundary_keeps_imagen():
    # 'the image' must not match 'the imagen'
    assert C.drop_hedge("The IMAGEN Consortium") == "The IMAGEN Consortium"
    assert C.drop_hedge("the image was unclear") is None


def test_subject_cleaner_is_light():
    assert SUBJECT_CLEANER.clean("Machine Learning") == "Machine Learning"
    assert SUBJECT_CLEANER.clean("AI") == "AI"          # short concept kept
    assert SUBJECT_CLEANER.clean("n/a") is None


def test_fold_possessive():
    assert C.fold_possessive("Alzheimer's disease") == "Alzheimer disease"
    assert C.fold_possessive("Crohn’s disease") == "Crohn disease"
    assert C.fold_possessive("alzheimer ' s disease") == "alzheimer disease"     # tokenized form
    assert C.fold_possessive("Fisher's exact test") == "Fisher exact test"
    assert C.fold_possessive("5'-UTR of the 3' end") == "5'-UTR of the 3' end"   # prime notation kept
    assert C.fold_possessive("Parkinson's") == "Parkinson"
    assert C.fold_possessive("Graves' disease") == "Graves disease"
    assert C.fold_possessive("graves ' disease") == "graves disease"              # tokenized form
    assert C.fold_possessive("Hodgkin's and Graves' disease") == "Hodgkin and Graves disease"
    assert C.fold_possessive("the 'cells' marker") == "the 'cells' marker"        # a quoted word


def test_term_cleaner_folds_but_org_cleaner_keeps_possessives():
    assert TERM_CLEANER.clean("Alzheimer's disease") == "Alzheimer disease"
    assert ORG_CLEANER.clean("King's College London") == "King's College London"


def test_minimal_cleaner():
    assert MINIMAL_CLEANER.clean("  CC-BY 4.0 ") == "CC-BY 4.0"
    assert MINIMAL_CLEANER.clean("123") is None          # no letter
