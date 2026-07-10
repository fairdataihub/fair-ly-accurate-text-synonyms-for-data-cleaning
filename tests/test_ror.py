import json

import numpy as np

from fairly.authorities.ror import RorAuthority, RorIndex, build_ror_index, norm


def _dump(path):
    orgs = [
        {"id": "https://ror.org/uw", "names": [
            {"value": "University of Washington", "types": ["ror_display", "label"]},
            {"value": "UW", "types": ["acronym"]},
            {"value": "Washington", "types": ["alias"]}],   # shared alias -> ambiguous
         "locations": [{"geonames_details": {"country_code": "US", "name": "Seattle"}}]},
        {"id": "https://ror.org/wu", "names": [
            {"value": "Washington University in St. Louis", "types": ["ror_display"]},
            {"value": "Washington University", "types": ["label"]},
            {"value": "Washington", "types": ["alias"]}],   # shared alias -> ambiguous
         "locations": [{"geonames_details": {"country_code": "US", "name": "St. Louis"}}]},
    ]
    path.write_text(json.dumps(orgs), encoding="utf-8")
    return str(path)


def test_build_index_resolves_and_drops_ambiguous(tmp_path):
    idx = build_ror_index(_dump(tmp_path / "ror.json"))
    assert idx.resolve("University of Washington") == "https://ror.org/uw"
    assert idx.resolve("washington university") == "https://ror.org/wu"  # norm() lowercases
    assert idx.resolve("Washington") is None                            # ambiguous dropped
    assert idx.display["https://ror.org/uw"] == "University of Washington"


def test_save_load_roundtrip(tmp_path):
    idx = build_ror_index(_dump(tmp_path / "ror.json"))
    p = tmp_path / "idx.pickle"
    idx.save(str(p))
    idx2 = RorIndex.load(str(p))
    assert idx2.resolve("University of Washington") == "https://ror.org/uw"


def test_authority_splits_two_institutions(tmp_path):
    idx = build_ror_index(_dump(tmp_path / "ror.json"))
    auth = RorAuthority(idx)
    phrases = ["University of Washington", "Washington University", "Somewhere Lab"]
    emb = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
    parts = auth.split([0, 1, 2], phrases, emb)
    # UW and WashU resolve to different RORs -> at least 2 groups; the unresolved
    # "Somewhere Lab" joins the nearest centroid.
    assert len(parts) == 2
    flat = sorted(i for p in parts for i in p)
    assert flat == [0, 1, 2]


def test_norm():
    assert norm("Universität Trier") == "universitat trier"
