"""Data access for chat_sessions and chat_messages (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection


class SessionRepository:
    """Skeleton repository for chat_sessions and chat_messages."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory

    def create_session(
        self,
        conn: Connection,
        user_id: uuid.UUID,
        *,
        mode: str = "text",
        is_active: bool = True,
    ) -> uuid.UUID:
        """Insert chat_sessions; return id."""
        raise NotImplementedError

    def get_active_session_for_user(
        self, conn: Connection, user_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the active session row for a user, if any."""
        raise NotImplementedError

    def set_session_mode(self, conn: Connection, session_id: uuid.UUID, mode: str) -> None:
        """Update chat_sessions.mode (text | rag | voice | image)."""
        raise NotImplementedError

    def append_message(
        self,
        conn: Connection,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        role: str,
        content: str,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Insert chat_messages; return id."""
        raise NotImplementedError

    def list_messages_for_session(
        self,
        conn: Connection,
        session_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent messages for a session."""
        raise NotImplementedError
