"""Sentence-embedding of distinct field terms, with an on-disk cache.

The embedding model (a SentenceTransformer, default ``Alibaba-NLP/gte-large-en-v1.5``)
is an *optional* dependency (``pip install fairly-synonyms[cluster]``) and is imported
lazily, so the rest of the library works without it.

The cache key includes the model id and a cache-version tag as well as the phrase
list, so bumping the model never silently reuses stale vectors.
"""
from __future__ import annotations

import hashlib
import os
from typing import List, Optional, Sequence

import numpy as np

DEFAULT_MODEL = "Alibaba-NLP/gte-large-en-v1.5"
CACHE_VERSION = "1"


def _cache_path(cache_dir: str, phrases: Sequence[str], model_name: str) -> str:
    h = hashlib.sha1()
    h.update(CACHE_VERSION.encode())
    h.update(b"\0")
    h.update(model_name.encode())
    h.update(b"\0")
    h.update("\n".join(phrases).encode("utf-8"))
    return os.path.join(cache_dir, f"emb.{h.hexdigest()[:16]}.npy")


def embed(
    phrases: Sequence[str],
    model_name: str = DEFAULT_MODEL,
    cache_dir: Optional[str] = None,
    batch_size: int = 256,
    show_progress: bool = True,
) -> np.ndarray:
    """Return an ``(n, d)`` array of L2-normalized embeddings for ``phrases``.

    If ``cache_dir`` is given and a matching cache file exists it is loaded;
    otherwise the vectors are computed and written there. Requires the optional
    ``cluster`` extra (sentence-transformers).
    """
    phrases = list(phrases)
    cpath = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cpath = _cache_path(cache_dir, phrases, model_name)
        if os.path.exists(cpath):
            return np.load(cpath)
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "Semantic clustering needs the 'cluster' extra: "
            "pip install fairly-synonyms[cluster]"
        ) from exc
    model = SentenceTransformer(model_name, trust_remote_code=True)
    emb = model.encode(
        phrases,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=show_progress,
        batch_size=batch_size,
    )
    if cpath:
        np.save(cpath, emb)
    return emb
