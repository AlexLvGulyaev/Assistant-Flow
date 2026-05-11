"""Chat sessions and message history (chat_sessions, chat_messages)."""

from __future__ import annotations

import uuid
from typing import Any

from repositories.connection import get_connection
from repositories.session_repository import SessionRepository


class ChatSessionService:
    """Координация сессий и сообщений в PostgreSQL."""

    def __init__(self, repository: SessionRepository | None = None) -> None:
        self._repository = repository or SessionRepository()

    def get_or_create_active_session(self, user_id: uuid.UUID, *, mode: str = "text") -> uuid.UUID:
        """Активная сессия пользователя или новая запись."""
        with get_connection() as conn:
            row = self._repository.get_active_session_for_user(conn, user_id)
            if row:
                return row["id"]
            return self._repository.create_session(conn, user_id, mode=mode, is_active=True)

    def set_mode(self, session_id: uuid.UUID, mode: str) -> None:
        """Persist session mode."""
        with get_connection() as conn:
            self._repository.set_session_mode(conn, session_id, mode)

    def record_message(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        role: str,
        content: str,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
        execution_id: str | None = None,
        intake_event_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Append chat_messages; return message id."""
        with get_connection() as conn:
            return self._repository.append_message(
                conn,
                session_id,
                user_id,
                role=role,
                content=content,
                modality=modality,
                metadata=metadata,
                execution_id=execution_id,
                intake_event_id=intake_event_id,
            )

    def list_recent_messages_raw(
        self, session_id: uuid.UUID, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Сырые строки chat_messages (новые первые)."""
        with get_connection() as conn:
            return self._repository.list_messages_for_session(conn, session_id, limit=limit)
