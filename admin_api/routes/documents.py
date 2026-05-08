from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from admin_api.deps import get_admin_service, log_row_to_entry

router = APIRouter(prefix="/api", tags=["documents"])

_DOCS_CAP = 400
_LOGS_CAP = 500


@router.get("/documents")
def api_documents(limit: int = Query(default=200, ge=1, le=_DOCS_CAP)) -> dict[str, Any]:
    svc = get_admin_service()
    docs_raw = svc.get_documents_with_versions()
    docs_limited = docs_raw[: min(limit, _DOCS_CAP)]

    # lightweight observability from capped recent logs only
    logs = svc.get_recent_logs(limit=_LOGS_CAP)
    logs_entries = [log_row_to_entry(r) for r in logs]
    reindex_events = [
        e
        for e in logs_entries
        if str(e.get("stage") or "").startswith("admin_reindex_")
    ]
    admin_ops = [
        e
        for e in logs_entries
        if str(e.get("stage") or "").startswith("admin_")
    ][:30]
    docs_timeline = [
        e
        for e in logs_entries
        if str(e.get("stage") or "") in ("admin_document_uploaded",)
    ][:120]

    timeline_by_file: dict[str, dict[str, Any]] = {}
    for ev in docs_timeline:
        details = ev.get("details") if isinstance(ev.get("details"), dict) else {}
        filename = str((details or {}).get("filename") or "").strip()
        if not filename:
            continue
        key = filename.lower()
        if key not in timeline_by_file:
            timeline_by_file[key] = ev

    items: list[dict[str, Any]] = []
    for row in docs_limited:
        filename = str(row.get("filename") or "")
        ext = Path(filename).suffix.lower() or "—"
        status = str(row.get("status") or "unknown").strip().lower()
        active_chunks = int(row.get("active_chunk_count") or 0)
        indexed = status == "indexed" and active_chunks > 0
        badge = (
            "indexed"
            if indexed
            else "error"
            if status in ("failed", "error")
            else "pending"
            if status in ("indexing", "queued", "pending")
            else "missing"
            if status in ("missing", "not_found")
            else "unsupported"
            if status in ("unsupported",)
            else "stale"
            if status in ("stale", "outdated")
            else "pending"
        )
        linked = timeline_by_file.get(filename.lower())
        items.append(
            {
                "document_id": str(row.get("document_id") or ""),
                "filename": filename,
                "extension": ext,
                "status": badge,
                "status_raw": status,
                "active_version": row.get("active_version"),
                "versions_count": int(row.get("versions_count") or 0),
                "chunk_count": active_chunks,
                "last_indexed_at": _to_iso(row.get("last_indexed_at")),
                # graceful degradation: DB summary does not expose file size/mtime/path
                "size_bytes": None,
                "modified_at": None,
                "path_category": None,
                "last_indexing_event": linked,
            }
        )

    return {
        "count": len(items),
        "limit": min(limit, _DOCS_CAP),
        "items": items,
        "observability": {
            "reindex_available": True,
            "last_reindex_event": reindex_events[0] if reindex_events else None,
            "admin_operations": admin_ops,
            "timeline_events": docs_timeline,
        },
    }


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None

