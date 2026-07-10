from collections import Counter

from fairly.io import collect_counts, iter_values, map_values


def _rec():
    return {
        "publisher": {"name": "Zenodo"},
        "fundingReferences": [{"funderName": "NSF"}, {"funderName": "NIH"}],
        "creators": [
            {"affiliation": [{"name": "Stanford University"}, {"name": "MIT"}]},
            {"affiliation": [{"name": "Stanford Univ."}]},
        ],
        "subjects": [{"subject": "biology"}, {"subject": "genetics"}],
    }


def test_iter_scalar_and_nested_list_paths():
    r = _rec()
    assert list(iter_values(r, "publisher.name")) == ["Zenodo"]
    assert list(iter_values(r, "fundingReferences[].funderName")) == ["NSF", "NIH"]
    assert list(iter_values(r, "creators[].affiliation[].name")) == [
        "Stanford University", "MIT", "Stanford Univ."]


def test_collect_counts():
    c = collect_counts([_rec(), _rec()], "creators[].affiliation[].name")
    assert c == Counter({"Stanford University": 2, "MIT": 2, "Stanford Univ.": 2})


def test_map_scalar_and_list_with_drop():
    r = _rec()
    # canonicalize a nested list leaf, and drop one
    def fn(v):
        if v == "MIT":
            return None            # drop
        return {"Stanford Univ.": "Stanford University"}.get(v, v)
    changed = map_values(r, "creators[].affiliation[].name", fn)
    assert changed
    names = list(iter_values(r, "creators[].affiliation[].name"))
    assert names == ["Stanford University", "Stanford University"]  # MIT dropped, Univ. canonicalized


def test_map_scalar_leaf():
    r = _rec()
    changed = map_values(r, "publisher.name", lambda v: "Figshare" if v == "Zenodo" else v)
    assert changed and r["publisher"]["name"] == "Figshare"
