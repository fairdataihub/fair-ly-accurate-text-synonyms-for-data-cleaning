from collections import Counter

from fairly.acronyms import acronym_map, best_long_form, count_definitions, definitions
from fairly.presets import TERM_CLEANER

ABSTRACT = ("Ibrutinib, a Bruton tyrosine kinase (BTK) inhibitor, is approved for chronic lymphocytic "
            "leukemia (CLL). Continuous positive airway pressure (CPAP) treats obstructive sleep apnea "
            "(OSA). Patients (n = 42) were followed (see Table 1). Tumor necrosis factor-alpha "
            "(TNF-alpha) rose.")


def test_definitions_in_an_abstract():
    got = dict(definitions(ABSTRACT))
    assert got["BTK"] == "Bruton tyrosine kinase"
    assert got["CLL"] == "chronic lymphocytic leukemia"
    assert got["CPAP"] == "Continuous positive airway pressure"
    assert got["OSA"] == "obstructive sleep apnea"
    assert got["TNF-alpha"] == "Tumor necrosis factor-alpha"
    assert "n = 42" not in got and "see Table 1" not in got


def test_best_long_form():
    assert best_long_form("PCR", "using the polymerase chain reaction") == "polymerase chain reaction"
    assert best_long_form("XYZ", "was measured in the cohort") is None


def test_count_definitions_counts_texts_once():
    c = count_definitions([ABSTRACT, ABSTRACT + " Bruton tyrosine kinase (BTK) again.", None, "no parens"])
    assert c[("BTK", "Bruton tyrosine kinase")] == 2


def test_spelling_variants_count_together():
    defs = Counter({("BTK", "Bruton tyrosine kinase"): 40, ("BTK", "Bruton's tyrosine kinase"): 35,
                    ("BTK", "Brutons tyrosine kinase"): 5, ("BTK", "B-cell receptor kinase"): 20})
    amap = acronym_map(defs)        # 80 of 100 once the three spellings are one group
    assert amap.apply("BTK") == "Bruton tyrosine kinase"
    assert amap.apply("Bruton's tyrosine kinase") == "Bruton tyrosine kinase"
    assert amap.apply("B-cell receptor kinase") == "B-cell receptor kinase"
    defs = Counter({("CLL", "chronic lymphocytic leukemias"): 30, ("CLL", "Chronic lymphocytic leukemia"): 50,
                    ("CLL", "chronic lymphocytic leukaemia"): 10})
    amap = acronym_map(defs)
    assert amap.apply("CLL") == "Chronic lymphocytic leukemia"
    assert amap.apply("chronic lymphocytic leukemias") == "Chronic lymphocytic leukemia"
    assert "chronic lymphocytic leukaemia" not in amap        # spelling variants are the semantic pass's job


def test_ambiguous_acronym_left_alone():
    defs = Counter({("AMP", "adenosine monophosphate"): 1400, ("AMP", "antimicrobial peptide"): 948,
                    ("AMP", "ampicillin"): 600, ("AMP", "amplitude"): 500})
    amap = acronym_map(defs)
    assert "AMP" not in amap and amap.meta["n_ambiguous"] == 1


def test_coverage_keeps_a_common_word():
    defs = Counter({("fish", "fluorescence in situ hybridization"): 300})
    assert "fish" not in acronym_map(defs, counts={"fish": 20000})          # the animal
    assert acronym_map(defs, counts={"fish": 900}).apply("fish") == "fluorescence in situ hybridization"


def test_authority_conflict_and_min_texts():
    defs = Counter({("ADP", "adenosine diphosphate"): 50, ("XQ", "x-ray quantum"): 2})
    ids = {"ADP": "D000244", "adenosine diphosphate": "D000244"}.get
    assert acronym_map(defs, identity_of=ids).apply("ADP") == "adenosine diphosphate"
    other = {"ADP": "D000244", "adenosine diphosphate": "D999999"}.get
    assert "ADP" not in acronym_map(defs, identity_of=other)
    assert "XQ" not in acronym_map(defs)                                    # 2 texts < min_texts


def test_clean_folds_possessives_first():
    defs = Counter({("AD", "Alzheimer's disease"): 60, ("AD", "Alzheimer disease"): 30,
                    ("AD", "atopic dermatitis"): 25})
    amap = acronym_map(defs, clean=TERM_CLEANER)
    assert amap.apply("AD") == "Alzheimer disease"


def test_authority_ids_split_groups_before_the_share():
    # two guard-compatible spellings that an authority says are different things
    defs = Counter({("ACE", "angiotensin converting enzyme"): 40, ("ACE", "angiotensin-converting enzymes"): 35,
                    ("ACE", "acetylcholinesterase"): 25})
    ids = {"angiotensin converting enzyme": "D1", "angiotensin-converting enzymes": "D2"}.get
    amap = acronym_map(defs, identity_of=ids)      # 40% and 35%: neither dominates once split
    assert "ACE" not in amap and amap.meta["n_ambiguous"] == 1
    assert acronym_map(defs).apply("ACE") == "angiotensin converting enzyme"     # 75% as one group


def test_counts_keys_match_ignoring_case():
    defs = Counter({("BTK", "Bruton tyrosine kinase"): 50})
    amap = acronym_map(defs, counts={"btk": 120, "Bruton tyrosine kinase": 300})
    assert amap.apply("btk") == "Bruton tyrosine kinase"
    assert acronym_map(defs, counts={"btk": 1000}).meta["n_uncovered"] == 1        # 50 < 10% of 1000


def test_rare_definitions_still_count_toward_the_share():
    defs = Counter({("XY", "alpha one"): 5, ("XY", "beta two"): 2, ("XY", "gamma three"): 2})
    assert "XY" not in acronym_map(defs)                  # 5 of 9 < 60%, the rare meanings count
    defs = Counter({("BTK", "Bruton tyrosine kinase"): 2, ("BTK", "Bruton's tyrosine kinase"): 2})
    assert acronym_map(defs).apply("BTK") == "Bruton tyrosine kinase"   # 4 texts as one group >= min_texts
    assert acronym_map(Counter({("XQ", "x-ray quantum"): 2})).meta["n_rare"] == 1


def test_review_clusters_merge_acronyms_with_one_long_form():
    defs = Counter({("BTK", "Bruton tyrosine kinase"): 50, ("BTKI", "Bruton tyrosine kinase"): 20})
    amap = acronym_map(defs)
    assert amap.apply("BTKI") == amap.apply("BTK") == "Bruton tyrosine kinase"
    assert set(amap.clusters["Bruton tyrosine kinase"]) == {"Bruton tyrosine kinase", "BTK", "BTKI"}
