"""
Admin API business logic for Evaluation / RAGAS Console (P2-lite).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from repositories.connection import get_connection
from repositories.evaluation_repository import EvaluationRepository
from repositories.processing_logs_repository import ProcessingLogsRepository
from services.evaluation_import_service import (
    build_interaction_from_trace,
    import_interactions_to_run,
)
from services.evaluation_ragas_service import execute_ragas_for_run
from services.evaluation_service import compute_run_summary

UI_INTERACTIVE_DATASET = "interactive_eval_ui"
_PREVIEW_LEN = 280


def _json_dict(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            p = json.loads(val)
            return p if isinstance(p, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _iso(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt) if dt is not None else None


def _preview(text: str | None, n: int = _PREVIEW_LEN) -> str | None:
    if not text:
        return None
    t = text.strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _execution_has_ragas_metrics(conn: Any, execution_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM evaluation_metric_fact emf
                JOIN evaluation_item ei ON ei.id = emf.item_id
                JOIN evaluation_dataset_item edi ON edi.id = ei.dataset_item_id
                WHERE edi.metadata->>'execution_id' = %s
                  AND emf.metric_key ~ '^ragas[.]'
                  AND emf.metric_value_numeric IS NOT NULL
            )
            """,
            (execution_id,),
        )
        row = cur.fetchone()
    return bool(row[0]) if row else False


def list_rag_turns(
    *,
    limit: int = 50,
    since_hours: int = 24,
    fallback: str | None = None,
    has_ragas_metrics: bool | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    lim = max(1, min(int(limit), 200))
    hours = max(1, min(int(since_hours), 24 * 365))
    fb = (fallback or "").strip().lower()
    q = (search or "").strip().lower()

    with get_connection() as conn:
        proc = ProcessingLogsRepository()
        rows = proc.list_recent_rag_events(conn, limit=min(lim * 3, 500))
        out: list[dict[str, Any]] = []
        cutoff_ms = datetime.now(timezone.utc).timestamp() - hours * 3600

        for row in rows:
            created = row.get("created_at")
            if isinstance(created, datetime):
                if created.timestamp() < cutoff_ms:
                    continue
            eid = str(row.get("execution_id") or "").strip()
            if not eid:
                continue
            details = _json_dict(row.get("details"))
            fr = str(details.get("fallback_reason") or row.get("fallback_reason") or "").strip()
            if fb and fb != "all":
                if fb == "none" and fr and fr.lower() not in ("none", ""):
                    continue
                if fb not in ("none", "all") and fr.lower() != fb:
                    continue

            query = (
                str(details.get("user_input") or "").strip()
                or str(details.get("query_preview") or "").strip()
                or str(row.get("query_preview") or "").strip()
            )
            answer = str(details.get("answer_text") or "").strip()
            if q and q not in query.lower() and q not in answer.lower() and q not in eid.lower():
                continue

            has_ragas = _execution_has_ragas_metrics(conn, eid)
            if has_ragas_metrics is True and not has_ragas:
                continue
            if has_ragas_metrics is False and has_ragas:
                continue

            gen = {
                k: details.get(k)
                for k in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "rag_pipeline_wall_ms",
                    "llm_latency_ms",
                )
                if details.get(k) is not None
            }
            item = {
                "execution_id": eid,
                "created_at": _iso(created),
                "query": query or None,
                "answer_preview": _preview(answer),
                "backend": details.get("retrieval_backend") or details.get("active_backend"),
                "top_k": details.get("top_k"),
                "retrieved_count": details.get("retrieved_count") or row.get("retrieved_count"),
                "fallback_reason": fr or None,
                "token_usage": gen if gen else None,
                "latency_ms": details.get("rag_pipeline_wall_ms"),
                "has_ragas_metrics": has_ragas,
                "status": str(row.get("status") or ""),
            }
            out.append(item)
            if len(out) >= lim:
                break

    return {"limit": lim, "since_hours": hours, "count": len(out), "items": out}


def get_rag_turn_detail(*, execution_id: str) -> dict[str, Any] | None:
    eid = (execution_id or "").strip()
    if not eid:
        return None
    with get_connection() as conn:
        proc = ProcessingLogsRepository()
        events = proc.list_events_for_execution_ids(conn, execution_ids=[eid])
        if not events:
            return None
        try:
            inter = build_interaction_from_trace(conn, execution_id=eid, events=events)
        except ValueError as exc:
            return {"execution_id": eid, "error": str(exc), "events_count": len(events)}
        has_ragas = _execution_has_ragas_metrics(conn, eid)
        chunks = inter.retrieval_diag.get("retrieved_chunks") or []
        return {
            "execution_id": eid,
            "query": inter.query_text,
            "answer": inter.answer_text,
            "retrieval_diag": inter.retrieval_diag,
            "generation_diag": inter.generation_diag,
            "retrieved_chunks": chunks,
            "metadata": inter.interaction_metadata,
            "has_ragas_metrics": has_ragas,
            "latency_ms_total": inter.latency_ms_total,
        }


def import_turns(
    *,
    execution_ids: list[str],
    dataset: str = UI_INTERACTIVE_DATASET,
    run_name: str | None = None,
) -> dict[str, Any]:
    run_id = import_interactions_to_run(
        execution_ids=execution_ids,
        dataset_slug=(dataset or UI_INTERACTIVE_DATASET).strip(),
        run_name=run_name or f"ui-import-{len(execution_ids)}",
        run_notes="imported via Admin UI",
    )
    return {"run_id": str(run_id), "imported_count": len(execution_ids)}


def run_ragas(*, run_id: uuid.UUID) -> dict[str, Any]:
    out = execute_ragas_for_run(run_id)
    ragas = out.get("ragas") or {}
    return {
        "run_id": str(run_id),
        "status": ragas.get("status"),
        "detail": ragas.get("detail"),
        "run_means": ragas.get("run_means"),
        "unavailable_metrics": ragas.get("unavailable_metrics"),
        "run_summary": out.get("run_summary"),
    }


def _serialize_run(row: dict[str, Any]) -> dict[str, Any]:
    snap = _json_dict(row.get("config_snapshot"))
    summary = _json_dict(row.get("run_summary"))
    return {
        "id": str(row["id"]),
        "name": row.get("name"),
        "notes": row.get("notes"),
        "status": row.get("status"),
        "created_at": _iso(row.get("created_at")),
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
        "item_count": row.get("item_count"),
        "import_mode": snap.get("import_mode") or summary.get("import_mode"),
        "source_execution_ids": snap.get("execution_ids")
        or summary.get("source_execution_ids"),
        "config_snapshot": snap,
        "run_summary": summary,
        "ragas": summary.get("ragas"),
    }


def list_runs(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    repo = EvaluationRepository()
    with get_connection() as conn:
        rows = repo.list_runs(conn, limit=limit, offset=offset)
    items = [_serialize_run(dict(r)) for r in rows]
    return {"limit": limit, "offset": offset, "count": len(items), "items": items}


def _metrics_by_item(
    metrics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in metrics:
        iid = str(m.get("item_id"))
        key = str(m.get("metric_key") or "")
        out.setdefault(iid, {})[key] = {
            "numeric": m.get("metric_value_numeric"),
            "json": _json_dict(m.get("metric_value_json")),
        }
    return out


def get_run_detail(*, run_id: uuid.UUID) -> dict[str, Any] | None:
    repo = EvaluationRepository()
    with get_connection() as conn:
        run = repo.get_run(conn, run_id=run_id)
        if not run:
            return None
        items = repo.list_items_for_run(conn, run_id=run_id)
        metrics = repo.list_metrics_for_run(conn, run_id=run_id)
        ds_items: dict[str, dict[str, Any]] = {}
        if items:
            ds = repo.list_dataset_items(conn, dataset_id=run["dataset_id"])
            for d in ds:
                ds_items[str(d["id"])] = dict(d)

    m_by_item = _metrics_by_item(metrics)
    item_rows: list[dict[str, Any]] = []
    for it in items:
        iid = str(it["id"])
        dsid = it.get("dataset_item_id")
        meta = _json_dict(ds_items.get(str(dsid), {}).get("metadata")) if dsid else {}
        rd = _json_dict(it.get("retrieval_diag"))
        gd = _json_dict(it.get("generation_diag"))
        item_rows.append(
            {
                "id": iid,
                "ordinal": it.get("ordinal"),
                "query": it.get("query_text"),
                "answer": it.get("answer_text"),
                "status": it.get("status"),
                "retrieval_diag": rd,
                "generation_diag": gd,
                "retrieved_chunks": rd.get("retrieved_chunks") or [],
                "latency_ms_total": it.get("latency_ms_total"),
                "execution_id": meta.get("execution_id"),
                "ground_truth": meta.get("ground_truth"),
                "question_type": meta.get("question_type"),
                "metrics": m_by_item.get(iid, {}),
            }
        )

    body = _serialize_run(dict(run))
    body["items"] = item_rows
    return body


def get_run_metrics_grouped(*, run_id: uuid.UUID) -> dict[str, Any] | None:
    repo = EvaluationRepository()
    with get_connection() as conn:
        run = repo.get_run(conn, run_id=run_id)
        if not run:
            return None
        items = repo.list_items_for_run(conn, run_id=run_id)
        metrics = repo.list_metrics_for_run(conn, run_id=run_id)

    by_ordinal: dict[int, list[dict[str, Any]]] = {}
    ord_map = {str(it["id"]): int(it["ordinal"]) for it in items}
    for m in metrics:
        iid = str(m.get("item_id"))
        ord_ = ord_map.get(iid, 0)
        by_ordinal.setdefault(ord_, []).append(
            {
                "item_id": iid,
                "metric_key": m.get("metric_key"),
                "metric_value_numeric": m.get("metric_value_numeric"),
                "metric_value_json": _json_dict(m.get("metric_value_json")),
            }
        )
    return {
        "run_id": str(run_id),
        "by_ordinal": {str(k): v for k, v in sorted(by_ordinal.items())},
    }


def patch_evaluation_item(
    *,
    item_id: uuid.UUID,
    ground_truth: str | None = None,
    notes: str | None = None,
    manual_score: float | None = None,
) -> dict[str, Any]:
    repo = EvaluationRepository()
    with get_connection() as conn:
        item = repo.get_item(conn, item_id=item_id)
        if not item:
            return {"error": "item_not_found"}
        run_id = item["run_id"]
        if not isinstance(run_id, uuid.UUID):
            run_id = uuid.UUID(str(run_id))

        meta_patch: dict[str, Any] = {}
        if ground_truth is not None:
            meta_patch["ground_truth"] = ground_truth
        if notes is not None:
            meta_patch["operator_notes"] = notes

        ds_item_id = item.get("dataset_item_id")
        if meta_patch and ds_item_id is not None:
            if not isinstance(ds_item_id, uuid.UUID):
                ds_item_id = uuid.UUID(str(ds_item_id))
            repo.patch_dataset_item_metadata(
                conn, dataset_item_id=ds_item_id, metadata_patch=meta_patch
            )

        if manual_score is not None:
            repo.upsert_metric(
                conn,
                run_id=run_id,
                item_id=item_id,
                metric_key="manual.overall",
                metric_value_numeric=float(manual_score),
                metric_value_json={"source": "admin_ui"},
            )

        if manual_score is not None or meta_patch:
            loaded = repo.list_items_for_run(conn, run_id=run_id)
            mids: dict[uuid.UUID, list[dict[str, Any]]] = {}
            for m in repo.list_metrics_for_run(conn, run_id=run_id):
                mid = m.get("item_id")
                if mid is None:
                    continue
                if not isinstance(mid, uuid.UUID):
                    mid = uuid.UUID(str(mid))
                mids.setdefault(mid, []).append(dict(m))
            summary = compute_run_summary(loaded, mids)
            run = repo.get_run(conn, run_id=run_id) or {}
            full = _json_dict(run.get("run_summary"))
            full.update(summary)
            repo.update_run_summary(conn, run_id=run_id, summary=full)

        conn.commit()

    detail = get_run_detail(run_id=run_id)
    patched = None
    if detail:
        for it in detail.get("items") or []:
            if str(it.get("id")) == str(item_id):
                patched = it
                break
    return {"item": patched, "run_id": str(run_id)}
