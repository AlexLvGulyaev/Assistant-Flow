"""P1-lite: execute evaluation runs against RagQueryService (no Telegram, no hot-path writes)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from repositories.connection import get_connection
from repositories.evaluation_repository import EvaluationRepository
from services.rag_query_service import RagQueryService
from services.rag_types import RagQueryResult
from utils.config import AppConfig, load_config

from providers.openai_chat_provider import OpenAIChatProvider
from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
from services.retrieval.runtime_manager import RetrievalBackendManager


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_project_path(config: AppConfig, p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return _project_root() / path


def build_rag_query_service_for_eval(config: AppConfig) -> RagQueryService:
    """
    Same construction pattern as production RAG (Telegram path), without importing telegram_bot
    (avoids loading pyTelegramBotAPI).
    """
    chroma_dir = _resolve_project_path(config, config.chroma_persist_dir)
    tuning = RetrievalTuningResolver(config)
    manager = RetrievalBackendManager(
        config,
        project_root=_project_root(),
        chroma_persist_directory=chroma_dir,
        tuning_resolver=tuning,
    )
    retrieval = manager.get_retrieval()
    try:
        health = retrieval.healthcheck()
        print(
            "[evaluation] retrieval healthcheck: "
            f"backend={health.backend} ok={health.ok} count={health.collection_count}",
            flush=True,
        )
    except Exception as exc:
        print(f"[evaluation] retrieval healthcheck failed: {exc}", flush=True)
        raise
    chat = OpenAIChatProvider(config)
    return RagQueryService(manager, chat, config, tuning_resolver=tuning)


_RETRIEVAL_DIAG_KEYS = (
        "query_preview",
        "top_k",
        "retrieved_count",
        "filtered_count",
        "relevance_threshold",
        "chunks_missing_score",
        "unique_sources_count",
        "scores",
        "context_chars",
        "fallback_reason",
        "retrieved_chunks",
        "used_chunks_count",
        "retrieval_latency_ms",
        "embedding_model",
        "chroma_collection",
        "active_backend",
        "retrieval_backend",
        "active_collection_count",
        "retrieval_readiness",
        "retrieval_cache_hit",
        "retrieval_cache_key_hash_prefix",
        "retrieval_cache_fingerprint_backend",
        "retrieved_duplicate_count",
        "retrieval_dedupe_applied",
        "retrieval_vector_hits_raw",
        "retrieval_ready_query",
        "best_distance",
)

_GENERATION_DIAG_KEYS = (
        "llm_latency_ms",
        "rag_pipeline_wall_ms",
        "llm_provider",
        "llm_model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
)


def split_log_details_to_blobs(
    details: dict[str, Any], *, wall_ms: int | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split ``processing_logs.details`` (RAG) into evaluation_item JSONB columns."""
    skip = frozenset({"user_input", "answer_text", "route", "downstream_route", "mode"})
    ret: dict[str, Any] = {
        k: details[k] for k in _RETRIEVAL_DIAG_KEYS if k in details and k not in skip
    }
    gen: dict[str, Any] = {k: details[k] for k in _GENERATION_DIAG_KEYS if k in details}
    if wall_ms is not None:
        gen["wall_ms_client"] = int(wall_ms)
    rpm = details.get("rag_pipeline_wall_ms")
    if rpm is not None and "rag_pipeline_wall_ms_diag" not in gen:
        try:
            gen["rag_pipeline_wall_ms_diag"] = int(rpm)
        except (TypeError, ValueError):
            pass
    return ret, gen


def diagnostics_to_blobs(
    result: RagQueryResult, *, wall_ms: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split diagnostics into retrieval-heavy vs generation/token fields for JSONB columns."""
    d = result.diagnostics.to_log_details() if result.diagnostics is not None else {}
    ret, gen = split_log_details_to_blobs(d, wall_ms=wall_ms)
    if result.diagnostics is not None and result.diagnostics.rag_pipeline_wall_ms is not None:
        gen["rag_pipeline_wall_ms_diag"] = int(result.diagnostics.rag_pipeline_wall_ms)
    return ret, gen


def duplicate_chunk_rate_from_diag(retrieval: dict[str, Any]) -> float | None:
    raw = retrieval.get("retrieval_vector_hits_raw")
    dup = retrieval.get("retrieved_duplicate_count")
    if raw is None:
        return None
    try:
        r = int(raw)
        if r <= 0:
            return None
        dcnt = int(dup) if dup is not None else 0
        return round(dcnt / r, 6)
    except (TypeError, ValueError):
        return None


def compute_run_summary(
    items: list[dict[str, Any]],
    metrics_by_item: dict[uuid.UUID, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate metrics for compare script and run row (best-effort; nulls for gaps)."""
    n = len(items)
    if n == 0:
        return {
            "item_count": 0,
            "avg_manual_score": None,
            "avg_tokens": None,
            "avg_latency_ms": None,
            "fallback_rate": None,
            "duplicate_chunk_rate": None,
            "retrieved_count_avg": None,
        }

    manual: list[float] = []
    tokens: list[int] = []
    latencies: list[int] = []
    fallbacks = 0
    dup_rates: list[float] = []
    ret_counts: list[int] = []

    for row in items:
        rid = row["id"]
        if not isinstance(rid, uuid.UUID):
            rid = uuid.UUID(str(rid))

        rd = row.get("retrieval_diag") or {}
        if isinstance(rd, str):
            try:
                rd = json.loads(rd)
            except Exception:
                rd = {}
        gd = row.get("generation_diag") or {}
        if isinstance(gd, str):
            try:
                gd = json.loads(gd)
            except Exception:
                gd = {}

        tt = gd.get("total_tokens")
        if tt is not None:
            try:
                tokens.append(int(tt))
            except (TypeError, ValueError):
                pass

        lt = row.get("latency_ms_total")
        if lt is not None:
            try:
                latencies.append(int(lt))
            except (TypeError, ValueError):
                pass

        fr = rd.get("fallback_reason")
        if fr and str(fr).strip().lower() not in ("none", ""):
            fallbacks += 1

        dr = duplicate_chunk_rate_from_diag(rd if isinstance(rd, dict) else {})
        if dr is not None:
            dup_rates.append(dr)

        rc = rd.get("retrieved_count")
        if rc is not None:
            try:
                ret_counts.append(int(rc))
            except (TypeError, ValueError):
                pass

        for m in metrics_by_item.get(rid, []):
            if m.get("metric_key") == "manual.overall" and m.get("metric_value_numeric") is not None:
                try:
                    manual.append(float(m["metric_value_numeric"]))
                except (TypeError, ValueError):
                    pass

    def avg(xs: list[float | int]) -> float | None:
        if not xs:
            return None
        return round(sum(xs) / len(xs), 4)

    return {
        "item_count": n,
        "avg_manual_score": avg(manual) if manual else None,
        "avg_tokens": avg(tokens) if tokens else None,
        "avg_latency_ms": avg(latencies) if latencies else None,
        "fallback_rate": round(fallbacks / n, 6) if n else None,
        "duplicate_chunk_rate": avg(dup_rates) if dup_rates else None,
        "retrieved_count_avg": avg(ret_counts) if ret_counts else None,
    }


def execute_run(run_id: uuid.UUID) -> dict[str, Any]:
    """
    Load run + dataset items, call ``RagQueryService.answer`` per query, persist items + summary.
    Does not touch Telegram or ``processing_logs``.
    """
    repo = EvaluationRepository()
    config = load_config()
    rag = build_rag_query_service_for_eval(config)

    with get_connection() as conn:
        run = repo.get_run(conn, run_id=run_id)
        if not run:
            raise ValueError(f"run not found: {run_id}")
        st = str(run.get("status") or "")
        if st == "running":
            raise ValueError("run is already marked running")
        if st == "completed":
            raise ValueError("run already completed; create a new run to re-execute")

        snap = run.get("config_snapshot") or {}
        if isinstance(snap, str):
            import json

            snap = json.loads(snap)
        top_k = snap.get("top_k")
        if top_k is None:
            top_k = config.rag_top_k
        top_k = int(top_k)

        items = repo.list_dataset_items(conn, dataset_id=run["dataset_id"])
        if not items:
            raise ValueError("dataset has no items")

        repo.update_run_status(conn, run_id=run_id, status="running", started=True)
        conn.commit()

        for row in items:
            q = str(row["query_text"] or "").strip()
            ord_ = int(row["ordinal"])
            ds_item_id = row["id"]
            t0 = time.monotonic()
            try:
                result = rag.answer(q, top_k=top_k, conversation_history=None)
                wall_ms = int((time.monotonic() - t0) * 1000)
                ret_b, gen_b = diagnostics_to_blobs(result, wall_ms=wall_ms)
                repo.insert_item(
                    conn,
                    run_id=run_id,
                    dataset_item_id=ds_item_id,
                    ordinal=ord_,
                    query_text=q,
                    status="ok",
                    error_text=None,
                    answer_text=(result.answer or "").strip() or None,
                    retrieval_diag=ret_b,
                    generation_diag=gen_b,
                    latency_ms_total=wall_ms,
                )
            except Exception as exc:
                wall_ms = int((time.monotonic() - t0) * 1000)
                repo.insert_item(
                    conn,
                    run_id=run_id,
                    dataset_item_id=ds_item_id,
                    ordinal=ord_,
                    query_text=q,
                    status="error",
                    error_text=f"{type(exc).__name__}: {exc}"[:4000],
                    answer_text=None,
                    retrieval_diag={},
                    generation_diag={"wall_ms_client": wall_ms},
                    latency_ms_total=wall_ms,
                )
            conn.commit()

        loaded = repo.list_items_for_run(conn, run_id=run_id)
        mids: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for m in repo.list_metrics_for_run(conn, run_id=run_id):
            iid = m.get("item_id")
            if iid is None:
                continue
            if not isinstance(iid, uuid.UUID):
                iid = uuid.UUID(str(iid))
            mids.setdefault(iid, []).append(dict(m))

        summary = compute_run_summary(loaded, mids)
        summary["config_snapshot_effective"] = {
            "top_k": top_k,
            "note": "backend resolved at worker process from env/DB tuning",
        }
        repo.update_run_status(
            conn,
            run_id=run_id,
            status="completed",
            run_summary=summary,
            finished=True,
        )
        conn.commit()
        return summary
