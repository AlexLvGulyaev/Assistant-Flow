"""Data access for app_users (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


class UserRepository:
    """PostgreSQL persistence for app_users."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory

    def get_by_telegram_user_id(
        self, conn: Connection, telegram_user_id: int
    ) -> dict[str, Any] | None:
        """Load a row by telegram_user_id (id as UUID)."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, telegram_user_id, telegram_chat_id, username, first_name, last_name,
                       role, is_active, created_at, updated_at
                FROM app_users
                WHERE telegram_user_id = %s
                LIMIT 1
                """,
                (telegram_user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users (
                    telegram_user_id, telegram_chat_id, username, first_name, last_name,
                    role, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    telegram_user_id,
                    telegram_chat_id,
                    username,
                    first_name,
                    last_name,
                    role,
                    is_active,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert app_users: no id returned")
        return row[0]

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
        sets: list[str] = []
        vals: list[Any] = []
        if telegram_chat_id is not None:
            sets.append("telegram_chat_id = %s")
            vals.append(telegram_chat_id)
        if username is not None:
            sets.append("username = %s")
            vals.append(username)
        if first_name is not None:
            sets.append("first_name = %s")
            vals.append(first_name)
        if last_name is not None:
            sets.append("last_name = %s")
            vals.append(last_name)
        if role is not None:
            sets.append("role = %s")
            vals.append(role)
        if is_active is not None:
            sets.append("is_active = %s")
            vals.append(is_active)
        if not sets:
            return
        vals.append(user_id)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE app_users SET {', '.join(sets)}, updated_at = NOW() WHERE id = %s",
                vals,
            )
