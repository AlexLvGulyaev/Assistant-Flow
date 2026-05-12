"""
Базовые типы и контракт retrieval backend (P6.1).

Операционная индексация (reset/add/delete перед reindex) — часть единого контракта
для Chroma (default) и FAISS (secondary, RAG_BACKEND=faiss).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from services.retrieval_security.context import RetrievalSecurityContext


@dataclass(frozen=True)
class RetrievalChunk:
    """Один фрагмент текста для retrieval (аналог page_content + metadata).

    Минимальный набор полей в metadata после P6.2b — см. ``chunk_metadata.apply_retrieval_metadata_contract``
    и PROJECT_STATE (контракт retrieval metadata). Старые индексы без полей не ломаются: бэкенды
    подставляют safe defaults при маппинге.
    """

    page_content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RetrievalSearchResult:
    """Результат similarity search: чанк + score.

    ``score`` — **backend-local** семантика (Chroma distance / FAISS L2 и т.д.), **не** сравнима
    между разными backend в одном ranking без отдельного слоя normalization/reranking.

    TODO (P6+ hybrid): единая нормализация или калиброванные ранги перед merge результатов
    нескольких backend; до этого **запрещено** смешивать сырые scores разных backend в одном pipeline.
    """

    chunk: RetrievalChunk
    score: float


@dataclass(frozen=True)
class RetrievalHealth:
    """Минимальный снимок здоровья retrieval backend (без полного telemetry contract).

    Интерпретация полей (P6.2b, едино для Chroma/FAISS):
    - ``backend`` — идентификатор backend;
    - ``ok`` — готовность к **осмысленному** query retrieval (пустая коллекция Chroma допустима и
      даёт ``ok=True``, ``collection_count=0``; пустой FAISS-индекс — ``ok=False``);
    - ``detail`` — краткое пояснение / путь к индексу (без больших payload);
    - ``collection_count`` — число векторов/записей или ``None`` при ошибке подсчёта.
    """

    backend: str
    ok: bool
    detail: str | None = None
    collection_count: int | None = None


@runtime_checkable
class RetrievalBackend(Protocol):
    """Единый контракт retrieval: чтение + операционная запись для admin indexer."""

    @property
    def backend_name(self) -> str:
        """Короткий идентификатор backend (chroma, faiss, ...)."""
        ...

    def collection_count(self) -> int:
        """Число записей в активной коллекции/индексе (best-effort)."""
        ...

    def reset_for_full_reindex(self) -> None:
        """Полный сброс векторного индекса перед полной переиндексацией корпуса."""
        ...

    def add_documents(self, documents: list[Any]) -> list[str]:
        """
        Добавить чанки с эмбеддингами. ``documents`` — ``langchain_core.documents.Document``.
        Возвращает стабильные id записей (Chroma uuid / FAISS uuid string).
        """
        ...

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        """Удалить векторы документа перед повторной индексацией одного файла (идемпотентность)."""
        ...

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[RetrievalSearchResult]:
        """Similarity search; пустой query → пустой список (как у ChromaRagStore).

        ``security_context`` — P6.7: фильтрация до/после vector query по backend;
        ``None`` — permissive default (как до P6.7).

        Scores в результатах — в шкале конкретного backend (см. RetrievalSearchResult).
        """
        ...

    def healthcheck(self) -> RetrievalHealth:
        """Лёгкая проверка доступности (без тяжёлых embedding-вызовов)."""
        ...
