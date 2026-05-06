"""Data access for app_users (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection

from repositories.connection import get_connection


class UserRepository:
    """Skeleton repository for table app_users."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory or get_connection

    def get_by_telegram_user_id(
        self, conn: Connection, telegram_user_id: int
    ) -> dict[str, Any] | None:
        """Load a row by telegram_user_id."""
        raise NotImplementedError

    def insert(
        self,
        conn: Connection,
        telegram_user_id: int,
        *,
        telegram_chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str = "user",
        is_active: bool = True,
    ) -> uuid.UUID:
        """Insert a new app_users row; return id."""
        raise NotImplementedError

    def update_profile(
        self,
        conn: Connection,
        user_id: uuid.UUID,
        *,
        telegram_chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        """Update allowed columns on app_users."""
        raise NotImplementedError
