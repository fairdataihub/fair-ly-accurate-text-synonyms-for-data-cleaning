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

from typing import Optional

from .controlled import ControlledVocabulary

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


def classify(value, allowed=ALLOWED, blocked=BLOCKED) -> str:
    """Classify a license value (string or list of strings/dicts) as
    ``'allowed'`` / ``'blocked'`` / ``'unknown'``.

    Any single allowed entry wins (dual licensing). ``unknown`` means empty or
    unresolved -- callers typically treat it as blocked (default-deny).
    """
    if not value:
        return "blocked"
    entries = value if isinstance(value, list) else [value]
    has_blocked = False
    for e in entries:
        if isinstance(e, dict):
            e = e.get("rightsIdentifier") or e.get("rights") or ""
        canon = LICENSES.normalize(e)
        if canon is None:
            continue
        if canon in allowed:
            return "allowed"
        if canon in blocked:
            has_blocked = True
    return "blocked" if has_blocked else "unknown"
