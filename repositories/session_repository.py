"""Data access for chat_sessions and chat_messages (see database/schema.sql)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json


class SessionRepository:
    """PostgreSQL persistence for chat_sessions and chat_messages."""

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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_sessions (user_id, mode, is_active)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, mode, is_active),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("create_session: no id returned")
        return row[0]

    def get_active_session_for_user(
        self, conn: Connection, user_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the active session row for a user, if any."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, mode, is_active, created_at, updated_at
                FROM chat_sessions
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def set_session_mode(self, conn: Connection, session_id: uuid.UUID, mode: str) -> None:
        """Update chat_sessions.mode (text | rag | voice | image | career | hr_screening)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions SET mode = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (mode, session_id),
            )

    def deactivate_all_active_for_user(self, conn: Connection, user_id: uuid.UUID) -> int:
        """Set is_active=FALSE for all active sessions of a user; returns rowcount."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET is_active = FALSE, updated_at = NOW()
                WHERE user_id = %s AND is_active = TRUE
                """,
                (user_id,),
            )
            return int(cur.rowcount or 0)

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
        execution_id: str | None = None,
        intake_event_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert chat_messages; return id."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (
                    session_id, user_id, role, content, modality, metadata, execution_id, intake_event_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    user_id,
                    role,
                    content,
                    modality,
                    Json(metadata or {}),
                    execution_id,
                    intake_event_id,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("append_message: no id returned")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
                (session_id,),
            )
        return row[0]

    def list_messages_for_session(
        self,
        conn: Connection,
        session_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent messages for a session (newest first)."""
        lim = max(1, min(int(limit), 500))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, session_id, user_id, role, content, modality, metadata,
                       execution_id, intake_event_id, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id, lim),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_sessions_for_admin(
        self,
        conn: Connection,
        *,
        active_only: bool,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """Join app_users + message counts for Admin observability (newest activity first)."""
        lim = max(1, min(int(limit), 200))
        off = max(0, int(offset))
        active_clause = "AND s.is_active = TRUE" if active_only else ""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    s.id,
                    s.user_id,
                    s.mode,
                    s.is_active,
                    s.created_at,
                    s.updated_at,
                    u.telegram_user_id,
                    u.username,
                    u.first_name,
                    (
                        SELECT COUNT(*)::int
                        FROM chat_messages m
                        WHERE m.session_id = s.id
                    ) AS messages_count
                FROM chat_sessions s
                INNER JOIN app_users u ON u.id = s.user_id
                WHERE 1=1 {active_clause}
                ORDER BY s.updated_at DESC
                LIMIT %s OFFSET %s
                """,
                (lim, off),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_session_with_user_for_admin(
        self, conn: Connection, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Single session + app_users profile for Admin detail."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.user_id,
                    s.mode,
                    s.is_active,
                    s.created_at,
                    s.updated_at,
                    u.telegram_user_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    (
                        SELECT COUNT(*)::int
                        FROM chat_messages m
                        WHERE m.session_id = s.id
                    ) AS messages_count
                FROM chat_sessions s
                INNER JOIN app_users u ON u.id = s.user_id
                WHERE s.id = %s
                LIMIT 1
                """,
                (session_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def count_active_sessions(self, conn: Connection) -> int:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*)::int FROM chat_sessions WHERE is_active = TRUE"
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def avg_turns_for_sessions_touched_within_hours(
        self, conn: Connection, *, hours: int
    ) -> float:
        """Approximate dialog turns = (user+assistant message count) / 2, averaged over sessions."""
        h = max(1, min(int(hours), 24 * 365))
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(AVG(msg_cnt / 2.0), 0)::double precision
                FROM (
                    SELECT
                        s.id,
                        (
                            SELECT COUNT(*)::float
                            FROM chat_messages m
                            WHERE m.session_id = s.id
                              AND LOWER(m.role) IN ('user', 'assistant')
                        ) AS msg_cnt
                    FROM chat_sessions s
                    WHERE s.updated_at >= NOW() - (%s * INTERVAL '1 hour')
                ) t
                WHERE t.msg_cnt > 0
                """,
                (h,),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            return 0.0
        return float(row[0])
