"""License / rights normalization -- a worked controlled-vocabulary example.

Ships a :class:`fairly.controlled.ControlledVocabulary` over SPDX / Creative Commons
license ids, plus a redistribution-permission classifier. This is the canonical use
case for controlled-vocabulary normalization (see ``fairly.controlled``): the same
license shows up as ``CC-BY-4.0``, ``CC BY 4.0``, ``cc-by-4.0``, ``cc-by``, and they
must all resolve to one id -- while ``CC-BY-SA-4.0`` and ``CC-BY-NC-4.0`` must stay
distinct, which embedding clustering cannot guarantee.

    from fairly.licenses import LICENSES, classify
    LICENSES.normalize("CC BY 4.0")        # -> "CC-BY-4.0"
    classify("cc-by")                       # -> "allowed"
    classify("CC-BY-NC-ND-4.0")             # -> "blocked"

The allowed/blocked split here is one reasonable policy (does the license permit
redistributing derivative works); override it for your own policy.
"""
from __future__ import annotations

import re
from typing import Optional

from .controlled import ControlledVocabulary, fold_key

# derivatives / redistribution permitted
ALLOWED = frozenset({
    "CC0-1.0",
    "CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.5", "CC-BY-2.0", "CC-BY-1.0",
    "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-SA-2.5", "CC-BY-SA-2.0", "CC-BY-SA-1.0",
    "CC-BY-NC-4.0", "CC-BY-NC-3.0", "CC-BY-NC-2.5", "CC-BY-NC-2.0", "CC-BY-NC-1.0",
    "CC-BY-NC-SA-4.0", "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-2.5", "CC-BY-NC-SA-2.0", "CC-BY-NC-SA-1.0",
    "MIT", "Apache-2.0", "GPL-3.0", "GPL-2.0", "LGPL-3.0", "LGPL-2.1",
    "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "ISC", "Unlicense",
    "other-open", "other-pd",
})

# no-derivatives / restrictive / undetermined
BLOCKED = frozenset({
    "CC-BY-ND-4.0", "CC-BY-ND-3.0", "CC-BY-ND-2.5", "CC-BY-ND-2.0", "CC-BY-ND-1.0",
    "CC-BY-NC-ND-4.0", "CC-BY-NC-ND-3.0", "CC-BY-NC-ND-2.5", "CC-BY-NC-ND-2.0", "CC-BY-NC-ND-1.0",
    "In Copyright", "All Rights Reserved", "Copyright not evaluated", "Copyright undetermined",
    "other-at", "other-closed", "other-nc", "other",
})

# vernacular / version-less / alternate spellings not reachable by folding a canonical
ALIASES = {
    "cc0": "CC0-1.0", "cczero": "CC0-1.0", "creativecommonszero": "CC0-1.0",
    "publicdomain": "other-pd", "pd": "other-pd",
    "ccby": "CC-BY-4.0", "ccbysa": "CC-BY-SA-4.0", "ccbync": "CC-BY-NC-4.0",
    "ccbyncsa": "CC-BY-NC-SA-4.0", "ccbynd": "CC-BY-ND-4.0", "ccbyncnd": "CC-BY-NC-ND-4.0",
    "apache2": "Apache-2.0", "apachelicense20": "Apache-2.0", "asl20": "Apache-2.0",
    "gpl": "GPL-3.0", "gpl3": "GPL-3.0", "gplv3": "GPL-3.0",
    "gpl3orlater": "GPL-3.0", "gpl30orlater": "GPL-3.0", "gplv3orlater": "GPL-3.0",
    "gpl2": "GPL-2.0", "gplv2": "GPL-2.0", "lgpl3": "LGPL-3.0", "lgplv3": "LGPL-3.0",
    "mitlicense": "MIT", "bsd": "BSD-3-Clause", "bsd3": "BSD-3-Clause", "bsd2": "BSD-2-Clause",
    "allrightsreserved": "In Copyright", "copyright": "In Copyright",
}

#: A ControlledVocabulary over all known license ids.
LICENSES = ControlledVocabulary(list(ALLOWED) + list(BLOCKED), ALIASES)

_CC_URI_RE = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z0-9-]+)(?:/(\d\.\d))?", re.I)
_CC_VER_RE = re.compile(r"(\d)(\d)")


def _cc_from_display(k):
    """Canonical CC id from a folded spelled-out name, e.g.
    'creativecommonsattributionnoncommercial40international' -> 'CC-BY-NC-4.0'.
    Handles the jurisdiction-named forms repositories emit ('... 3.0 Germany')."""
    if "creativecommons" not in k:
        return None
    if "zero" in k:
        return "CC0-1.0"
    if "attribution" not in k:
        return None
    elems = ["BY"]
    if "noncommercial" in k:
        elems.append("NC")
    if "noderiv" in k:                       # noderiv / noderivs / noderivatives
        elems.append("ND")
    if "sharealike" in k:
        elems.append("SA")
    m = _CC_VER_RE.search(k)
    ver = f"{m.group(1)}.{m.group(2)}" if m else "4.0"
    return "CC-" + "-".join(elems) + "-" + ver


def _license_from_uri(uri):
    """Canonical license id from a creativecommons.org rightsUri, or None. The URI
    path is the most reliable license signal a DataCite deposit carries (many drop
    rightsIdentifier and give only a jurisdiction-named display string + URI)."""
    if not isinstance(uri, str):
        return None
    m = _CC_URI_RE.search(uri)
    if not m:
        return None
    kind, code, ver = m.group(1).lower(), m.group(2).lower(), m.group(3) or "4.0"
    if kind == "publicdomain":
        return "CC0-1.0" if code in ("zero", "cc0") else "other-pd"
    elems = [e for e in code.split("-") if e in ("by", "nc", "nd", "sa")]
    if "by" not in elems:
        return None
    return "CC-" + "-".join(e.upper() for e in elems) + "-" + ver


def normalize(value) -> Optional[str]:
    """License-aware normalize: the controlled-vocabulary lookup, then a
    spelled-out Creative Commons name parser (``Creative Commons Attribution 3.0
    Germany`` -> ``CC-BY-3.0``)."""
    canon = LICENSES.normalize(value)
    if canon is not None:
        return canon
    if isinstance(value, str):
        return _cc_from_display(fold_key(value))
    return None


def classify(value, allowed=ALLOWED, blocked=BLOCKED) -> str:
    """Classify a license value (string or list of strings/dicts) as
    ``'allowed'`` / ``'blocked'`` / ``'unknown'``.

    Any single allowed entry wins (dual licensing). ``unknown`` means empty or
    unresolved -- callers typically treat it as blocked (default-deny). Dict
    entries are read from ``rightsIdentifier``, then ``rights``, then
    ``rightsUri`` (a creativecommons.org URL, the most reliable signal)."""
    if not value:
        return "blocked"
    entries = value if isinstance(value, list) else [value]
    has_blocked = False
    for e in entries:
        if isinstance(e, dict):
            canon = (normalize(e.get("rightsIdentifier") or "")
                     or normalize(e.get("rights") or "")
                     or _license_from_uri(e.get("rightsUri") or ""))
        else:
            canon = normalize(e)
        if canon is None:
            continue
        if canon in allowed:
            return "allowed"
        if canon in blocked:
            has_blocked = True
    return "blocked" if has_blocked else "unknown"
