"""fairly - authority-aware synonym collapsing for FAIR / DataCite metadata fields.

Public API::

    from fairly import Normalizer, FieldConfig, SynonymMap, get_preset

    cfg = get_preset("affiliation")          # DataCite field preset
    smap = Normalizer(cfg).build(counts, authority=ror_index)
    clean_value = smap.apply("Univ. of California, Berkeley")

See ``fairly.presets`` for the built-in DataCite/FAIR field configurations and
``docs/methods.md`` for the method and recommended settings.
"""
from .config import FieldConfig
from .synonyms import SynonymMap
from .pipeline import Normalizer
from .presets import PRESETS, get_preset

__version__ = "0.1.0"

__all__ = [
    "FieldConfig",
    "SynonymMap",
    "Normalizer",
    "PRESETS",
    "get_preset",
    "__version__",
]
