"""Read-only access to processing_logs (see database/schema.sql)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


def _sanitize_hours(hours: int) -> int:
    return max(1, min(int(hours), 24 * 365))


class ProcessingLogsRepository:
    """Recent lifecycle rows for admin/diagnostics."""

    def count_events_since(self, conn: Connection, *, hours: int = 24) -> int:
        """Total rows in ``processing_logs`` since ``NOW() - hours``."""
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::bigint
                FROM processing_logs
                WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                """,
                (h,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def count_by_status_since(self, conn: Connection, *, hours: int = 24) -> dict[str, int]:
        """Counts grouped by ``status`` in the time window."""
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*)::int
                FROM processing_logs
                WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                GROUP BY status
                ORDER BY status
                """,
                (h,),
            )
            rows = cur.fetchall()
        return {str(r[0]): int(r[1]) for r in rows if r[0] is not None}

    def count_by_stage_since(self, conn: Connection, *, hours: int = 24) -> dict[str, int]:
        """Counts grouped by ``stage`` in the time window."""
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stage, COUNT(*)::int
                FROM processing_logs
                WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                GROUP BY stage
                ORDER BY stage
                """,
                (h,),
            )
            rows = cur.fetchall()
        return {str(r[0]): int(r[1]) for r in rows if r[0] is not None}

    def count_routes_since(self, conn: Connection, *, hours: int = 24) -> dict[str, int]:
        """
        Count rows with ``stage`` in ``route_selected`` / ``processing_done`` only,
        where ``details`` JSON has a known ``route`` (``rag``, ``text``,
        ``image_generation``). Rows without ``route`` or with other values are omitted.
        """
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT (details->>'route') AS route_bucket, COUNT(*)::int
                FROM processing_logs
                WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND stage IN ('route_selected', 'processing_done')
                  AND (details->>'route') IN ('rag', 'text', 'image_generation')
                GROUP BY route_bucket
                ORDER BY route_bucket
                """,
                (h,),
            )
            rows = cur.fetchall()
        return {str(r[0]): int(r[1]) for r in rows if r[0] is not None}

    def get_rag_quality_stats_since(
        self, conn: Connection, *, hours: int = 24
    ) -> dict[str, Any]:
        """
        Aggregate RAG-oriented rows in ``processing_logs`` (``details`` JSON).

        A row is included when ``details->>'route'`` is ``rag`` or when ``details``
        contains any of ``fallback_reason``, ``retrieved_count``, ``context_chars``.
        Fallback buckets follow ``services/rag_query_service`` (``low_relevance``,
        ``empty_retrieval``, ``empty_context``, ``llm_error``).
        """
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)::bigint AS rag_events,
                    COUNT(*) FILTER (WHERE details->>'fallback_reason' = 'low_relevance')::int
                        AS low_relevance,
                    COUNT(*) FILTER (WHERE details->>'fallback_reason' = 'empty_retrieval')::int
                        AS empty_retrieval,
                    COUNT(*) FILTER (WHERE details->>'fallback_reason' = 'empty_context')::int
                        AS empty_context,
                    COUNT(*) FILTER (WHERE details->>'fallback_reason' = 'llm_error')::int
                        AS llm_error,
                    AVG(
                        NULLIF(jsonb_extract_path_text(details, 'retrieved_count'), '')::double precision
                    ) AS avg_retrieved_count,
                    AVG(
                        NULLIF(jsonb_extract_path_text(details, 'filtered_count'), '')::double precision
                    ) AS avg_filtered_count,
                    AVG(
                        NULLIF(jsonb_extract_path_text(details, 'context_chars'), '')::double precision
                    ) AS avg_context_chars
                FROM processing_logs
                WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND (
                    (details->>'route') = 'rag'
                    OR details ? 'fallback_reason'
                    OR details ? 'retrieved_count'
                    OR details ? 'context_chars'
                  )
                """,
                (h,),
            )
            row = cur.fetchone()
        if not row:
            return _empty_rag_quality_stats()
        return {
            "rag_events": int(row[0] or 0),
            "low_relevance": int(row[1] or 0),
            "empty_retrieval": int(row[2] or 0),
            "empty_context": int(row[3] or 0),
            "llm_error": int(row[4] or 0),
            "avg_retrieved_count": _avg_to_float(row[5]),
            "avg_filtered_count": _avg_to_float(row[6]),
            "avg_context_chars": _avg_to_float(row[7]),
        }

    def list_recent(
        self,
        conn: Connection,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 500))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, created_at
                FROM processing_logs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (lim,),
            )
            return list(cur.fetchall())

    def list_recent_rag_events(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        fallback_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Last RAG answer events from ``processing_logs`` (stage ``rag_answer_done``).
        Optionally filter by ``details->>'fallback_reason'``.
        """
        lim = max(1, min(int(limit), 500))
        fallback = (fallback_reason or "").strip()
        with conn.cursor(row_factory=dict_row) as cur:
            if fallback:
                cur.execute(
                    """
                    SELECT
                        created_at,
                        execution_id,
                        status,
                        details->>'query_preview' AS query_preview,
                        details->>'fallback_reason' AS fallback_reason,
                        NULLIF(details->>'retrieved_count', '')::int AS retrieved_count,
                        NULLIF(details->>'filtered_count', '')::int AS filtered_count,
                        NULLIF(details->>'context_chars', '')::int AS context_chars,
                        details->'scores' AS scores,
                        NULLIF(details->>'relevance_threshold', '')::double precision AS relevance_threshold,
                        details
                    FROM processing_logs
                    WHERE stage = 'rag_answer_done'
                      AND details->>'fallback_reason' = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (fallback, lim),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        created_at,
                        execution_id,
                        status,
                        details->>'query_preview' AS query_preview,
                        details->>'fallback_reason' AS fallback_reason,
                        NULLIF(details->>'retrieved_count', '')::int AS retrieved_count,
                        NULLIF(details->>'filtered_count', '')::int AS filtered_count,
                        NULLIF(details->>'context_chars', '')::int AS context_chars,
                        details->'scores' AS scores,
                        NULLIF(details->>'relevance_threshold', '')::double precision AS relevance_threshold,
                        details
                    FROM processing_logs
                    WHERE stage = 'rag_answer_done'
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (lim,),
                )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_recent_route_events(
        self,
        conn: Connection,
        *,
        route: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Last rows where ``details.route`` equals the provided route."""
        route_norm = (route or "").strip()
        if not route_norm:
            return []
        lim = max(1, min(int(limit), 500))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT created_at, execution_id, status, details
                FROM processing_logs
                WHERE details->>'route' = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (route_norm, lim),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def count_stage_last_hours(
        self,
        conn: Connection,
        *,
        stage: str,
        hours: int = 24,
    ) -> int:
        """Rows with given stage since NOW() - interval hours (admin overview)."""
        h = max(1, min(int(hours), 24 * 365))
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int
                FROM processing_logs
                WHERE stage = %s
                  AND created_at >= NOW() - (%s * INTERVAL '1 hour')
                """,
                (stage, h),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def get_latest(self, conn: Connection) -> dict[str, Any] | None:
        """Single newest row (overview «последнее событие»)."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, created_at
                FROM processing_logs
                ORDER BY created_at DESC
                LIMIT 1
                """,
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _avg_to_float(val: object) -> float:
    if val is None:
        return 0.0
    return float(val)


def _empty_rag_quality_stats() -> dict[str, Any]:
    return {
        "rag_events": 0,
        "low_relevance": 0,
        "empty_retrieval": 0,
        "empty_context": 0,
        "llm_error": 0,
        "avg_retrieved_count": 0.0,
        "avg_filtered_count": 0.0,
        "avg_context_chars": 0.0,
    }
