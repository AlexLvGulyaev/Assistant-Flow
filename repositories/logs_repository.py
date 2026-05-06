"""Data access for request_logs and error_logs (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection


class LogsRepository:
    """Skeleton repository for request_logs and error_logs."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory

    def insert_request_log(
        self,
        conn: Connection,
        *,
        request_type: str,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        success: bool = True,
    ) -> uuid.UUID:
        """Insert request_logs; return id."""
        raise NotImplementedError

    def insert_error_log(
        self,
        conn: Connection,
        *,
        component: str,
        operation: str,
        error_message: str,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        error_type: str | None = None,
        traceback: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Insert error_logs; return id."""
        raise NotImplementedError
