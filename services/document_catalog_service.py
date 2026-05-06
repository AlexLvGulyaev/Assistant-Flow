"""Knowledge-base documents and indexing jobs. Not wired into runtime yet."""

from __future__ import annotations

import uuid

from repositories.document_repository import DocumentRepository


class DocumentCatalogService:
    """Coordinates documents, versions, and indexing_jobs."""

    def __init__(self, repository: DocumentRepository | None = None) -> None:
        self._repository = repository or DocumentRepository()

    def register_uploaded_document(
        self,
        *,
        title: str,
        source_filename: str,
        storage_path: str,
        uploaded_by: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Create documents row in uploaded (or equivalent) state."""
        raise NotImplementedError

    def enqueue_indexing_job(self, document_id: uuid.UUID) -> uuid.UUID:
        """Create indexing_jobs row in pending state."""
        raise NotImplementedError
