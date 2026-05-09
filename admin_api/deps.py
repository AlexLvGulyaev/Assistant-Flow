from __future__ import annotations

import json
import os
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
        "database_url_configured": bool((os.getenv("DATABASE_URL") or "").strip()),
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


def truncate_details(details: Any, *, max_len: int = 4000) -> Any:
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
    return {"_truncated": True, "preview": raw[: max_len - 24] + "…(truncated)"}


def log_row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details")
    dd: dict[str, Any] = details if isinstance(details, dict) else {}
    route = str(dd.get("route") or "").strip() or None
    mode = str(dd.get("mode") or "").strip() or None
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
        "details": truncate_details(details),
        "error_text": err_out,
    }
