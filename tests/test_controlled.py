from collections import Counter

from fairly import ControlledVocabulary, Normalizer, get_preset
from fairly.controlled import fold_key
from fairly.licenses import LICENSES, classify


def test_fold_key():
    assert fold_key("CC BY 4.0") == "ccby40"
    assert fold_key("cc-by-4.0") == "ccby40"
    assert fold_key("CC_BY_4.0") == "ccby40"
    assert fold_key("Zürich") == "zurich"          # diacritics folded


def test_license_vocab_normalizes_variants():
    for v in ["CC-BY-4.0", "CC BY 4.0", "cc-by-4.0", "CC_BY_4.0"]:
        assert LICENSES.normalize(v) == "CC-BY-4.0"
    assert LICENSES.normalize("CC0") == "CC0-1.0"
    assert LICENSES.normalize("cc-by") == "CC-BY-4.0"          # version-less alias
    assert LICENSES.normalize("Apache 2.0") == "Apache-2.0"
    assert LICENSES.normalize("cc-by-3.0-us") == "CC-BY-3.0"   # region strip
    assert LICENSES.normalize("Totally Made Up") is None


def test_controlled_keeps_distinct_ids():
    # the whole point vs clustering: near-identical strings stay distinct
    assert LICENSES.normalize("CC-BY-SA-4.0") == "CC-BY-SA-4.0"
    assert LICENSES.normalize("CC-BY-NC-4.0") == "CC-BY-NC-4.0"
    assert LICENSES.normalize("CC BY SA 4.0") != LICENSES.normalize("CC BY NC 4.0")


def test_classify():
    for lic in ["CC BY 4.0", "CC0", "cc-by", "Apache 2.0", "mit-license", "other-open"]:
        assert classify(lic) == "allowed", lic
    for lic in ["CC-BY-ND-4.0", "CC BY-NC-ND 4.0", "In Copyright", "All Rights Reserved"]:
        assert classify(lic) == "blocked", lic
    assert classify(None) == "blocked"
    assert classify("mystery license") == "unknown"
    assert classify([{"rights": "In Copyright"}, {"rights": "CC BY 4.0"}]) == "allowed"  # dual


def test_custom_controlled_vocab():
    vocab = ControlledVocabulary(["US", "GB", "DE"], aliases={"USA": "US", "United States": "US",
                                                              "UK": "GB", "Germany": "DE"})
    assert vocab.normalize("u.s.a.") == "US"
    assert vocab.normalize("united  states") == "US"
    assert vocab.normalize("Germany") == "DE"
    assert vocab.normalize("Mars") is None


def test_rights_preset_uses_controlled_strategy():
    cfg = get_preset("rights")
    assert cfg.strategy == "controlled" and cfg.vocab is LICENSES
    smap = Normalizer(cfg).build(Counter({"CC BY 4.0": 5, "cc-by-4.0": 3, "CC-BY-SA-4.0": 2}))
    assert smap.apply("CC BY 4.0") == "CC-BY-4.0"
    assert smap.apply("cc-by-4.0") == "CC-BY-4.0"
    assert smap.apply("CC-BY-SA-4.0") == "CC-BY-SA-4.0"        # distinct, unchanged
