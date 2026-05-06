"""PostgreSQL access for intake_events, processing_logs, error_logs (schema v2)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.types.json import Json


class RuntimeLifecycleRepository:
    """Insert lifecycle rows; caller owns transaction (commit/rollback)."""

    def insert_intake_event(
        self,
        conn: Connection,
        *,
        execution_id: str,
        telegram_chat_id: int,
        telegram_user_id: int,
        raw_payload: dict[str, Any],
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO intake_events (
                    execution_id,
                    source,
                    event_type,
                    input_type,
                    telegram_chat_id,
                    telegram_user_id,
                    raw_payload,
                    status
                )
                VALUES (
                    %s,
                    'telegram',
                    'message',
                    'text',
                    %s,
                    %s,
                    %s,
                    'received'
                )
                RETURNING id
                """,
                (
                    execution_id,
                    telegram_chat_id,
                    telegram_user_id,
                    Json(raw_payload),
                ),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError("insert_intake_event: RETURNING id is empty")
        return row[0]

    def insert_processing_log(
        self,
        conn: Connection,
        *,
        execution_id: str,
        intake_event_id: uuid.UUID | None,
        stage: str,
        status: str,
        details: dict[str, Any] | None,
        error_text: str | None,
        attempt: int = 1,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processing_logs (
                    execution_id,
                    intake_event_id,
                    stage,
                    status,
                    details,
                    error_text,
                    attempt
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    intake_event_id,
                    stage,
                    status,
                    Json(details if details is not None else {}),
                    error_text,
                    attempt,
                ),
            )

    def insert_error_log(
        self,
        conn: Connection,
        *,
        execution_id: str,
        intake_event_id: uuid.UUID | None,
        component: str,
        operation: str,
        error_message: str,
        error_type: str | None,
        traceback_text: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO error_logs (
                    execution_id,
                    intake_event_id,
                    component,
                    operation,
                    error_type,
                    error_message,
                    traceback,
                    metadata,
                    severity
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'error')
                """,
                (
                    execution_id,
                    intake_event_id,
                    component,
                    operation,
                    error_type,
                    error_message,
                    traceback_text,
                    Json(metadata if metadata is not None else {}),
                ),
            )
