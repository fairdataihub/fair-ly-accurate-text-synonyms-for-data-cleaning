from collections import Counter

from fairly import get_preset
from fairly.config import FieldConfig
from fairly.pipeline import Normalizer
from fairly.presets import PRESETS
from fairly.synonyms import SynonymMap


def test_synonymmap_apply_and_roundtrip(tmp_path):
    smap = SynonymMap({"Stanford Univ.": "Stanford University"},
                      {"Stanford University": ["Stanford University", "Stanford Univ."]},
                      field="affiliation")
    assert smap.apply("Stanford Univ.") == "Stanford University"
    assert smap.apply("Unrelated") == "Unrelated"
    assert "Stanford Univ." in smap
    p = tmp_path / "m.pickle"
    smap.save(str(p))
    assert SynonymMap.load(str(p)).apply("Stanford Univ.") == "Stanford University"


def test_review_tsv(tmp_path):
    smap = SynonymMap({"Stanford Univ.": "Stanford University"},
                      {"Stanford University": ["Stanford University", "Stanford Univ."]})
    p = tmp_path / "r.tsv"
    smap.write_review(str(p), Counter({"Stanford University": 10, "Stanford Univ.": 3}))
    text = p.read_text(encoding="utf-8")
    assert "canonical\tfreq\tmerged_variants" in text
    assert "Stanford University\t10\tStanford Univ.(3)" in text


def test_all_presets_valid():
    for name, cfg in PRESETS.items():
        assert isinstance(cfg, FieldConfig)
        assert cfg.strategy in ("semantic", "geocode", "controlled", "cooccur")
        assert cfg.authority in (None, "ror")


def test_pipeline_clean_counts_drops_junk():
    norm = Normalizer(get_preset("publisher"))
    raw = Counter({"Stanford University": 5, "The authors": 3, "  Stanford University ": 1})
    cleaned = norm.clean_counts(raw)
    assert cleaned["Stanford University"] == 6      # whitespace variant folded in
    assert "The authors" not in cleaned             # junk dropped


def test_pipeline_normalize_uses_fallback():
    cfg = get_preset("publisher")
    cfg.fallback = "Zenodo"
    norm = Normalizer(cfg)
    smap = SynonymMap({})
    assert norm.normalize("The authors", smap) == "Zenodo"   # junk -> fallback
    assert norm.normalize("Stanford University", smap) == "Stanford University"


def test_geocode_pipeline_with_injected_resolver():
    cfg = get_preset("geoLocationPlace")
    norm = Normalizer(cfg)
    places = Counter({"Graz, Austria": 3, "graz austria": 2, "Vienna, Austria": 1})
    resolved = {
        "Graz, Austria": {"country": "Austria", "cc": "at", "city": "Graz"},
        "graz austria": {"country": "Austria", "cc": "at", "city": "Graz"},
        "Vienna, Austria": {"country": "Austria", "cc": "at", "city": "Vienna"},
    }
    smap = norm.build(places, resolve=lambda p: resolved.get(p))
    assert smap.apply("graz austria") == "Graz, Austria"
    assert smap.apply("Vienna, Austria") == "Vienna, Austria"   # kept apart from Graz
