"""Built-in cleaner and field presets for common DataCite / FAIR metadata fields.

The per-field ``eps`` values are **V-measure validated** against the curated gold
sets in ``gold/`` (see ``docs/methods.md`` for the sweep results): each sits on its
field's optimal V-measure plateau. eps is insensitive when entities are well
separated, so funders/affiliations are kept tight (0.07) to stay safe at real
corpus *density*, where looser thresholds over-merge. Re-run
``fairly validate`` on your own gold set when the corpus or embedding model changes.
"""
from __future__ import annotations

from typing import Dict

from . import cleaners as C
from .cleaners import Cleaner
from .config import FieldConfig
from .licenses import LICENSES

# --- cleaner presets --------------------------------------------------------

#: Organizations / publishers / funders: normalize, strip LLM preambles, drop
#: URLs, placeholders, generic non-entities, hedge phrases and citations. No
#: word-count cap (real institution names can be long).
ORG_CLEANER = Cleaner([
    C.normalize_space, C.strip_preamble, C.drop_url, C.require_min_len(3),
    C.require_letter, C.drop_placeholder, C.drop_generic, C.drop_hedge, C.drop_citation,
])

#: Subjects / keywords: light touch -- keep short concepts, only drop placeholders.
SUBJECT_CLEANER = Cleaner([
    C.normalize_space, C.require_min_len(2), C.require_letter, C.drop_placeholder,
])

#: Minimal: normalize whitespace + require a letter.
MINIMAL_CLEANER = Cleaner([C.normalize_space, C.require_letter])


# --- field presets ----------------------------------------------------------

PRESETS: Dict[str, FieldConfig] = {
    "publisher": FieldConfig(
        name="publisher", strategy="semantic", eps=0.30, holdout=True, authority="ror", identity_guard=True,
        cleaner=ORG_CLEANER,
        description="DataCite publisher: diverse (repos, journals, universities); "
                    "moderate eps, ROR split guards org over-merge."),
    "funderName": FieldConfig(
        name="funderName", strategy="semantic", eps=0.07, holdout=True, authority="ror", identity_guard=True,
        cleaner=ORG_CLEANER,
        description="fundingReferences.funderName: homogeneous 'science funder' language "
                    "prone to cross-country over-merge -- tight eps + ROR split are essential."),
    "affiliation": FieldConfig(
        name="affiliation", strategy="semantic", eps=0.07, holdout=True, authority="ror", identity_guard=True,
        cleaner=ORG_CLEANER,
        description="creators/contributors.affiliation: tight eps, holdout + ROR split "
                    "(University of Washington vs Washington University)."),
    "subject": FieldConfig(
        name="subject", strategy="semantic", eps=0.10, holdout=True, authority=None,
        cleaner=SUBJECT_CLEANER,
        description="subjects.subject: concepts, no authority; hold acronyms out, "
                    "keep eps tight to avoid conflating distinct topics."),
    "rights": FieldConfig(
        name="rights", strategy="controlled", vocab=LICENSES,
        description="rightsList.rights: a CONTROLLED VOCABULARY (SPDX/CC ids). Deterministic "
                    "fold + alias resolution -- never clustered (CC-BY-SA vs CC-BY-NC must stay "
                    "distinct). See fairly.licenses."),
    "geoLocationPlace": FieldConfig(
        name="geoLocationPlace", strategy="geocode",
        description="geoLocations.geoLocationPlace: geocode + group by (country, city) "
                    "-> 'City, Country'. Never embed places -- it conflates nearby cities."),
}

# aliases
PRESETS["subjects"] = PRESETS["subject"]
PRESETS["funder"] = PRESETS["funderName"]
PRESETS["location"] = PRESETS["geoLocationPlace"]


def get_preset(field: str) -> FieldConfig:
    """Return the FieldConfig preset for a DataCite/FAIR field name (KeyError if unknown)."""
    if field not in PRESETS:
        raise KeyError(f"no preset for {field!r}; known: {sorted(PRESETS)}")
    return PRESETS[field]
