"""The Authority protocol used to split semantic clusters."""
from __future__ import annotations

from typing import List, Protocol, Sequence

import numpy as np


class Authority(Protocol):
    """Splits a cluster of term indices into per-entity sub-clusters.

    ``split`` receives the indices of one semantic cluster, the full phrase list,
    and the full embedding matrix (for assigning unresolved members to the nearest
    resolved sub-group). It returns a list of index-lists: one per distinct
    authority entity. A cluster that resolves to at most one entity is returned
    intact (``[idxs]``).
    """

    def split(
        self, idxs: Sequence[int], phrases: Sequence[str], emb: np.ndarray
    ) -> List[List[int]]:
        ...
