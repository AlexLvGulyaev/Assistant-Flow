"""
RAGAS batch evaluation against completed ``evaluation_run`` rows (offline, no Telegram).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from repositories.connection import get_connection
from repositories.evaluation_repository import EvaluationRepository
from services.evaluation.ragas_adapter import (
    RAGAS_METRIC_KEYS,
    build_ragas_single_row,
    run_ragas_evaluation,
)


def _parse_json_field(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def contexts_from_retrieval_diag(retrieval_diag: dict[str, Any]) -> list[str]:
    """Extract context strings from persisted ``evaluation_item.retrieval_diag``."""
    chunks = retrieval_diag.get("retrieved_chunks") or []
    if not isinstance(chunks, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        if not isinstance(c, dict):
            continue
        passed = c.get("passed_filter", True)
        body = (c.get("chunk_text_full") or c.get("text_preview") or "").strip()
        if not body:
            continue
        if passed is False:
            continue
        if body in seen:
            continue
        seen.add(body)
        out.append(body)
    return out


def build_ragas_rows_for_run(
    conn: Any,
    repo: EvaluationRepository,
    *,
    run_id: uuid.UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build RAGAS rows and parallel item records for persistence.

    Returns (ragas_rows, item_bindings) where item_bindings hold evaluation_item id + ordinal.
    """
    run = repo.get_run(conn, run_id=run_id)
    if not run:
        raise ValueError(f"evaluation_run not found: {run_id}")
    status = str(run.get("status") or "")
    if status != "completed":
        raise ValueError(f"run status must be completed, got {status!r}")

    items = repo.list_items_for_run(conn, run_id=run_id)
    if not items:
        raise ValueError("run has no evaluation_item rows")

    ds_items = repo.list_dataset_items(conn, dataset_id=run["dataset_id"])
    meta_by_ds_id: dict[uuid.UUID, dict[str, Any]] = {}
    for ds in ds_items:
        dsid = ds["id"]
        if not isinstance(dsid, uuid.UUID):
            dsid = uuid.UUID(str(dsid))
        meta_by_ds_id[dsid] = _parse_json_field(ds.get("metadata"))

    ragas_rows: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []

    for it in items:
        iid = it["id"]
        if not isinstance(iid, uuid.UUID):
            iid = uuid.UUID(str(iid))
        ds_item_id = it.get("dataset_item_id")
        meta: dict[str, Any] = {}
        if ds_item_id is not None:
            if not isinstance(ds_item_id, uuid.UUID):
                ds_item_id = uuid.UUID(str(ds_item_id))
            meta = meta_by_ds_id.get(ds_item_id, {})

        rd = _parse_json_field(it.get("retrieval_diag"))
        contexts = contexts_from_retrieval_diag(rd)
        ground_truth = (meta.get("ground_truth") or "").strip() or None
        question_type = meta.get("question_type")

        row = build_ragas_single_row(
            question=str(it.get("query_text") or ""),
            answer=str(it.get("answer_text") or ""),
            contexts=contexts,
            ground_truth=ground_truth,
        )
        row["ordinal"] = int(it.get("ordinal") or 0)
        row["question_type"] = question_type
        ragas_rows.append(row)
        bindings.append(
            {
                "item_id": iid,
                "ordinal": row["ordinal"],
                "question_type": question_type,
                "contexts_count": len(contexts),
            }
        )

    return ragas_rows, bindings


def persist_ragas_results(
    conn: Any,
    repo: EvaluationRepository,
    *,
    run_id: uuid.UUID,
    items: list[dict[str, Any]],
    ragas_out: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write per-item metrics and merge run_summary ragas section."""
    per_item = ragas_out.get("per_item") or []
    binding_by_ord = {int(b["ordinal"]): b for b in bindings}
    scored_keys_by_ord: dict[int, set[str]] = {}

    for entry in per_item:
        ord_ = int(entry.get("ordinal") or 0)
        bind = binding_by_ord.get(ord_)
        if not bind:
            continue
        item_id = bind["item_id"]
        scores = entry.get("scores") or {}
        errors = entry.get("errors") or {}
        scored_keys_by_ord[ord_] = set(scores.keys())
        for metric_key, numeric in scores.items():
            if metric_key not in RAGAS_METRIC_KEYS:
                continue
            repo.upsert_metric(
                conn,
                run_id=run_id,
                item_id=item_id,
                metric_key=metric_key,
                metric_value_numeric=float(numeric) if numeric is not None else None,
                metric_value_json={
                    "source": "ragas",
                    "errors": errors.get(metric_key),
                    "question_type": bind.get("question_type"),
                    "contexts_count": bind.get("contexts_count"),
                },
            )

    unavailable = ragas_out.get("unavailable_metrics") or []
    for metric_key in unavailable:
        if metric_key not in RAGAS_METRIC_KEYS:
            continue
        for bind in bindings:
            ord_ = int(bind["ordinal"])
            if metric_key in scored_keys_by_ord.get(ord_, set()):
                continue
            repo.upsert_metric(
                conn,
                run_id=run_id,
                item_id=bind["item_id"],
                metric_key=metric_key,
                metric_value_numeric=None,
                metric_value_json={
                    "source": "ragas",
                    "status": "not_collected",
                    "reason": ragas_out.get("detail") or "metric unavailable",
                },
            )

    run = repo.get_run(conn, run_id=run_id) or {}
    summary = _parse_json_field(run.get("run_summary"))
    summary["ragas"] = {
        "status": ragas_out.get("status"),
        "detail": ragas_out.get("detail"),
        "run_means": ragas_out.get("run_means"),
        "unavailable_metrics": unavailable,
    }
    repo.update_run_summary(conn, run_id=run_id, summary=summary)
    return summary


def execute_ragas_for_run(
    run_id: uuid.UUID,
    *,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Load run items, run RAGAS, persist ``evaluation_metric_fact`` + ``run_summary.ragas``."""
    repo = EvaluationRepository()
    with get_connection() as conn:
        rows, bindings = build_ragas_rows_for_run(conn, repo, run_id=run_id)
        ragas_out = run_ragas_evaluation(rows, openai_api_key=openai_api_key)
        summary = persist_ragas_results(
            conn, repo, run_id=run_id, items=rows, ragas_out=ragas_out, bindings=bindings
        )
        conn.commit()
    return {"ragas": ragas_out, "run_summary": summary}
