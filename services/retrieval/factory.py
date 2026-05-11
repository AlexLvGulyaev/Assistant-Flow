"""
Фабрика retrieval backend по AppConfig.

- chroma (по умолчанию): ChromaBackend + chroma_store.
- faiss: явный демо-контур; требует embeddings и готовый индекс под FAISS_INDEX_DIR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.retrieval.base import RetrievalBackend

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

    from services.rag_chroma_store import ChromaRagStore
    from utils.config import AppConfig


def normalize_rag_backend(raw: str | None) -> str:
    """Пустое / отсутствующее значение → chroma."""
    s = (raw or "").strip().lower()
    return s if s else "chroma"


def build_retrieval_backend(
    config: "AppConfig",
    *,
    chroma_store: "ChromaRagStore | None" = None,
    embeddings: "Embeddings | None" = None,
) -> RetrievalBackend:
    """
    Собирает RetrievalBackend для runtime RAG.

    Raises:
        ValueError: неподдерживаемый RAG_BACKEND, отсутствуют обязательные аргументы,
            нет FAISS-индекса при RAG_BACKEND=faiss (без молчаливого fallback на Chroma).
    """
    name = normalize_rag_backend(config.rag_backend)
    if name == "chroma":
        if chroma_store is None:
            raise ValueError(
                "RAG_BACKEND=chroma: требуется передать chroma_store=ChromaRagStore(...)."
            )
        from services.retrieval.chroma_backend import ChromaBackend

        return ChromaBackend(chroma_store)

    if name == "faiss":
        if embeddings is None:
            raise ValueError(
                "RAG_BACKEND=faiss: требуется передать embeddings=build_openai_embeddings(config). "
                "Молчаливый fallback на Chroma не выполняется."
            )
        from pathlib import Path

        from services.retrieval.faiss_backend import (
            FaissBackend,
            resolve_faiss_index_dir,
            VECTORS_FILENAME,
        )

        # Корень репозитория: parent of services/retrieval
        project_root = Path(__file__).resolve().parents[2]
        index_dir = resolve_faiss_index_dir(config, project_root=project_root)
        vec_file = index_dir / VECTORS_FILENAME
        if not vec_file.is_file():
            raise ValueError(
                "RAG_BACKEND=faiss: индекс не найден — отсутствует файл "
                f"{vec_file}. Укажите FAISS_INDEX_DIR или соберите индекс: "
                "python scripts/build_faiss_demo_index.py. Fallback на Chroma не выполняется."
            )
        try:
            return FaissBackend(index_dir=index_dir, embeddings=embeddings)
        except Exception as exc:
            raise ValueError(
                "RAG_BACKEND=faiss: не удалось загрузить FAISS-индекс "
                f"из {index_dir}: {type(exc).__name__}: {exc}. "
                "Проверьте chunks.json и manifest; пересоберите демо-индекс при необходимости."
            ) from exc

    raise ValueError(
        f"RAG_BACKEND={name!r}: неподдерживаемый retrieval backend. "
        f"Допустимо: chroma (по умолчанию), faiss (демо/курс, явный выбор)."
    )
