"""Data access for documents, document_versions, indexing_jobs (see database/schema.sql)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json


class DocumentRepository:
    """PostgreSQL persistence for knowledge-base documents and indexing jobs."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory

    def insert_document(
        self,
        conn: Connection,
        *,
        title: str,
        source_filename: str,
        storage_path: str,
        content_type: str | None = None,
        description: str | None = None,
        status: str = "uploaded",
        uploaded_by: uuid.UUID | None = None,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (
                    title, source_filename, storage_path, content_type, description,
                    status, uploaded_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title,
                    source_filename,
                    storage_path,
                    content_type,
                    description,
                    status,
                    uploaded_by,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_document: no id returned")
        return row[0]

    def insert_document_version(
        self,
        conn: Connection,
        document_id: uuid.UUID,
        *,
        version_number: int,
        storage_path: str,
        file_hash: str | None = None,
        indexed_at: datetime | None = None,
        chunk_count: int = 0,
        is_active: bool = True,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_versions (
                    document_id, version_number, storage_path, file_hash,
                    indexed_at, chunk_count, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    document_id,
                    version_number,
                    storage_path,
                    file_hash,
                    indexed_at,
                    chunk_count,
                    is_active,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_document_version: no id returned")
        return row[0]

    def create_indexing_job(
        self,
        conn: Connection,
        document_id: uuid.UUID,
        *,
        document_version_id: uuid.UUID | None = None,
        status: str = "pending",
        started_at: datetime | None = None,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO indexing_jobs (
                    document_id, document_version_id, status, started_at
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (document_id, document_version_id, status, started_at),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("create_indexing_job: no id returned")
        return row[0]

    def get_indexing_job_document_version_id(
        self, conn: Connection, job_id: uuid.UUID
    ) -> uuid.UUID | None:
        """FK document_version_id for this job (canonical target for post-index updates)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_version_id
                FROM indexing_jobs
                WHERE id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return row[0]

    def count_documents(self, conn: Connection) -> int:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::bigint FROM documents")
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def sum_version_chunk_counts(self, conn: Connection) -> int:
        """Sum chunk_count for active versions only (current index metadata per document)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(chunk_count), 0)::bigint
                FROM document_versions
                WHERE is_active = true
                """
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def delete_document_chunks_for_version(
        self, conn: Connection, document_version_id: uuid.UUID
    ) -> None:
        """Remove chunk metadata rows for one version before re-embedding (not a global wipe)."""
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE document_version_id = %s",
                (document_version_id,),
            )

    def find_active_version_for_document(
        self, conn: Connection, document_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Current indexed version row, if any."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, version_number, file_hash, chunk_count, indexed_at
                FROM document_versions
                WHERE document_id = %s AND is_active = true
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def deactivate_document_version(self, conn: Connection, version_id: uuid.UUID) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE document_versions SET is_active = false WHERE id = %s",
                (version_id,),
            )

    def list_documents_with_version_summary(self, conn: Connection) -> list[dict[str, Any]]:
        """
        One row per document: filename, status, active version stats, version counts.
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    d.id AS document_id,
                    d.source_filename AS filename,
                    d.status,
                    (
                        SELECT dv.version_number
                        FROM document_versions dv
                        WHERE dv.document_id = d.id AND dv.is_active = true
                        LIMIT 1
                    ) AS active_version,
                    (
                        SELECT COUNT(*)::int
                        FROM document_versions dv
                        WHERE dv.document_id = d.id
                    ) AS versions_count,
                    COALESCE(
                        (
                            SELECT dv.chunk_count
                            FROM document_versions dv
                            WHERE dv.document_id = d.id AND dv.is_active = true
                            LIMIT 1
                        ),
                        0
                    ) AS active_chunk_count,
                    (
                        SELECT dv.indexed_at
                        FROM document_versions dv
                        WHERE dv.document_id = d.id AND dv.is_active = true
                        LIMIT 1
                    ) AS last_indexed_at
                FROM documents d
                ORDER BY d.created_at DESC
                """
            )
            return list(cur.fetchall())

    def list_document_versions(
        self, conn: Connection, document_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """All versions for a document, ordered by version_number."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id AS version_id,
                    version_number,
                    is_active,
                    chunk_count,
                    file_hash,
                    indexed_at
                FROM document_versions
                WHERE document_id = %s
                ORDER BY version_number ASC
                """,
                (document_id,),
            )
            return list(cur.fetchall())

    def get_document(self, conn: Connection, document_id: uuid.UUID) -> dict[str, Any] | None:
        """Single documents row."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id AS document_id,
                    title,
                    source_filename,
                    storage_path,
                    content_type,
                    description,
                    status,
                    uploaded_by,
                    created_at,
                    updated_at
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def count_chunks_by_version_for_document(
        self, conn: Connection, document_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Chunk row counts grouped by document_version_id (diagnostics)."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT document_version_id::text AS version_id, COUNT(*)::bigint AS row_count
                FROM document_chunks
                WHERE document_id = %s
                GROUP BY document_version_id
                ORDER BY document_version_id
                """,
                (document_id,),
            )
            return list(cur.fetchall())

    def insert_document_chunk(
        self,
        conn: Connection,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        chunk_index: int,
        chunk_text_preview: str | None,
        token_count: int | None,
        chroma_collection: str,
        chroma_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta = metadata if metadata is not None else {}
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_chunks (
                    document_version_id,
                    document_id,
                    chunk_index,
                    chunk_text_preview,
                    token_count,
                    chroma_collection,
                    chroma_id,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document_version_id,
                    document_id,
                    chunk_index,
                    chunk_text_preview,
                    token_count,
                    chroma_collection,
                    chroma_id,
                    Json(meta),
                ),
            )

    def count_chunks_for_version(
        self, conn: Connection, document_version_id: uuid.UUID
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::bigint
                FROM document_chunks
                WHERE document_version_id = %s
                """,
                (document_version_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def list_chunks_for_version(
        self,
        conn: Connection,
        document_version_id: uuid.UUID,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 500))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    chunk_index,
                    chunk_text_preview,
                    token_count,
                    chroma_collection,
                    chroma_id,
                    metadata,
                    created_at
                FROM document_chunks
                WHERE document_version_id = %s
                ORDER BY chunk_index ASC
                LIMIT %s
                """,
                (document_version_id, lim),
            )
            return list(cur.fetchall())

    def list_documents_by_status(
        self, conn: Connection, status: str
    ) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM documents WHERE status = %s ORDER BY created_at",
                (status,),
            )
            return list(cur.fetchall())

    def find_latest_document_id_by_storage_path(
        self, conn: Connection, storage_path: str
    ) -> uuid.UUID | None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM documents
                WHERE storage_path = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (storage_path,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def max_version_number(self, conn: Connection, document_id: uuid.UUID) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(version_number), 0)
                FROM document_versions
                WHERE document_id = %s
                """,
                (document_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def update_document_status(
        self, conn: Connection, document_id: uuid.UUID, status: str
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET status = %s WHERE id = %s",
                (status, document_id),
            )

    def update_document_version_after_index(
        self,
        conn: Connection,
        version_id: uuid.UUID,
        *,
        chunk_count: int,
        indexed_at: datetime | None = None,
        file_hash: str | None = None,
    ) -> None:
        when = indexed_at if indexed_at is not None else datetime.now(timezone.utc)
        with conn.cursor() as cur:
            if file_hash is not None:
                cur.execute(
                    """
                    UPDATE document_versions
                    SET chunk_count = %s, indexed_at = %s, file_hash = %s
                    WHERE id = %s
                    """,
                    (chunk_count, when, file_hash, version_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE document_versions
                    SET chunk_count = %s, indexed_at = %s
                    WHERE id = %s
                    """,
                    (chunk_count, when, version_id),
                )

    def update_document_version_chunk_count_if_distinct(
        self,
        conn: Connection,
        version_id: uuid.UUID,
        chunk_count: int,
    ) -> None:
        """Bump chunk_count only when it changed (reindex, same file hash — no other columns)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE document_versions
                SET chunk_count = %s
                WHERE id = %s
                  AND chunk_count IS DISTINCT FROM %s
                """,
                (chunk_count, version_id, chunk_count),
            )

    def finalize_indexing_job(
        self,
        conn: Connection,
        job_id: uuid.UUID,
        *,
        status: str,
        error_text: str | None = None,
    ) -> None:
        finished = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = %s, error_text = %s, finished_at = %s
                WHERE id = %s
                """,
                (status, error_text, finished, job_id),
            )
