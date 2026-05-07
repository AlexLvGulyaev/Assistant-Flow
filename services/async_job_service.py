"""Async job lifecycle foundation service (P5.3a).

This module defines DB-backed job model APIs for future background workers.
It does not start workers and does not change current runtime behavior.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from psycopg.rows import dict_row

from repositories.connection import get_connection

AsyncJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "retry_scheduled",
    "cancelled",
]


@dataclass(frozen=True)
class AsyncJob:
    id: uuid.UUID
    job_type: str
    status: AsyncJobStatus
    payload_json: dict[str, Any]
    result_json: dict[str, Any]
    error_json: dict[str, Any]
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class AsyncJobService:
    """DB lifecycle operations for async_jobs table."""

    _CLAIMABLE_STATUSES: tuple[str, ...] = ("queued", "retry_scheduled")

    def create_job(
        self,
        *,
        job_type: str,
        payload_json: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> AsyncJob:
        jt = (job_type or "").strip()
        if not jt:
            raise ValueError("job_type is required")
        ma = max(1, int(max_attempts))
        payload = payload_json if isinstance(payload_json, dict) else {}
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO async_jobs (
                    job_type, status, payload_json, max_attempts
                )
                VALUES (%s, 'queued', %s::jsonb, %s)
                RETURNING *
                """,
                (jt, payload, ma),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("create_job: INSERT RETURNING returned no row")
            conn.commit()
        return self._row_to_job(row)

    def get_job(self, job_id: uuid.UUID | str) -> AsyncJob | None:
        jid = self._normalize_job_id(job_id)
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM async_jobs WHERE id = %s", (jid,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def mark_running(self, job_id: uuid.UUID | str) -> AsyncJob:
        jid = self._normalize_job_id(job_id)
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE async_jobs
                   SET status = 'running',
                       started_at = COALESCE(started_at, NOW())
                 WHERE id = %s
                 RETURNING *
                """,
                (jid,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"job not found: {jid}")
            conn.commit()
        return self._row_to_job(row)

    def mark_succeeded(
        self,
        job_id: uuid.UUID | str,
        *,
        result_json: dict[str, Any] | None = None,
    ) -> AsyncJob:
        jid = self._normalize_job_id(job_id)
        result = result_json if isinstance(result_json, dict) else {}
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE async_jobs
                   SET status = 'succeeded',
                       result_json = %s::jsonb,
                       finished_at = NOW()
                 WHERE id = %s
                 RETURNING *
                """,
                (result, jid),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"job not found: {jid}")
            conn.commit()
        return self._row_to_job(row)

    def mark_failed(
        self,
        job_id: uuid.UUID | str,
        *,
        error_json: dict[str, Any] | None = None,
        retry: bool = False,
    ) -> AsyncJob:
        jid = self._normalize_job_id(job_id)
        err = error_json if isinstance(error_json, dict) else {}
        next_status: AsyncJobStatus = "retry_scheduled" if retry else "failed"
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE async_jobs
                   SET status = %s,
                       error_json = %s::jsonb,
                       finished_at = CASE
                           WHEN %s = 'failed' THEN NOW()
                           ELSE finished_at
                       END
                 WHERE id = %s
                 RETURNING *
                """,
                (next_status, err, next_status, jid),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"job not found: {jid}")
            conn.commit()
        return self._row_to_job(row)

    def claim_next_job(self, *, job_type: str | None = None) -> AsyncJob | None:
        """
        Atomically claim one next queued job.

        Uses FOR UPDATE SKIP LOCKED to be safe for future concurrent workers.
        """
        jt = (job_type or "").strip()
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if jt:
                cur.execute(
                    """
                    WITH candidate AS (
                        SELECT id
                          FROM async_jobs
                         WHERE status IN ('queued', 'retry_scheduled')
                           AND job_type = %s
                           AND attempts < max_attempts
                         ORDER BY created_at ASC
                         FOR UPDATE SKIP LOCKED
                         LIMIT 1
                    )
                    UPDATE async_jobs j
                       SET status = 'running',
                           attempts = attempts + 1,
                           started_at = COALESCE(started_at, NOW())
                      FROM candidate
                     WHERE j.id = candidate.id
                    RETURNING j.*
                    """,
                    (jt,),
                )
            else:
                cur.execute(
                    """
                    WITH candidate AS (
                        SELECT id
                          FROM async_jobs
                         WHERE status IN ('queued', 'retry_scheduled')
                           AND attempts < max_attempts
                         ORDER BY created_at ASC
                         FOR UPDATE SKIP LOCKED
                         LIMIT 1
                    )
                    UPDATE async_jobs j
                       SET status = 'running',
                           attempts = attempts + 1,
                           started_at = COALESCE(started_at, NOW())
                      FROM candidate
                     WHERE j.id = candidate.id
                    RETURNING j.*
                    """
                )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return self._row_to_job(row)

    @staticmethod
    def _normalize_job_id(job_id: uuid.UUID | str) -> uuid.UUID:
        if isinstance(job_id, uuid.UUID):
            return job_id
        return uuid.UUID(str(job_id))

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> AsyncJob:
        return AsyncJob(
            id=row["id"],
            job_type=str(row["job_type"]),
            status=row["status"],
            payload_json=row["payload_json"] or {},
            result_json=row["result_json"] or {},
            error_json=row["error_json"] or {},
            attempts=int(row["attempts"] or 0),
            max_attempts=int(row["max_attempts"] or 0),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
        )
