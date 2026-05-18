"""
Фабрика retrieval backend по AppConfig.

- chroma (по умолчанию): ChromaBackend + chroma_store.
- faiss: secondary operational backend; embeddings + FAISS_INDEX_DIR.
- weaviate: tertiary operational backend; embeddings + WEAVIATE_* (BYOV vectors).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.retrieval.base import RetrievalBackend

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

    from services.rag_chroma_store import ChromaRagStore
    from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
    from utils.config import AppConfig


def normalize_rag_backend(raw: str | None) -> str:
    """Пустое / отсутствующее значение → chroma."""
    s = (raw or "").strip().lower()
    return s if s else "chroma"


KNOWN_RAG_BACKENDS: frozenset[str] = frozenset({"chroma", "faiss", "weaviate"})


def effective_rag_backend_from_sources(
    *,
    env_backend: str,
    db_backend: str | None,
) -> str:
    """
    DB wins when set and valid; otherwise env bootstrap default.
    ``db_backend`` must already be validated or None.
    """
    if db_backend is not None and db_backend in KNOWN_RAG_BACKENDS:
        return db_backend
    return normalize_rag_backend(env_backend)
def build_retrieval_backend(
    config: "AppConfig",
    *,
    chroma_store: "ChromaRagStore | None" = None,
    embeddings: "Embeddings | None" = None,
    tuning_resolver: "RetrievalTuningResolver | None" = None,
) -> RetrievalBackend:
    """
    Собирает RetrievalBackend для runtime RAG.

    Raises:
        ValueError: неподдерживаемый RAG_BACKEND, отсутствуют обязательные аргументы
            (без молчаливого fallback на Chroma).
    """
    name = normalize_rag_backend(config.rag_backend)
    backend: RetrievalBackend

    if name == "chroma":
        if chroma_store is None:
            raise ValueError(
                "RAG_BACKEND=chroma: требуется передать chroma_store=ChromaRagStore(...)."
            )
        from services.retrieval.chroma_backend import ChromaBackend

        backend = ChromaBackend(chroma_store)

    elif name == "faiss":
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
        allow_empty = not vec_file.is_file()
        try:
            backend = FaissBackend(
                index_dir=index_dir,
                embeddings=embeddings,
                app_config=config,
                allow_empty=allow_empty,
            )
        except Exception as exc:
            raise ValueError(
                "RAG_BACKEND=faiss: не удалось инициализировать FAISS backend "
                f"в {index_dir}: {type(exc).__name__}: {exc}. "
                "Проверьте FAISS_INDEX_DIR, chunks.json и manifest."
            ) from exc

    elif name == "weaviate":
        if embeddings is None:
            raise ValueError(
                "RAG_BACKEND=weaviate: требуется передать embeddings=build_openai_embeddings(config). "
                "Молчаливый fallback на Chroma не выполняется."
            )
        from services.retrieval.weaviate_backend import WeaviateBackend

        try:
            backend = WeaviateBackend(config=config, embeddings=embeddings)
        except Exception as exc:
            raise ValueError(
                "RAG_BACKEND=weaviate: не удалось подключиться к Weaviate или создать схему: "
                f"{type(exc).__name__}: {exc}. Проверьте WEAVIATE_HOST / WEAVIATE_URL и compose."
            ) from exc

    else:
        raise ValueError(
            f"RAG_BACKEND={name!r}: неподдерживаемый retrieval backend. "
            f"Допустимо: chroma (по умолчанию), faiss, weaviate."
        )

    from services.cache.caching_retrieval_backend import CachingRetrievalBackend

    return CachingRetrievalBackend(
        backend,
        config=config,
        tuning_resolver=tuning_resolver,
    )
