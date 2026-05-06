"""Chat sessions and message history (chat_sessions, chat_messages). Not wired into Telegram yet."""

from __future__ import annotations

import uuid
from typing import Any

from repositories.session_repository import SessionRepository


class ChatSessionService:
    """Coordinates session and message persistence."""

    def __init__(self, repository: SessionRepository | None = None) -> None:
        self._repository = repository or SessionRepository()

    def get_or_create_active_session(self, user_id: uuid.UUID) -> uuid.UUID:
        """Return active chat_sessions id for the given app_users.id."""
        raise NotImplementedError

    def set_mode(self, session_id: uuid.UUID, mode: str) -> None:
        """Persist session mode: text | rag | voice | image."""
        raise NotImplementedError

    def record_message(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        role: str,
        content: str,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append chat_messages."""
        raise NotImplementedError
