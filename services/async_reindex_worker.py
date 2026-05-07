"""Async reindex orchestration skeleton (P5.3b).

Foundation-only module:
- does NOT start background loops/threads
- does NOT change current synchronous reindex behavior
- executes exactly one claimed job when explicitly called
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from typing import Any

from services.admin_service import AdminService, ReindexRunResult
from services.async_job_service import AsyncJob, AsyncJobService


@dataclass(frozen=True)
class AsyncReindexRunOutcome:
    claimed: bool
    job_id: str | None
    status: str
    details: dict[str, Any]


class AsyncReindexWorker:
    """Single-step worker skeleton for `rag_reindex` jobs."""

    JOB_TYPE = "rag_reindex"

    def __init__(
        self,
        *,
        job_service: AsyncJobService | None = None,
        admin_service: AdminService | None = None,
    ) -> None:
        self._jobs = job_service or AsyncJobService()
        self._admin = admin_service or AdminService()

    def enqueue_reindex_job(
        self,
        *,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> AsyncJob:
        """Create queued reindex job; no execution in this method."""
        job = self._jobs.create_job(
            job_type=self.JOB_TYPE,
            payload_json=payload or {},
            max_attempts=max_attempts,
        )
        print(
            f"[assistant-flow] async_reindex: enqueued job_id={job.id} "
            f"job_type={job.job_type} status={job.status}",
            flush=True,
        )
        return job

    def run_single_job(self) -> AsyncReindexRunOutcome:
        """
        Claim exactly one `rag_reindex` job and execute existing sync reindex.

        This is a controlled orchestration step for future workers (P5.3c).
        """
        job = self._jobs.claim_next_job(job_type=self.JOB_TYPE)
        if job is None:
            return AsyncReindexRunOutcome(
                claimed=False,
                job_id=None,
                status="idle",
                details={"reason": "no_claimable_jobs"},
            )
        print(
            f"[assistant-flow] async_reindex: claimed job_id={job.id} "
            f"job_type={job.job_type} status={job.status} attempts={job.attempts}",
            flush=True,
        )
        # Explicit transition call for clear lifecycle contract (idempotent here).
        job = self._jobs.mark_running(job.id)
        t0 = time.monotonic()
        try:
            result: ReindexRunResult = self._admin.run_reindex()
            duration_ms = int((time.monotonic() - t0) * 1000)
            if result.success:
                payload = {
                    "duration_ms": duration_ms,
                    "chunks_created": result.chunks_created,
                    "collection_count": result.collection_count,
                    "files_indexed_ok": result.files_indexed_ok,
                    "files_found": result.files_found,
                    "used_postgres": result.used_postgres,
                }
                done = self._jobs.mark_succeeded(job.id, result_json=payload)
                print(
                    f"[assistant-flow] async_reindex: succeeded job_id={done.id} "
                    f"status={done.status} duration_ms={duration_ms}",
                    flush=True,
                )
                return AsyncReindexRunOutcome(
                    claimed=True,
                    job_id=str(done.id),
                    status=done.status,
                    details=payload,
                )

            err_payload = {
                "duration_ms": duration_ms,
                "error_message": result.error_message or "reindex reported failure",
                "chunks_created": result.chunks_created,
                "collection_count": result.collection_count,
                "files_indexed_ok": result.files_indexed_ok,
                "files_found": result.files_found,
                "used_postgres": result.used_postgres,
            }
            failed = self._jobs.mark_failed(job.id, error_json=err_payload, retry=True)
            print(
                f"[assistant-flow] async_reindex: failed job_id={failed.id} "
                f"status={failed.status} duration_ms={duration_ms}",
                flush=True,
            )
            return AsyncReindexRunOutcome(
                claimed=True,
                job_id=str(failed.id),
                status=failed.status,
                details=err_payload,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            err_payload = {
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc()[:4000],
            }
            failed = self._jobs.mark_failed(job.id, error_json=err_payload, retry=True)
            print(
                f"[assistant-flow] async_reindex: exception job_id={failed.id} "
                f"status={failed.status} duration_ms={duration_ms}",
                flush=True,
            )
            return AsyncReindexRunOutcome(
                claimed=True,
                job_id=str(failed.id),
                status=failed.status,
                details=err_payload,
            )
