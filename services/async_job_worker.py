"""In-process async job worker daemon (P5.3c, variant A).

Background thread inside the admin-api process that consumes `async_jobs`
(claim via FOR UPDATE SKIP LOCKED) and executes `rag_reindex` jobs through
the existing single-step `AsyncReindexWorker` skeleton.

Design constraints (VPS 7.8 GiB, heavy-RAG safeguards):
- one job at a time, small poll interval when idle, no parallel workers;
- graceful stop via threading.Event (lifespan shutdown);
- on start, stale `running` jobs (left by a restarted process) are
  reclaimed back to `queued` so they are not stuck forever.

Env:
- AF_ASYNC_WORKER_ENABLED (default "1") — "0" disables the daemon;
- AF_ASYNC_WORKER_POLL_SECONDS (default "5") — idle poll interval;
- AF_ASYNC_WORKER_STALE_RUNNING_SECONDS (default "1800") — reclaim age.
"""

from __future__ import annotations

import os
import threading
import time

from services.async_reindex_worker import AsyncReindexWorker


class AsyncJobWorkerDaemon:
    """Single-threaded consumer loop for `async_jobs` (variant A)."""

    def __init__(self, *, worker: AsyncReindexWorker | None = None) -> None:
        self._worker = worker or AsyncReindexWorker()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ---- configuration -------------------------------------------------

    @staticmethod
    def enabled() -> bool:
        raw = (os.getenv("AF_ASYNC_WORKER_ENABLED", "1") or "1").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    @staticmethod
    def poll_seconds() -> float:
        try:
            val = float(os.getenv("AF_ASYNC_WORKER_POLL_SECONDS", "5"))
        except ValueError:
            return 5.0
        return max(1.0, min(val, 60.0))

    @staticmethod
    def stale_running_seconds() -> int:
        try:
            val = int(os.getenv("AF_ASYNC_WORKER_STALE_RUNNING_SECONDS", "1800"))
        except ValueError:
            return 1800
        return max(60, val)

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> bool:
        """Start the daemon thread; idempotent. Returns True if started."""
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="af-async-job-worker",
            daemon=True,
        )
        self._thread.start()
        print(
            "[assistant-flow] async_worker: started "
            f"(poll_seconds={self.poll_seconds()}, "
            f"stale_running_seconds={self.stale_running_seconds()})",
            flush=True,
        )
        return True

    def stop(self, *, timeout: float = 10.0) -> bool:
        """Signal stop and join the thread. Returns True if joined."""
        self._stop.set()
        thread = self._thread
        if thread is None or not thread.is_alive():
            return True
        thread.join(timeout=timeout)
        stopped = not thread.is_alive()
        print(
            "[assistant-flow] async_worker: stop signal "
            f"joined={stopped}",
            flush=True,
        )
        return stopped

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- loop -----------------------------------------------------------

    def _run_loop(self) -> None:
        # Reclaim jobs orphaned by a previous process restart (mid-job crash).
        reclaimed = self._reclaim_stale_running()
        if reclaimed:
            print(
                f"[assistant-flow] async_worker: reclaimed {reclaimed} "
                "stale running job(s) -> queued",
                flush=True,
            )
        while not self._stop.is_set():
            try:
                outcome = self._worker.run_single_job()
                if not outcome.claimed:
                    # Idle: sleep in small steps so stop is responsive.
                    self._stop.wait(timeout=self.poll_seconds())
            except Exception as exc:  # loop must survive any job error
                print(
                    f"[assistant-flow] async_worker: loop error "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                self._stop.wait(timeout=self.poll_seconds())

    def _reclaim_stale_running(self) -> int:
        try:
            return self._worker._jobs.reclaim_stale_running(
                older_than_seconds=self.stale_running_seconds()
            )
        except Exception as exc:
            print(
                f"[assistant-flow] async_worker: reclaim failed "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            return 0


# Process-wide singleton (variant A: one worker per admin-api process).
_daemon: AsyncJobWorkerDaemon | None = None
_daemon_lock = threading.Lock()


def get_async_job_worker() -> AsyncJobWorkerDaemon:
    global _daemon
    with _daemon_lock:
        if _daemon is None:
            _daemon = AsyncJobWorkerDaemon()
        return _daemon