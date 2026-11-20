"""Embedding and reranking models (local, free, CPU via ONNX/fastembed).

Default embedder: ``paraphrase-multilingual-MiniLM-L12-v2`` (384-d, 50+ languages
including Hebrew, 0.22 GB). Reranker: ``jina-reranker-v2-base-multilingual`` cross
encoder (1.1 GB) - optional because of its size. A deterministic ``HashEmbedder``
exists only for unit tests and CI where downloading models is undesirable; it is
never used to report dense-retrieval benchmark results.
"""
from __future__ import annotations

import hashlib
import threading
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings
from app.services.rag.text import normalize


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedEmbedder:
    def __init__(self, model: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self.name = model
        self._model = TextEmbedding(model_name=model, cache_dir=cache_dir, threads=None)
        self.dim = int(self._model.embedding_size) if hasattr(self._model, "embedding_size") else 384
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            vecs = np.array(list(self._model.embed(texts, batch_size=32)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.maximum(norms, 1e-12)


class HashEmbedder:
    """Character-trigram feature hashing. Test double only (not a semantic model)."""

    def __init__(self, dim: int = 384) -> None:
        self.name, self.dim = f"hash-trigram-{dim}", dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            s = f"  {normalize(t)} "
            for j in range(len(s) - 2):
                h = int(hashlib.md5(s[j:j + 3].encode()).hexdigest()[:8], 16)
                out[i, h % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-12)


class Reranker(Protocol):
    name: str

    def score(self, query: str, docs: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model: str, cache_dir: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = model
        self._model = TextCrossEncoder(model_name=model, cache_dir=cache_dir)
        self._lock = threading.Lock()

    def score(self, query: str, docs: list[str]) -> list[float]:
        with self._lock:
            return [float(s) for s in self._model.rerank(query, docs, batch_size=16)]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend == "hash":
        return HashEmbedder(s.embedding_dim)
    return FastEmbedEmbedder(s.embedding_model, str(s.model_cache_dir))


@lru_cache
def get_reranker() -> Reranker | None:
    s = get_settings()
    if s.reranker_backend == "fastembed":
        return FastEmbedReranker(s.reranker_model, str(s.model_cache_dir))
    return None
