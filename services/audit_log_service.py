"""Product request and error logs (request_logs, error_logs). Not wired into providers yet."""

from __future__ import annotations

import uuid
from typing import Any

from repositories.logs_repository import LogsRepository


class AuditLogService:
    """Coordinates persistence of request_logs and error_logs."""

    def __init__(self, repository: LogsRepository | None = None) -> None:
        self._repository = repository or LogsRepository()

    def log_request(
        self,
        *,
        request_type: str,
        success: bool = True,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Insert a request_logs row (see schema check constraint on request_type)."""
        raise NotImplementedError

    def log_error(
        self,
        *,
        component: str,
        operation: str,
        error_message: str,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        error_type: str | None = None,
        traceback: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert an error_logs row."""
        raise NotImplementedError
