from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

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
        if str(e.get("stage") or "")
        in (
            "admin_document_uploaded",
            "admin_document_reindex_started",
            "admin_document_reindex_done",
            "admin_document_reindex_error",
        )
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

    kb = svc.get_knowledge_base_status()
    pg_sum = kb.postgres_chunks_sum
    vector_n = kb.collection_count
    global_mismatch = (
        kb.postgres_available
        and pg_sum is not None
        and pg_sum != vector_n
    )

    return {
        "count": len(items),
        "limit": min(limit, _DOCS_CAP),
        "items": items,
        "embedding_model": getattr(svc.app_config, "openai_embedding_model", None),
        "global_index_sync": {
            "chroma_collection_chunks": vector_n,
            "vector_index_chunks": kb.vector_index_chunk_count or vector_n,
            "active_retrieval_backend": kb.active_retrieval_backend,
            "postgres_chunks_sum_active_versions": pg_sum,
            "postgres_available": kb.postgres_available,
            "global_chunks_mismatch": global_mismatch,
        },
        "observability": {
            "reindex_available": True,
            "last_reindex_event": reindex_events[0] if reindex_events else None,
            "admin_operations": admin_ops,
            "timeline_events": docs_timeline,
        },
    }


class ReindexRequest(BaseModel):
    scope: str = Field(default="document", description="'all' or 'document'")
    document_id: str | None = Field(default=None)


@router.post("/documents/upload")
async def api_documents_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    svc = get_admin_service()
    raw = await file.read()
    name = file.filename or "upload.txt"
    try:
        result = svc.upload_txt_and_index(name, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/documents/reindex")
def api_documents_reindex(body: ReindexRequest) -> dict[str, Any]:
    svc = get_admin_service()
    scope = (body.scope or "document").strip().lower()
    if scope == "all":
        report = svc.run_reindex()
        return {
            "scope": "all",
            "success": report.success,
            "error": report.error_message,
            "chunks_created": report.chunks_created,
            "collection_count": report.collection_count,
            "files_indexed_ok": report.files_indexed_ok,
            "files_found": report.files_found,
        }
    if scope != "document":
        raise HTTPException(status_code=400, detail="scope must be 'all' or 'document'")
    did = (body.document_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="document_id required for scope=document")
    try:
        uid = uuid.UUID(did)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid document_id") from exc
    return svc.reindex_document_file(uid)


@router.get("/documents/{document_id}/detail")
def api_document_detail(
    document_id: str,
    version_number: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    try:
        uid = uuid.UUID(document_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid document_id") from exc
    svc = get_admin_service()
    bundle = svc.get_document_detail_bundle(uid, version_number=version_number)
    err = bundle.get("error")
    if err == "not_found":
        raise HTTPException(status_code=404, detail="document not found")
    if err == "postgres_unavailable":
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    if err == "load_failed":
        raise HTTPException(
            status_code=500,
            detail=str(bundle.get("message") or "load_failed"),
        )

    raw_rows = bundle.pop("timeline_rows", [])
    timeline = [log_row_to_entry(r) for r in raw_rows]
    # chronological for lifecycle reading (oldest first)
    timeline.sort(key=lambda e: str(e.get("created_at") or ""))
    bundle["timeline"] = timeline
    return bundle


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None
