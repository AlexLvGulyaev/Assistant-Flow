"""Data access for user_channel_identities (P9.1)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


CHANNEL_TELEGRAM = "telegram"


class ChannelIdentityRepository:
    """PostgreSQL persistence for external channel → platform user links."""

    def get_by_channel_external(
        self,
        conn: Connection,
        *,
        channel: str,
        external_user_id: str,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, channel, external_user_id, external_chat_id,
                       metadata, created_at, updated_at
                FROM user_channel_identities
                WHERE channel = %s AND external_user_id = %s
                LIMIT 1
                """,
                (channel, external_user_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def insert(
        self,
        conn: Connection,
        *,
        user_id: uuid.UUID,
        channel: str,
        external_user_id: str,
        external_chat_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_channel_identities (
                    user_id, channel, external_user_id, external_chat_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (user_id, channel, external_user_id, external_chat_id, meta_json),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert user_channel_identities: no id returned")
        return row[0]
