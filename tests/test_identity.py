import json
import os
import pickle
import warnings
from collections import Counter

import numpy as np
import pytest

import fairly.cluster as cl
from fairly import Normalizer, get_preset
from fairly.authorities.ror import RorIndex, identity_words_from_dump
from fairly.cluster import synonym_lustre
from fairly.identity import IdentityGuard, changes_identity, identity_guard

PLACES = {"antwerp", "belgium", "stockholm", "sweden", "los", "angeles", "california",
          "berkeley", "san", "diego", "texas", "florida", "ohio", "iowa", "harvard",
          "stanford", "columbia", "washington", "mount", "sinai", "rio", "janeiro",
          "grande", "sul", "paris", "lyon", "chile", "barcelona", "hamburg", "koln",
          "mexico", "oxford", "united", "kingdom", "france", "portugal"}


def test_identity_changing_remaps():
    for variant, canonical in [
        ("Library & Researcher Information Services", "Library"),
        ("University Library", "Library"),
        ("Department of Microbiology, University of California", "Department of Microbiology"),
        ("The Hockaday School", "The Hotchkiss School"),
        ("Eurofins (France)", "Euro-Funding"),
        ("Key Laboratory of Crop Physiology", "Kay Laboratory of Crop Physiology"),
        ("Wroclaw University", "Wroclaw University of Economics and Business"),
        ("University of California, Berkeley", "University of California, Los Angeles"),
        ("UC San Diego", "University of California"),
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
        ("KTH Royal Institute of Technology, Stockholm, Sweden", "KTH Royal Institute of Technology"),
        ("U.S. Environmental Protection Agency", "Environmental Protection Agency"),
        ("University of Oxford, Oxford, United Kingdom", "University of Oxford"),
    ]:
        assert not changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_place_words_are_never_swapped():
    for variant, canonical in [
        ("Harvard University", "Stanford University"),
        ("Ohio State University", "Iowa State University"),
        ("Department of Microbiology, University of Texas",
         "Department of Microbiology, University of Florida"),
        ("Universidade Federal do Rio de Janeiro", "Universidade Federal do Rio Grande do Sul"),
        ("Siemens (France)", "Siemens (Portugal)"),             # a place in parentheses counts
    ]:
        assert changes_identity(variant, canonical, PLACES), (variant, canonical)
    assert not changes_identity("Siemens (France)", "Siemens", PLACES)   # dropping is fine


def test_never_reduce_to_generic_words():
    for variant, canonical in [
        ("Columbia University", "University"),
        ("University of Washington", "University"),
        ("Mount Sinai Hospital", "Hospital"),
        ("National Institutes of Health", "Institutes of Health"),
        ("Ohio State University", "State University"),
        ("University", "Columbia University"),
    ]:
        assert changes_identity(variant, canonical, PLACES), (variant, canonical)
    # data-derived generic words add to the built-in list
    assert not changes_identity("Springfield Widget Works", "Widget Works", {"springfield"})
    assert changes_identity("Springfield Widget Works", "Widget Works", {"springfield"},
                            {"widget", "works"})


def test_stopwords_and_short_words_are_not_abbreviations():
    for variant, canonical in [
        ("Department of Theoretical Physics", "The Department of Physics"),
        ("Forest Research Institute", "Institute for Research"),
        ("Structural Biology Unit", "Biology Unit, Str. 5"),
        ("Institute of Art", "Institute of Arthritis"),
        ("Gene Center", "General Center"),
        ("Department of Biochemistry", "Department of Bio"),
    ]:
        assert changes_identity(variant, canonical), (variant, canonical)
    for variant, canonical in [
        ("Univ Calif San Diego", "University of California San Diego"),
        ("Harvard Med. Sch.", "Harvard Medical School"),
        ("Lab of Y", "Laboratory of Y"),
        ("Dept. of Sci.", "Department of Science"),
    ]:
        assert not changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_numbers_letters_and_parentheses():
    for variant, canonical in [
        ("Universite Paris 1", "Universite Paris 8"),
        ("Universite Lyon 1", "Universite Lyon 2"),
        ("Hospital A", "Hospital B"),
        ("Universidad de Chile (Facultad de Medicina)", "Universidad de Chile (Facultad de Ingenieria)"),
    ]:
        assert changes_identity(variant, canonical, PLACES), (variant, canonical)
    for variant, canonical in [
        ("Universite Paris 1", "Universite Paris"),                 # a number may be dropped
        ("Zenodo", "Zenodo (CERN)"),                                # single-token acronym
        ("Universidad Nacional Autonoma de Mexico (U.N.A.M.)",
         "Universidad Nacional Autonoma de Mexico"),                # matches the initials
    ]:
        assert not changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_harmless_spelling_variants():
    for variant, canonical in [
        ("Centre for X", "Center for X"),
        ("Universitaet Hamburg", "Universitat Hamburg"),
        ("Universitat de Barcelona", "University of Barcelona"),
        ("Universitat zu Koln", "Universitat Koln"),
        ("Siemens AG", "Siemens"),
        ("Pfizer Ltd", "Pfizer Limited"),
        ("Institute of Mathematics", "Mathematical Institute"),
        ("Faculty of Medicine", "Medical Faculty"),
        ("Biology Department", "Biological Department"),
        ("Instituto de Fisica", "Institute of Physics"),
    ]:
        assert not changes_identity(variant, canonical, PLACES), (variant, canonical)


def test_guard_matches_function_and_batches():
    guard = identity_guard(PLACES)
    assert isinstance(guard, IdentityGuard)
    pairs = [("Gene Center", "General Center"), ("Univ. Hamburg", "Universitat Hamburg"),
             ("Hospital A", "Hospital B"), ("Centre for X", "Center for X")]
    for v, c in pairs:
        assert guard(v, c) == changes_identity(v, c, PLACES)
        assert guard(v, c) == guard(v, c)                          # cached
    variants = [v for v, _ in pairs] + ["General Center"]
    assert guard.blocked(variants, "General Center") == [guard(v, "General Center") for v in variants]


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


def test_large_blocking_cluster_is_fast(monkeypatch):
    import time
    words = [f"{a}{b}{c}" for a in "bdfgk" for b in "aeiou" for c in "lmnprst"]
    terms = [f"Institute of {w} {v}" for w in words[:40] for v in words[40:80]]   # 1,600 names
    counts = {t: 1 + i % 7 for i, t in enumerate(terms)}
    emb = np.random.default_rng(0).normal(size=(len(terms), 16))
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    t = time.time()
    smap = synonym_lustre(counts, emb, 0.1, holdout=False, identity_guard=identity_guard())
    assert smap.meta["n_guarded"] == len(terms) - 1
    assert time.time() - t < 10


def _dump(path):
    def org(i, name, city, country="Belgium"):
        return {"id": f"https://ror.org/{i}", "status": "active",
                "names": [{"value": name, "types": ["ror_display"]}],
                "locations": [{"geonames_details": {"name": city, "country_name": country}}]}
    orgs = [org("a", "University of Antwerp", "Antwerp"),
            org("b", "Antwerp Zoo", "Antwerp"),
            org("c", "Harvard University", "Cambridge", "United States"),
            org("d", "Harvard Medical School", "Boston", "United States"),
            org("e", "Harvard Clinic", "Harvard", "United States"),
            org("f", "Harvard Library", "Cambridge", "United States")]
    orgs += [org(f"u{i}", f"Example University {i}", "Ghent") for i in range(20)]
    path.write_text(json.dumps(orgs), encoding="utf-8")
    return str(path)


def test_identity_words_from_dump(tmp_path):
    place, generic = identity_words_from_dump(_dump(tmp_path / "ror.json"), generic_share=0.5)
    assert {"antwerp", "belgium", "ghent", "cambridge"} <= place
    assert "harvard" not in place            # in four names, located in Harvard once
    assert generic == {"example", "university"}


def test_old_pickle_loads_without_word_sets(tmp_path):
    path = tmp_path / "old.pickle"
    with open(path, "wb") as fh:
        pickle.dump({"name2ror": {}, "display": {}, "loc": {}}, fh)
    idx = RorIndex.load(str(path))
    assert idx.place_words == frozenset() and idx.generic_words == frozenset()


def _normalizer_build(cfg, monkeypatch, **kw):
    counts = {"University of Antwerp": 5, "University of Antwerp, Antwerp, Belgium": 2}
    emb = np.array([[1.0, 0.0], [0.99, 0.01]])
    monkeypatch.setattr(cl, "hdbscan_labels", lambda e, *a, **k: np.zeros(len(e), dtype=int))
    return Normalizer(cfg).build(counts, emb=emb, **kw)


def test_warns_when_guard_has_no_place_words(monkeypatch):
    with pytest.warns(UserWarning, match="without place words"):
        smap = _normalizer_build(get_preset("affiliation"), monkeypatch)
    assert smap.apply("University of Antwerp, Antwerp, Belgium") == \
        "University of Antwerp, Antwerp, Belgium"                  # stricter: no merge
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        smap = _normalizer_build(get_preset("affiliation"), monkeypatch, place_words=PLACES)
    assert smap.apply("University of Antwerp, Antwerp, Belgium") == "University of Antwerp"


def test_warns_when_place_words_are_ignored(monkeypatch):
    with pytest.warns(UserWarning, match="identity guard is off"):
        _normalizer_build(get_preset("subject"), monkeypatch, place_words=PLACES)


@pytest.mark.skipif(not os.environ.get("FAIRLY_ROR_INDEX"),
                    reason="set FAIRLY_ROR_INDEX to a RorIndex pickle built from a real ROR dump")
def test_real_ror_index():
    idx = RorIndex.load(os.environ["FAIRLY_ROR_INDEX"])
    guard = identity_guard(idx.place_words, idx.generic_words)
    for variant, canonical in [
        ("Harvard University", "Stanford University"),
        ("Ohio State University", "Iowa State University"),
        ("Universite Paris 1", "Universite Paris 8"),
        ("Columbia University", "University"),
        ("Rice", "Emory University"),
    ]:
        assert guard(variant, canonical), (variant, canonical)
    for variant, canonical in [
        ("University of Antwerp, Antwerp, Belgium", "University of Antwerp"),
        ("KTH Royal Institute of Technology, Stockholm, Sweden", "KTH Royal Institute of Technology"),
    ]:
        assert not guard(variant, canonical), (variant, canonical)


def test_country_words_that_fold_to_generic_words_stay_places():
    # "States" folds to the generic "state"; as a word of "United States" it is a place
    place = frozenset({"united", "states", "kingdom", "ohio", "iowa"})
    assert not changes_identity("Harvard University, United States", "Harvard University", place)
    assert not changes_identity("ADNET Systems Inc.", "Adnet Systems (United States)", place)
    assert changes_identity("Ohio State University", "Iowa State University", place)
    assert changes_identity("Ohio State University", "Ohio University", place)


def test_spacing_punctuation_and_case_only_is_the_same_name():
    assert not changes_identity("PolitecnicodiTorino", "Politecnico di Torino")
    assert not changes_identity("ETH-Zürich", "ETH Zurich")
    g = identity_guard()
    assert not g("DigitalHumanities Lab", "Digital Humanities Lab")
    assert g.blocked(["DigitalHumanities Lab", "Digital Sciences Lab"], "Digital Humanities Lab") == [False, True]
