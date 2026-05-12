from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from services.admin_service import AdminService
from services.healthcheck_service import HealthSnapshot, run_system_healthchecks
from utils.config import AppConfig, load_config


@lru_cache(maxsize=1)
def get_admin_service() -> AdminService:
    return AdminService()


def snapshot_to_public_dict(snap: HealthSnapshot) -> dict[str, Any]:
    """Serialize health snapshot without secrets."""
    out: dict[str, Any] = {
        "status": snap.status,
    }
    if snap.latency_ms is not None:
        out["latency_ms"] = snap.latency_ms
    if snap.detail:
        out["detail"] = snap.detail
    if snap.error_message:
        out["error_message"] = snap.error_message[:500]
    if snap.extras:
        safe_extras = {
            k: v
            for k, v in snap.extras.items()
            if k in ("collection_count",) or isinstance(v, (int, float, bool, str))
        }
        if safe_extras:
            out["extras"] = safe_extras
    return out


def config_readiness_summary(cfg: AppConfig) -> dict[str, Any]:
    """Non-secret flags for operators / probes."""
    return {
        "database_url_configured": bool((cfg.database_url or "").strip()),
        "chroma_use_http": cfg.chroma_use_http,
        "chroma_host": cfg.chroma_host,
        "chroma_port": cfg.chroma_port,
        "image_provider": cfg.image_provider,
        "audio_enabled": cfg.audio_enabled,
        "stt_provider": cfg.stt_provider,
        "tts_provider": cfg.tts_provider,
        "asset_storage_backend": cfg.asset_storage_backend,
        "asset_storage_dir": cfg.asset_storage_dir,
        "rag_documents_dir": cfg.rag_documents_dir,
        "chroma_persist_dir": cfg.chroma_persist_dir,
        "gigachat_configured": bool((cfg.gigachat_auth_key or "").strip()),
        "openai_configured": bool((cfg.openai_api_key or "").strip()),
        "proxy_configured": bool((cfg.proxy_api_key or "").strip()),
    }


def run_health_report() -> tuple[AppConfig, Any]:
    cfg = load_config()
    svc = get_admin_service()
    rep = run_system_healthchecks(
        cfg,
        chroma_persist_path=str(svc.chroma_persist_path),
    )
    return cfg, rep


# Keys operators/RAG UI rely on; must survive API truncation of heavy payloads.
_PRESERVED_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "route",
        "downstream_route",
        "mode",
        "modality",
        "user_input_kind",
        "system_output_kind",
        "user_text",
        "list_user_preview",
        "intake_image_asset_ref",
        "input_asset_ref",
        "input_asset_filename",
        "input_asset_content_type",
        "input_asset_size_bytes",
        "input_asset_sha256",
        "caption_preview",
        "recognized_text_preview",
        "recognized_text_length",
        "ocr_input_diagnostics",
        "answer_preview",
        "output_text",
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
        "used_chunks_count",
        "best_distance",
        "retrieval_latency_ms",
        "llm_latency_ms",
        "response_latency_ms",
        "vision_call_latency_ms",
        "usage_not_returned_by_provider_wrapper",
        "rag_pipeline_wall_ms",
        "llm_provider",
        "llm_model",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "embedding_model",
        "chroma_collection",
        "latency_ms",
        "duration_ms",
        "elapsed_ms",
        "user_input",
        "query",
        "prompt",
        "prompt_tokens",
        "completion_tokens",
        "token_usage",
        "usage",
    }
)


def _slim_details_for_payload(details: dict[str, Any]) -> dict[str, Any]:
    """Shrink heavy RAG fields while keeping telemetry & summaries for the Admin UI."""
    out: dict[str, Any] = {}
    for k in _PRESERVED_DETAIL_KEYS:
        if k in details:
            out[k] = details[k]

    qp = details.get("query_preview")
    if isinstance(qp, str) and qp:
        out["query_preview"] = qp if len(qp) <= 400 else qp[:397] + "…"

    at = details.get("answer_text")
    if isinstance(at, str) and at:
        out["answer_text"] = at if len(at) <= 1500 else at[:1497] + "…"

    rtp = details.get("recognized_text_preview")
    if isinstance(rtp, str) and rtp:
        out["recognized_text_preview"] = rtp if len(rtp) <= 1500 else rtp[:1497] + "…"

    ut = details.get("user_text")
    if isinstance(ut, str) and ut:
        out["user_text"] = ut if len(ut) <= 800 else ut[:797] + "…"

    chunks = details.get("retrieved_chunks")
    if isinstance(chunks, list):
        slim_chunks: list[dict[str, Any]] = []
        for raw_c in chunks[:18]:
            if not isinstance(raw_c, dict):
                continue
            prev = raw_c.get("text_preview")
            ps = str(prev) if prev is not None else ""
            slim_chunks.append(
                {
                    "source": raw_c.get("source"),
                    "score": raw_c.get("score"),
                    "passed_filter": raw_c.get("passed_filter"),
                    "text_preview": ps if len(ps) <= 96 else ps[:93] + "…",
                }
            )
        out["retrieved_chunks"] = slim_chunks

    for passthrough in ("answer", "rag_answer", "details"):
        if passthrough in details and passthrough not in out:
            v = details[passthrough]
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[passthrough] = v

    return out


def truncate_details(details: Any, *, max_len: int = 4000) -> Any:
    """
    Bound JSON size for /api/logs responses.

    RAG ``rag_answer_done`` rows can exceed ``max_len`` due to ``retrieved_chunks`` and
    ``answer_text``. Previously the entire ``details`` object was replaced with a short
    preview string, which dropped structured telemetry (latency, tokens, etc.) and made
    the React RAG page show only gaps (н/л).
    """
    if details is None:
        return None
    if not isinstance(details, dict):
        s = str(details)
        return s[:500] if len(s) > 500 else s

    try:
        raw = json.dumps(details, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(details)
        return s[:500] if len(s) > 500 else s
    if len(raw) <= max_len:
        return details

    slim = _slim_details_for_payload(details)
    try:
        raw_slim = json.dumps(slim, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        raw_slim = "{}"
    if len(raw_slim) <= max_len:
        return slim

    minimal = {k: slim[k] for k in slim if k in _PRESERVED_DETAIL_KEYS}
    if isinstance(slim.get("answer_text"), str):
        at = slim["answer_text"]
        minimal["answer_text"] = at[:400] + ("…" if len(at) > 400 else "")
    if isinstance(slim.get("recognized_text_preview"), str):
        rp = slim["recognized_text_preview"]
        minimal["recognized_text_preview"] = rp[:400] + ("…" if len(rp) > 400 else "")
    try:
        raw_min = json.dumps(minimal, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        raw_min = "{}"
    if len(raw_min) <= max_len:
        return minimal

    no_chunks = {k: v for k, v in minimal.items() if k != "retrieved_chunks"}
    try:
        raw_nc = json.dumps(no_chunks, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        raw_nc = "{}"
    if len(raw_nc) <= max_len:
        return no_chunks

    return {"_truncated": True, "preview": raw[: max_len - 24] + "…(truncated)"}


_OCR_PIPELINE_STAGES: frozenset[str] = frozenset(
    {
        "image_received",
        "ocr_started",
        "ocr_done",
        "ocr_error",
        "ocr_response_sent",
    }
)


def infer_modality_route(details: Any, *, stage: str | None = None) -> str:
    """
    Normalized modality for React filters (matches RouteFilter on Logs page).

    Centralizes OCR-as-text vs image-generation; avoids substring heuristics
    on the client when ``details`` is truncated in API responses.
    """
    d = details if isinstance(details, dict) else {}
    route = str(d.get("route") or "").strip().lower()
    dr = str(d.get("downstream_route") or "").strip().lower()
    mode = str(d.get("mode") or "").strip().lower()
    st = str(stage or "").strip().lower()

    if route == "vision_ocr" or dr == "vision_ocr" or mode == "ocr":
        return "text"
    if st in _OCR_PIPELINE_STAGES and (mode == "ocr" or route == "vision_ocr" or dr == "vision_ocr"):
        return "text"

    if route in ("rag", "rag_response") or mode == "rag" or st == "rag_answer_done":
        return "rag"
    if mode in ("voice", "audio") or route in ("audio", "voice", "voice_response"):
        return "audio"
    if st.startswith("stt_") or st.startswith("tts_") or st.startswith("voice_") or st.startswith(
        "audio_generation"
    ):
        return "audio"

    if route in ("image_generation", "image", "image_response") or st.startswith("image_generation"):
        return "image"
    if st in ("image_answer_done", "image_provider_done", "image_assets_persisted"):
        return "image"

    if route in ("text", "text_response") or mode == "text" or st == "text_answer_done":
        return "text"

    return "other"


def infer_modality(details: Any, *, stage: str | None = None) -> str | None:
    """High-level modality label for operators (``text`` includes OCR)."""
    mr = infer_modality_route(details, stage=stage)
    if mr == "other":
        return None
    return mr


def log_row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details")
    dd: dict[str, Any] = details if isinstance(details, dict) else {}
    route = str(dd.get("route") or "").strip() or None
    mode = str(dd.get("mode") or "").strip() or None
    st = str(row.get("stage") or "").strip() or None
    modality_route = infer_modality_route(details, stage=st)
    modality = infer_modality(details, stage=st)
    created = row.get("created_at")
    if isinstance(created, datetime):
        created_out = created.astimezone(timezone.utc).isoformat()
    else:
        created_out = created
    err_raw = row.get("error_text")
    err_out = str(err_raw).strip() if err_raw else None
    return {
        "execution_id": str(row.get("execution_id") or "") or None,
        "stage": str(row.get("stage") or "") or None,
        "status": str(row.get("status") or "") or None,
        "created_at": created_out,
        "route": route,
        "mode": mode,
        "modality": modality,
        "modality_route": modality_route,
        "details": truncate_details(details),
        "error_text": err_out,
    }
