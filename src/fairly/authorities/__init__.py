"""Authority-based cluster splitting.

An *authority* resolves a surface string to a canonical real-world entity id
(a ROR id for organizations, a geocoded place for locations). We use it to SPLIT
a semantic cluster that the embedding wrongly merged: if two members of one
cluster resolve to two different authority ids, they are pulled back apart before
a canonical is chosen. This is what keeps *University of Washington* and
*Washington University* -- lexically almost identical -- from collapsing.
"""
from .base import Authority
from .ror import RorIndex, RorAuthority, build_ror_index

__all__ = ["Authority", "RorIndex", "RorAuthority", "build_ror_index"]
