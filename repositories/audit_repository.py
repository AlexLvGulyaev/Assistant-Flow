"""PostgreSQL access for admin_audit_log (P9.5)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg import Connection


def insert_audit_row(
    conn: Connection,
    *,
    admin_user_id: uuid.UUID | None,
    execution_id: str | None,
    event_type: str,
    action: str,
    target_type: str | None,
    target_id: uuid.UUID | None,
    principal_email: str | None,
    platform_role: str | None,
    status: str,
    reason: str | None,
    request_path: str | None,
    request_method: str | None,
    ip_hash: str | None,
    user_agent: str | None,
    details: dict[str, Any],
) -> uuid.UUID:
    row_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_audit_log (
                id, admin_user_id, execution_id, event_type, action,
                target_type, target_id, principal_email, platform_role,
                status, reason, request_path, request_method,
                ip_hash, user_agent, details
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s::jsonb
            )
            """,
            (
                row_id,
                admin_user_id,
                execution_id,
                event_type,
                action,
                target_type,
                target_id,
                principal_email,
                platform_role,
                status,
                reason,
                request_path,
                request_method,
                ip_hash,
                (user_agent or "")[:512] or None,
                json.dumps(details, ensure_ascii=False, default=str),
            ),
        )
    return row_id


def list_recent(
    conn: Connection,
    *,
    limit: int,
    offset: int,
    event_type: str | None = None,
    status: str | None = None,
    principal_email: str | None = None,
    since_hours: int | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if event_type:
        clauses.append("event_type = %s")
        params.append(event_type)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if principal_email:
        clauses.append("LOWER(principal_email) = LOWER(%s)")
        params.append(principal_email.strip())
    if since_hours is not None:
        clauses.append("created_at >= NOW() - (%s || ' hours')::interval")
        params.append(str(int(since_hours)))
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, admin_user_id, execution_id, event_type, action,
                   target_type, target_id, principal_email, platform_role,
                   status, reason, request_path, request_method,
                   ip_hash, user_agent, details, created_at
            FROM admin_audit_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def summary_counts(
    conn: Connection,
    *,
    since_hours: int = 24,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE status = 'failure')::int AS failures,
                COUNT(*) FILTER (WHERE starts_with(event_type, 'auth.'))::int AS auth_events,
                COUNT(*) FILTER (WHERE starts_with(event_type, 'security.'))::int AS security_events
            FROM admin_audit_log
            WHERE created_at >= NOW() - (%s || ' hours')::interval
            """,
            (str(since_hours),),
        )
        row = cur.fetchone()
        total, failures, auth_events, security_events = row or (0, 0, 0, 0)
        cur.execute(
            """
            SELECT event_type, COUNT(*)::int AS cnt
            FROM admin_audit_log
            WHERE created_at >= NOW() - (%s || ' hours')::interval
            GROUP BY event_type
            ORDER BY cnt DESC
            LIMIT 20
            """,
            (str(since_hours),),
        )
        by_type = [{"event_type": r[0], "count": r[1]} for r in cur.fetchall()]
    return {
        "since_hours": since_hours,
        "total": total,
        "failures": failures,
        "auth_events": auth_events,
        "security_events": security_events,
        "by_event_type": by_type,
    }
