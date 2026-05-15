"""PostgreSQL persistence for Evaluation Layer P1-lite (datasets, runs, items, metrics)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json


class EvaluationRepository:
    """Evaluation datasets / runs / items / sparse metric facts."""

    def get_dataset_by_slug(
        self, conn: Connection, *, slug: str, version: int | None = None
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            if version is None:
                cur.execute(
                    """
                    SELECT * FROM evaluation_dataset
                    WHERE slug = %s
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (slug,),
                )
            else:
                cur.execute(
                    "SELECT * FROM evaluation_dataset WHERE slug = %s AND version = %s",
                    (slug, int(version)),
                )
            return cur.fetchone()

    def list_dataset_items(
        self, conn: Connection, *, dataset_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM evaluation_dataset_item
                WHERE dataset_id = %s
                ORDER BY ordinal ASC
                """,
                (dataset_id,),
            )
            return list(cur.fetchall())

    def list_metrics_for_run(
        self, conn: Connection, *, run_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM evaluation_metric_fact
                WHERE run_id = %s
                ORDER BY item_id ASC, metric_key ASC
                """,
                (run_id,),
            )
            return list(cur.fetchall())

    def insert_dataset(
        self,
        conn: Connection,
        *,
        slug: str,
        version: int = 1,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_dataset (slug, version, title, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug, version) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, evaluation_dataset.title),
                    metadata = evaluation_dataset.metadata || EXCLUDED.metadata
                RETURNING id
                """,
                (slug, int(version), title, Json(metadata or {})),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_dataset: no id returned")
        return row[0]

    def insert_dataset_item(
        self,
        conn: Connection,
        *,
        dataset_id: uuid.UUID,
        ordinal: int,
        query_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_dataset_item (dataset_id, ordinal, query_text, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (dataset_id, ordinal) DO UPDATE SET
                    query_text = EXCLUDED.query_text,
                    metadata = evaluation_dataset_item.metadata || EXCLUDED.metadata
                RETURNING id
                """,
                (dataset_id, int(ordinal), query_text, Json(metadata or {})),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_dataset_item: no id returned")
        return row[0]

    def insert_run(
        self,
        conn: Connection,
        *,
        dataset_id: uuid.UUID,
        dataset_version: int,
        name: str | None,
        notes: str | None,
        config_snapshot: dict[str, Any],
        status: str = "pending",
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_run (
                    dataset_id, dataset_version, name, notes, status, config_snapshot
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    dataset_id,
                    int(dataset_version),
                    name,
                    notes,
                    status,
                    Json(config_snapshot),
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_run: no id returned")
        return row[0]

    def update_run_status(
        self,
        conn: Connection,
        *,
        run_id: uuid.UUID,
        status: str,
        run_summary: dict[str, Any] | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        sets = ["status = %s"]
        args: list[Any] = [status]
        if started:
            sets.append("started_at = COALESCE(started_at, NOW())")
        if finished:
            sets.append("finished_at = NOW()")
        if run_summary is not None:
            sets.append("run_summary = %s")
            args.append(Json(run_summary))
        args.append(run_id)
        sql = f"UPDATE evaluation_run SET {', '.join(sets)} WHERE id = %s"
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args))

    def insert_item(
        self,
        conn: Connection,
        *,
        run_id: uuid.UUID,
        dataset_item_id: uuid.UUID | None,
        ordinal: int,
        query_text: str,
        status: str,
        error_text: str | None,
        answer_text: str | None,
        retrieval_diag: dict[str, Any] | None,
        generation_diag: dict[str, Any] | None,
        latency_ms_total: int | None,
    ) -> uuid.UUID:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_item (
                    run_id, dataset_item_id, ordinal, query_text, status, error_text,
                    answer_text, retrieval_diag, generation_diag, latency_ms_total
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    run_id,
                    dataset_item_id,
                    int(ordinal),
                    query_text,
                    status,
                    error_text,
                    answer_text,
                    Json(retrieval_diag or {}),
                    Json(generation_diag or {}),
                    latency_ms_total,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("insert_item: no id returned")
        return row[0]

    def upsert_metric(
        self,
        conn: Connection,
        *,
        run_id: uuid.UUID,
        item_id: uuid.UUID,
        metric_key: str,
        metric_value_numeric: float | None = None,
        metric_value_json: dict[str, Any] | None = None,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM evaluation_metric_fact
                WHERE item_id = %s AND metric_key = %s
                """,
                (item_id, metric_key),
            )
            cur.execute(
                """
                INSERT INTO evaluation_metric_fact (
                    run_id, item_id, metric_key, metric_value_numeric, metric_value_json
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    item_id,
                    metric_key,
                    metric_value_numeric,
                    Json(metric_value_json) if metric_value_json is not None else None,
                ),
            )

    def get_run(self, conn: Connection, *, run_id: uuid.UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM evaluation_run WHERE id = %s", (run_id,))
            return cur.fetchone()

    def list_items_for_run(
        self, conn: Connection, *, run_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM evaluation_item
                WHERE run_id = %s
                ORDER BY ordinal ASC
                """,
                (run_id,),
            )
            return list(cur.fetchall())

    def update_run_summary(
        self, conn: Connection, *, run_id: uuid.UUID, summary: dict[str, Any]
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE evaluation_run SET run_summary = %s WHERE id = %s",
                (Json(summary), run_id),
            )


