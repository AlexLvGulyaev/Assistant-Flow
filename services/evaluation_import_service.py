"""
P1.1: Import real conversational interactions into Evaluation Layer (offline).

Sources (no duplicate storage): ``processing_logs`` (primary), ``chat_messages``,
``request_logs`` (token/latency enrichment). Does not touch Telegram/RAG runtime.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from repositories.connection import get_connection
from repositories.evaluation_repository import EvaluationRepository
from repositories.processing_logs_repository import ProcessingLogsRepository
from services.evaluation_service import compute_run_summary, split_log_details_to_blobs

DEFAULT_INTERACTIVE_DATASET_SLUG = "interactive_eval_tmp"
INTERACTIVE_DATASET_TITLE = "Interactive conversational evaluation (imported traces)"


@dataclass(frozen=True)
class ImportedInteraction:
    execution_id: str
    query_text: str
    answer_text: str | None
    retrieval_diag: dict[str, Any]
    generation_diag: dict[str, Any]
    latency_ms_total: int | None
    item_status: str
    error_text: str | None
    interaction_metadata: dict[str, Any]
    interaction_at: datetime | None


def _parse_json(val: Any) -> dict[str, Any]:
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


def _pick_rag_answer_done(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [e for e in events if str(e.get("stage") or "") == "rag_answer_done"]
    if not candidates:
        return None
    return candidates[-1]


def _fetch_chat_turn(conn: Any, *, execution_id: str) -> tuple[str | None, str | None]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE execution_id = %s
            ORDER BY created_at ASC
            """,
            (execution_id,),
        )
        rows = cur.fetchall()
    user_text: str | None = None
    assistant_text: str | None = None
    for row in rows:
        role = str(row.get("role") or "")
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and user_text is None:
            user_text = content
        elif role == "assistant":
            assistant_text = content
    return user_text, assistant_text


def _fetch_request_log_agg(conn: Any, *, execution_id: str) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT request_type, input_tokens, output_tokens, latency_ms, metadata, created_at
            FROM request_logs
            WHERE execution_id = %s
              AND request_type IN ('rag', 'rag_answer', 'rag_retrieval', 'embedding')
            ORDER BY created_at ASC
            """,
            (execution_id,),
        )
        rows = list(cur.fetchall())
    if not rows:
        return {}
    total_in = 0
    total_out = 0
    latency: int | None = None
    for r in rows:
        if r.get("input_tokens") is not None:
            total_in += int(r["input_tokens"])
        if r.get("output_tokens") is not None:
            total_out += int(r["output_tokens"])
        if r.get("latency_ms") is not None:
            latency = int(r["latency_ms"])
    out: dict[str, Any] = {}
    if total_in:
        out["input_tokens"] = total_in
    if total_out:
        out["output_tokens"] = total_out
    if total_in or total_out:
        out["total_tokens"] = total_in + total_out
    if latency is not None:
        out["request_log_latency_ms"] = latency
    return out


def build_interaction_from_trace(
    conn: Any,
    *,
    execution_id: str,
    events: list[dict[str, Any]] | None = None,
) -> ImportedInteraction:
    """
    Build one evaluation-ready interaction from existing operational logs.
    """
    eid = (execution_id or "").strip()
    if not eid:
        raise ValueError("execution_id is required")

    proc = ProcessingLogsRepository()
    if events is None:
        events = proc.list_events_for_execution_ids(conn, execution_ids=[eid])
    if not events:
        raise ValueError(f"no processing_logs for execution_id={eid}")

    rag_row = _pick_rag_answer_done(events)
    if rag_row is None:
        stages = sorted({str(e.get("stage") or "") for e in events})
        raise ValueError(
            f"no rag_answer_done for execution_id={eid}; stages={stages[:12]}"
        )

    details = _parse_json(rag_row.get("details"))
    chat_user, chat_asst = _fetch_chat_turn(conn, execution_id=eid)
    req_agg = _fetch_request_log_agg(conn, execution_id=eid)

    query = (
        str(details.get("user_input") or "").strip()
        or str(details.get("query_preview") or "").strip()
        or str(details.get("retrieval_ready_query") or "").strip()
        or (chat_user or "").strip()
    )
    if not query:
        raise ValueError(f"could not resolve user query for execution_id={eid}")

    answer = (
        str(details.get("answer_text") or "").strip()
        or (chat_asst or "").strip()
        or None
    )

    wall_ms: int | None = None
    try:
        if details.get("rag_pipeline_wall_ms") is not None:
            wall_ms = int(details["rag_pipeline_wall_ms"])
    except (TypeError, ValueError):
        wall_ms = None
    if wall_ms is None and req_agg.get("request_log_latency_ms") is not None:
        wall_ms = int(req_agg["request_log_latency_ms"])

    retrieval_diag, generation_diag = split_log_details_to_blobs(details, wall_ms=wall_ms)
    for k, v in req_agg.items():
        if k not in generation_diag and not k.endswith("_ms"):
            generation_diag[k] = v

    pl_status = str(rag_row.get("status") or "success")
    item_status = "ok" if pl_status == "success" else "error"
    error_text = str(rag_row.get("error_text") or "").strip() or None

    created = rag_row.get("created_at")
    interaction_at: datetime | None = None
    if isinstance(created, datetime):
        interaction_at = created

    interaction_metadata = {
        "source": "interactive_import",
        "execution_id": eid,
        "route": details.get("route") or "rag",
        "top_k": details.get("top_k"),
        "retrieval_backend": details.get("retrieval_backend") or details.get("active_backend"),
        "fallback_reason": details.get("fallback_reason"),
        "processing_status": pl_status,
        "interaction_at": interaction_at.isoformat() if interaction_at else None,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }

    return ImportedInteraction(
        execution_id=eid,
        query_text=query,
        answer_text=answer,
        retrieval_diag=retrieval_diag,
        generation_diag=generation_diag,
        latency_ms_total=wall_ms,
        item_status=item_status,
        error_text=error_text,
        interaction_metadata=interaction_metadata,
        interaction_at=interaction_at,
    )


def _ensure_interactive_dataset(
    conn: Any, repo: EvaluationRepository, *, slug: str
) -> tuple[uuid.UUID, int]:
    ds = repo.get_dataset_by_slug(conn, slug=slug)
    if ds:
        return ds["id"], int(ds["version"])
    did = repo.insert_dataset(
        conn,
        slug=slug,
        version=1,
        title=INTERACTIVE_DATASET_TITLE,
        metadata={"kind": "interactive_import", "locale": "ru"},
    )
    return did, 1


def _next_dataset_ordinal(conn: Any, *, dataset_id: uuid.UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(MAX(ordinal), 0) + 1
            FROM evaluation_dataset_item
            WHERE dataset_id = %s
            """,
            (dataset_id,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 1


def import_interactions_to_run(
    *,
    execution_ids: list[str],
    dataset_slug: str = DEFAULT_INTERACTIVE_DATASET_SLUG,
    run_name: str | None = None,
    run_notes: str | None = None,
) -> uuid.UUID:
    """
    Import one or more ``execution_id`` traces into a completed ``evaluation_run``.

    Pipeline: interactive usage → import → (existing) ``evaluation_ragas.py run``.
    """
    ids = [str(x).strip() for x in execution_ids if str(x).strip()]
    if not ids:
        raise ValueError("execution_ids list is empty")

    repo = EvaluationRepository()
    proc = ProcessingLogsRepository()
    interactions: list[ImportedInteraction] = []

    with get_connection() as conn:
        dataset_id, dataset_version = _ensure_interactive_dataset(conn, repo, slug=dataset_slug)

        for eid in ids:
            events = proc.list_events_for_execution_ids(conn, execution_ids=[eid])
            interactions.append(
                build_interaction_from_trace(conn, execution_id=eid, events=events)
            )

        snap: dict[str, Any] = {
            "import_mode": "interactive",
            "source": "processing_logs+chat_messages+request_logs",
            "dataset_slug": dataset_slug,
            "execution_ids": ids,
        }
        if interactions:
            m0 = interactions[0].interaction_metadata
            snap.update(
                {
                    "route": m0.get("route"),
                    "top_k": m0.get("top_k"),
                    "retrieval_backend": m0.get("retrieval_backend"),
                }
            )

        rid = repo.insert_run(
            conn,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            name=run_name or f"interactive-import-{ids[0][:8]}",
            notes=run_notes,
            config_snapshot=snap,
            status="running",
        )
        repo.update_run_status(conn, run_id=rid, status="running", started=True)

        for run_ordinal, inter in enumerate(interactions, start=1):
            ds_ordinal = _next_dataset_ordinal(conn, dataset_id=dataset_id)
            ds_item_id = repo.insert_dataset_item(
                conn,
                dataset_id=dataset_id,
                ordinal=ds_ordinal,
                query_text=inter.query_text,
                metadata={
                    **inter.interaction_metadata,
                    "question_type": "interactive_trace",
                },
            )
            repo.insert_item(
                conn,
                run_id=rid,
                dataset_item_id=ds_item_id,
                ordinal=run_ordinal,
                query_text=inter.query_text,
                status=inter.item_status,
                error_text=inter.error_text,
                answer_text=inter.answer_text,
                retrieval_diag=inter.retrieval_diag,
                generation_diag=inter.generation_diag,
                latency_ms_total=inter.latency_ms_total,
            )

        loaded = repo.list_items_for_run(conn, run_id=rid)
        summary = compute_run_summary(loaded, {})
        summary["import_mode"] = "interactive"
        summary["source_execution_ids"] = ids
        repo.update_run_status(
            conn,
            run_id=rid,
            status="completed",
            run_summary=summary,
            finished=True,
        )
        conn.commit()
        return rid


def list_recent_rag_execution_ids(*, limit: int = 5) -> list[str]:
    """Recent RAG interactions (``rag_answer_done``) for batch import."""
    lim = max(1, min(int(limit), 100))
    proc = ProcessingLogsRepository()
    with get_connection() as conn:
        rows = proc.list_recent_rag_events(conn, limit=lim)
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        eid = str(row.get("execution_id") or "").strip()
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out
