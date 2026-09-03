"""
Адаптер Chroma: делегирует в ChromaRagStore, нормализует DTO для RetrievalBackend.

Scores — нативная семантика Chroma (distance); см. RetrievalSearchResult (backend-local).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from services.retrieval.base import (
    RetrievalChunk,
    RetrievalHealth,
    RetrievalSearchResult,
)
from services.retrieval.chunk_metadata import apply_retrieval_metadata_contract
from services.retrieval_security.chroma_where import build_chroma_where
from services.retrieval_security.context import RetrievalSecurityContext
from services.retrieval_security.result_filter import filter_search_results_by_security
from services.retrieval_security.telemetry import emit_retrieval_security_event

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

    def fetch_chunks_by_source(self, source: str, *, limit: int = 200) -> list[RetrievalChunk]:
        """Точная выборка чанков по metadata.source (без embeddings/similarity)."""
        out: list[RetrievalChunk] = []
        for rank, (page, meta) in enumerate(
            self._store.get_by_source(source, limit=limit)
        ):
            meta = apply_retrieval_metadata_contract(
                meta,
                backend=self.backend_name,
                result_rank=rank,
            )
            out.append(RetrievalChunk(page_content=page, metadata=meta))
        return out

    def reset_for_full_reindex(self) -> None:
        from services.rag_chroma_store import reset_chroma_for_reindex

        reset_chroma_for_reindex(
            self._store.app_config,
            persist_directory=self._store.persist_directory,
        )
        self._store.refresh_client_and_collection()

    def add_documents(self, documents: list[Any]) -> list[str]:
        return list(self._store.add_documents(documents))

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        self._store.delete_vectors_for_document_before_reindex(
            document_id=document_id,
            source_filename=source_filename,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[RetrievalSearchResult]:
        # Документы — объекты LangChain Document; не импортируем langchain_core на уровне модуля
        # (лёгкие тесты фабрики и import graph без тяжёлых зависимостей).
        ctx = security_context or RetrievalSecurityContext.permissive_default()
        chroma_where = build_chroma_where(ctx) if ctx.restricts_vector_query() else None
        if not ctx.is_fully_unrestricted():
            emit_retrieval_security_event(
                "retrieval_scope_applied",
                role=ctx.role,
                retrieval_scope=ctx.retrieval_scope,
                chroma_where=bool(chroma_where),
            )
        n = int(self.collection_count())
        requested = int(top_k)
        requested = min(n, max(requested * 8, requested)) if n > 0 else requested
        k = min(requested, n) if n > 0 else requested
        if k <= 0:
            return []
        raw: list[tuple[Any, float]] = self._store.native_similarity_search_with_score(
            query, k=k, where=chroma_where
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
        filtered = filter_search_results_by_security(out, ctx)
        return filtered[: int(top_k)]

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
