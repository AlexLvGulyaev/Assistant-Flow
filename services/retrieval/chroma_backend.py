"""
Адаптер Chroma: делегирует в ChromaRagStore, нормализует DTO для RetrievalBackend.

Scores — нативная семантика Chroma (distance); см. RetrievalSearchResult (backend-local).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.retrieval.base import (
    RetrievalChunk,
    RetrievalHealth,
    RetrievalSearchResult,
)
from services.retrieval.chunk_metadata import apply_retrieval_metadata_contract

if TYPE_CHECKING:
    from services.rag_chroma_store import ChromaRagStore


class ChromaBackend:
    """Тонкая обёртка над ChromaRagStore; логику Chroma не дублирует."""

    def __init__(self, store: "ChromaRagStore") -> None:
        self._store = store

    @property
    def backend_name(self) -> str:
        return "chroma"

    def collection_count(self) -> int:
        return int(self._store.collection_count())

    def search(self, query: str, top_k: int = 5) -> list[RetrievalSearchResult]:
        # Документы — объекты LangChain Document; не импортируем langchain_core на уровне модуля
        # (лёгкие тесты фабрики и import graph без тяжёлых зависимостей).
        raw: list[tuple[Any, float]] = self._store.native_similarity_search_with_score(
            query, k=top_k
        )
        out: list[RetrievalSearchResult] = []
        for rank, (doc, score) in enumerate(raw):
            meta = dict(getattr(doc, "metadata", None) or {})
            meta = apply_retrieval_metadata_contract(
                meta,
                backend=self.backend_name,
                result_rank=rank,
            )
            page = getattr(doc, "page_content", None) or ""
            out.append(
                RetrievalSearchResult(
                    chunk=RetrievalChunk(
                        page_content=page,
                        metadata=meta,
                    ),
                    score=float(score),
                )
            )
        return out

    def healthcheck(self) -> RetrievalHealth:
        """Пустая коллекция (count=0) — не ошибка: backend доступен, ретривал просто пуст."""
        try:
            n = self.collection_count()
            return RetrievalHealth(
                backend=self.backend_name,
                ok=True,
                detail=None,
                collection_count=n,
            )
        except Exception as exc:
            return RetrievalHealth(
                backend=self.backend_name,
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
                collection_count=None,
            )
