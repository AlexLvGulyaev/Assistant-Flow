"""Retrieval abstraction layer (P6.1)."""

from __future__ import annotations

from services.retrieval.base import (
    RetrievalBackend,
    RetrievalChunk,
    RetrievalHealth,
    RetrievalSearchResult,
)
from services.retrieval.factory import build_retrieval_backend, normalize_rag_backend

__all__ = [
    "RetrievalBackend",
    "RetrievalChunk",
    "RetrievalHealth",
    "RetrievalSearchResult",
    "ChromaBackend",
    "FaissBackend",
    "build_retrieval_backend",
    "normalize_rag_backend",
]


def __getattr__(name: str) -> object:
    """Ленивый импорт backend-классов (тяжёлые зависимости только при обращении)."""
    if name == "ChromaBackend":
        from services.retrieval.chroma_backend import ChromaBackend as _ChromaBackend

        return _ChromaBackend
    if name == "FaissBackend":
        from services.retrieval.faiss_backend import FaissBackend as _FaissBackend

        return _FaissBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
