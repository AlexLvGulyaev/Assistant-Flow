"""Best-effort runtime lifecycle logging to PostgreSQL (intake + processing + errors)."""

from __future__ import annotations

import sys
import traceback
import uuid
from typing import Any

from repositories.connection import get_connection, get_database_url
from repositories.runtime_lifecycle_repository import RuntimeLifecycleRepository

_LOG_PREFIX = "[assistant-flow] lifecycle:"

_MAX_PREVIEW = 200
_MAX_ERROR_TEXT = 4000
_MAX_TRACEBACK = 8000


def truncate_for_lifecycle_log(text: str, max_len: int = _MAX_PREVIEW) -> str:
    """User-visible text preview for logs (no secrets added here)."""
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


class RuntimeLifecycleService:
    """
    P1 lifecycle: intake_events + processing_logs + error_logs.
    All methods are best-effort: failures are printed to stderr and swallowed.
    """

    def __init__(self, repository: RuntimeLifecycleRepository | None = None) -> None:
        self._repo = repository or RuntimeLifecycleRepository()

    def _emit_failure(self, where: str, exc: BaseException) -> None:
        print(
            f"{_LOG_PREFIX} {where} failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )

    def create_intake_event(
        self,
        *,
        execution_id: str,
        telegram_chat_id: int,
        telegram_user_id: int,
        text_preview: str,
        original_char_length: int,
    ) -> uuid.UUID | None:
        """
        Insert intake_events (source=telegram, event_type=message, input_type=text).
        raw_payload: preview only + length; no API keys.
        """
        try:
            _ = get_database_url()
        except Exception as exc:
            self._emit_failure("create_intake_event (no DATABASE_URL)", exc)
            return None

        preview = truncate_for_lifecycle_log(text_preview, _MAX_PREVIEW)
        raw_payload: dict[str, Any] = {
            "text_preview": preview,
            "char_length": min(max(original_char_length, 0), 1_000_000),
        }

        try:
            with get_connection() as conn:
                intake_id = self._repo.insert_intake_event(
                    conn,
                    execution_id=execution_id,
                    telegram_chat_id=telegram_chat_id,
                    telegram_user_id=telegram_user_id,
                    raw_payload=raw_payload,
                )
                conn.commit()
                return intake_id
        except Exception as exc:
            self._emit_failure("create_intake_event", exc)
            return None

    def log_processing_event(
        self,
        *,
        execution_id: str,
        intake_event_id: uuid.UUID | None = None,
        stage: str,
        status: str,
        details: dict[str, Any] | None = None,
        error_text: str | None = None,
        attempt: int = 1,
    ) -> None:
        """Append processing_logs row."""
        try:
            _ = get_database_url()
        except Exception as exc:
            self._emit_failure("log_processing_event (no DATABASE_URL)", exc)
            return

        et = (error_text or "")[:_MAX_ERROR_TEXT] if error_text else None

        try:
            with get_connection() as conn:
                self._repo.insert_processing_log(
                    conn,
                    execution_id=execution_id,
                    intake_event_id=intake_event_id,
                    stage=stage,
                    status=status,
                    details=details,
                    error_text=et,
                    attempt=attempt,
                )
                conn.commit()
        except Exception as exc:
            self._emit_failure(f"log_processing_event ({stage})", exc)

    def log_error(
        self,
        *,
        execution_id: str,
        intake_event_id: uuid.UUID | None = None,
        component: str,
        operation: str,
        error_message: str,
        error_type: str | None = None,
        traceback_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append error_logs row."""
        try:
            _ = get_database_url()
        except Exception as exc:
            self._emit_failure("log_error (no DATABASE_URL)", exc)
            return

        tb = (traceback_text or "")[:_MAX_TRACEBACK] if traceback_text else None
        msg = (error_message or "")[:_MAX_ERROR_TEXT]

        try:
            with get_connection() as conn:
                self._repo.insert_error_log(
                    conn,
                    execution_id=execution_id,
                    intake_event_id=intake_event_id,
                    component=component,
                    operation=operation,
                    error_message=msg,
                    error_type=error_type,
                    traceback_text=tb,
                    metadata=metadata,
                )
                conn.commit()
        except Exception as exc:
            self._emit_failure("log_error", exc)

    def log_error_from_exception(
        self,
        *,
        execution_id: str,
        intake_event_id: uuid.UUID | None,
        component: str,
        operation: str,
        exc: BaseException,
    ) -> None:
        """Convenience: log_error + traceback string."""
        self.log_error(
            execution_id=execution_id,
            intake_event_id=intake_event_id,
            component=component,
            operation=operation,
            error_message=str(exc)[:_MAX_ERROR_TEXT],
            error_type=type(exc).__name__,
            traceback_text=traceback.format_exc()[:_MAX_TRACEBACK],
        )
