"""Index local documents into the active vector backend (admin / tooling)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from services.rag_document_loader import load_and_split_directory
from services.retrieval.base import RetrievalBackend
from utils.config import AppConfig


class LocalRagIndexer:
    """Build or refresh the vector index from files on disk."""

    def __init__(self, config: AppConfig, vector_backend: RetrievalBackend) -> None:
        self._config = config
        self._vector_backend = vector_backend

    def index_documents_dir(
        self,
        directory: Path | None = None,
    ) -> int:
        """
        Load, chunk, and upsert all supported files under directory (recursive).
        Returns number of chunks indexed. For a clean Chroma rebuild use
        ``reset_chroma_for_reindex`` / ``ChromaBackend.reset_for_full_reindex`` or
        ``admin_index_documents.py --reindex``.
        """
        source_dir = Path(directory) if directory else Path(self._config.rag_documents_dir)
        chunks = load_and_split_directory(source_dir, self._config)
        if not chunks:
            return 0
        self._vector_backend.add_documents(chunks)
        return len(chunks)

    def index_documents(self, chunks: list[Document]) -> int:
        """Index an explicit list of Document chunks (for tests or custom pipelines)."""
        if not chunks:
            return 0
        self._vector_backend.add_documents(chunks)
        return len(chunks)
