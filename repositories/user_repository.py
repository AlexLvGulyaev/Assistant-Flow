"""Data access for app_users (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


_USER_SELECT = """
    SELECT id, telegram_user_id, telegram_chat_id, username, first_name, last_name,
           role, is_active, created_at, updated_at,
           email, password_hash, display_name, status, platform_role, retrieval_role,
           last_login_at
    FROM app_users
"""


class UserRepository:
    """PostgreSQL persistence for app_users."""

    def __init__(self, connection_factory: Any = None) -> None:
        self._connection_factory = connection_factory

    def get_by_id(self, conn: Connection, user_id: uuid.UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"{_USER_SELECT} WHERE id = %s LIMIT 1", (user_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def get_by_email(self, conn: Connection, email: str) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"{_USER_SELECT} WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                (email.strip(),),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_by_telegram_user_id(
        self, conn: Connection, telegram_user_id: int
    ) -> dict[str, Any] | None:
        """Load a row by telegram_user_id (legacy column; P9.1 also uses channel identities)."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"{_USER_SELECT} WHERE telegram_user_id = %s LIMIT 1",
                (telegram_user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def count_by_platform_role(self, conn: Connection, platform_role: str) -> int:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM app_users WHERE platform_role = %s AND status = 'active'",
                (platform_role,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

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
                    role, is_active, platform_role, retrieval_role
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    "admin" if role == "admin" else "end_user",
                    "admin" if role == "admin" else "employee",
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

    def insert_platform_user(
        self,
        conn: Connection,
        *,
        email: str,
        password_hash: str,
        display_name: str | None = None,
        platform_role: str = "admin",
        retrieval_role: str = "admin",
        status: str = "active",
        telegram_user_id: int | None = None,
        legacy_role: str = "admin",
    ) -> uuid.UUID:
        """Создать platform user (email/password); telegram_user_id опционален."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users (
                    email, password_hash, display_name, platform_role, retrieval_role,
                    status, role, is_active, telegram_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                RETURNING id
                """,
                (
                    email.strip().lower(),
                    password_hash,
                    display_name,
                    platform_role,
                    retrieval_role,
                    status,
                    legacy_role,
                    telegram_user_id,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_platform_user: no id returned")
        return row[0]

    def update_last_login(self, conn: Connection, user_id: uuid.UUID) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s",
                (user_id,),
            )
