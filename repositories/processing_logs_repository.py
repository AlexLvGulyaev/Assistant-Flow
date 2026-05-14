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

    def count_unique_execution_ids_since(
        self, conn: Connection, *, hours: int = 24
    ) -> int:
        """Distinct ``execution_id`` count in the time window."""
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT execution_id)::bigint
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
        Count requests by normalized route in the time window.
        One request = one ``execution_id`` (not raw event row).
        Route inference accepts route/mode/stage aliases (text_response, text_answer_done,
        rag_answer_done, document stages, ``details.route``/``mode`` for document, etc.)
        and picks the latest known route per execution_id.

        Note: PostgreSQL ``LIKE`` treats ``_`` as a wildcard, so patterns such as
        ``'admin_document%'`` do **not** match literal ``admin_document…`` stages; use
        regex ``~ '^admin_document'`` instead.
        """
        h = _sanitize_hours(hours)
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH normalized AS (
                    SELECT
                        execution_id,
                        created_at,
                        CASE
                            WHEN (details->>'route') IN ('rag', 'rag_response', 'memory_meta')
                                 OR stage = 'rag_answer_done'
                                 OR (details->>'mode') = 'rag'
                            THEN 'rag'
                            WHEN (details->>'route') IN ('text', 'text_response', 'vision_ocr')
                                 OR stage = 'text_answer_done'
                                 OR (details->>'mode') IN ('text', 'ocr')
                            THEN 'text'
                            WHEN (details->>'route') IN ('image_generation', 'image', 'image_response')
                            THEN 'image_generation'
                            WHEN (details->>'route') IN ('audio', 'voice', 'voice_response')
                                 OR (details->>'mode') = 'voice'
                                 OR stage IN (
                                    'stt_started',
                                    'stt_completed',
                                    'tts_started',
                                    'tts_completed',
                                    'tts_skipped',
                                    'tts_error',
                                    'voice_processing_done',
                                    'voice_processing_error',
                                    'audio_generation_done',
                                    'audio_generation_error'
                                 )
                            THEN 'audio'
                            WHEN stage ~ '^admin_document'
                                 OR stage ~ '^document_(upload|preprocessing|processed|compatibility|indexing|edit|reindex)_'
                                 OR LOWER(COALESCE(details->>'route', '')) IN ('document', 'document_response')
                                 OR LOWER(COALESCE(details->>'downstream_route', ''))
                                    IN ('document', 'document_response')
                                 OR LOWER(COALESCE(details->>'mode', '')) = 'document'
                            THEN 'document'
                            ELSE NULL
                        END AS route_bucket
                    FROM processing_logs
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                ),
                last_route_per_request AS (
                    SELECT DISTINCT ON (execution_id)
                        execution_id,
                        route_bucket
                    FROM normalized
                    WHERE route_bucket IS NOT NULL
                    ORDER BY execution_id, created_at DESC
                )
                SELECT route_bucket, COUNT(*)::int
                FROM last_route_per_request
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
        offset: int = 0,
        since_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 2000))
        off = max(0, int(offset))
        with conn.cursor(row_factory=dict_row) as cur:
            if since_hours is None:
                cur.execute(
                    """
                    SELECT execution_id, stage, status, details, created_at
                    FROM processing_logs
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (lim, off),
                )
            else:
                h = _sanitize_hours(since_hours)
                cur.execute(
                    """
                    SELECT execution_id, stage, status, details, created_at
                    FROM processing_logs
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (h, lim, off),
                )
            return list(cur.fetchall())

    def list_logs_for_document_filename(
        self,
        conn: Connection,
        *,
        filename: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Recent processing_logs rows mentioning a knowledge-base filename in details."""
        fn = (filename or "").strip()
        if not fn:
            return []
        lim = max(1, min(int(limit), 200))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, error_text, created_at
                FROM processing_logs
                WHERE LOWER(COALESCE(details->>'filename', '')) = LOWER(%s)
                   OR LOWER(COALESCE(details->>'source_filename', '')) = LOWER(%s)
                   OR LOWER(COALESCE(details->>'indexed_target_filename', '')) = LOWER(%s)
                   OR LOWER(COALESCE(details->>'original_upload_filename', '')) = LOWER(%s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (fn, fn, fn, fn, lim),
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

    def list_recent_text_events(
        self,
        conn: Connection,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Full processing_logs chains for recent text requests by execution_id.

        Text request detection:
        - details.route in ('text', 'text_response'), OR
        - details.mode = 'text'
        """
        lim = max(1, min(int(limit), 500))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH selected_exec AS (
                    SELECT execution_id, MAX(created_at) AS last_at
                    FROM processing_logs
                    WHERE (details->>'route') IN ('text', 'text_response')
                       OR (details->>'mode') = 'text'
                    GROUP BY execution_id
                    ORDER BY last_at DESC
                    LIMIT %s
                )
                SELECT
                    p.execution_id,
                    p.stage,
                    p.status,
                    p.details,
                    p.created_at
                FROM processing_logs p
                JOIN selected_exec s
                  ON s.execution_id = p.execution_id
                ORDER BY s.last_at DESC, p.created_at ASC
                """,
                (lim,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def count_distinct_execution_ids(self, conn: Connection) -> int:
        """Total distinct requests in processing_logs."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT execution_id)::bigint
                FROM processing_logs
                """,
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def list_recent_execution_ids(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Recent requests (execution_id) sorted by latest event time."""
        lim = max(1, min(int(limit), 500))
        off = max(0, int(offset))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, MAX(created_at) AS last_at
                FROM processing_logs
                GROUP BY execution_id
                ORDER BY last_at DESC
                LIMIT %s OFFSET %s
                """,
                (lim, off),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_events_for_execution_ids(
        self,
        conn: Connection,
        *,
        execution_ids: list[str],
    ) -> list[dict[str, Any]]:
        """All rows for selected execution_ids."""
        ids = [str(x).strip() for x in execution_ids if str(x).strip()]
        if not ids:
            return []
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, created_at
                FROM processing_logs
                WHERE execution_id = ANY(%s::text[])
                ORDER BY created_at ASC
                """,
                (ids,),
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

    def list_memory_events_for_session(
        self,
        conn: Connection,
        *,
        session_id_str: str,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Recent memory_* stages where details.session_id matches (metadata only in API layer)."""
        lim = max(1, min(int(limit), 200))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, created_at
                FROM processing_logs
                WHERE stage ~ '^memory_'
                  AND details->>'session_id' = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id_str, lim),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_memory_session_cleared_for_user(
        self,
        conn: Connection,
        *,
        app_user_id_str: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 50))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT execution_id, stage, status, details, created_at
                FROM processing_logs
                WHERE stage = 'memory_session_cleared'
                  AND details->>'user_id' = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (app_user_id_str, lim),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def telegram_user_ids_with_recent_memory_clear(
        self,
        conn: Connection,
        *,
        within_hours: float = 2.0,
    ) -> set[str]:
        """Telegram user ids (as strings) that had memory_session_cleared recently."""
        wh = max(0.25, min(float(within_hours), 168.0))
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT details->>'telegram_user_id' AS tid
                FROM processing_logs
                WHERE stage = 'memory_session_cleared'
                  AND created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND details ? 'telegram_user_id'
                  AND COALESCE(details->>'telegram_user_id', '') <> ''
                """,
                (wh,),
            )
            rows = cur.fetchall()
        return {str(r[0]) for r in rows if r and r[0]}

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
