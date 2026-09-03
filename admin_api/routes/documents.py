from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from admin_api.deps import get_admin_service, log_row_to_entry
from admin_api.security.deps import require_permission
from services.retrieval_security.principal_bridge import retrieval_security_from_principal
from services.retrieval_security.visibility import (
    document_visible_to_context,
    filter_documents_by_retrieval_context,
)
from services.security.audit_service import get_audit_service
from services.security.principal import PrincipalContext
from services.security.rbac import (
    PERM_DOCUMENTS_READ,
    PERM_DOCUMENTS_REINDEX,
    PERM_DOCUMENTS_WRITE,
)

router = APIRouter(prefix="/api", tags=["documents"])

_DOCS_CAP = 400
_LOGS_CAP = 500


def _live_active_index_chunk_count(
    kb: Any, retrieval_ops: dict[str, Any]
) -> int | None:
    """Same source as RS/RAG: active backend health collection_count."""
    raw = retrieval_ops.get("active_collection_count")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    try:
        return int(kb.collection_count)
    except (TypeError, ValueError):
        return None


def _role_scope_documents_aggregates(
    items: list[dict[str, Any]],
    *,
    role_scoped: bool,
    kb: Any,
    retrieval_ops: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Documents list aggregates aligned with Retrieval Settings / RAG.

    Primary chunk total: live ``active_collection_count`` from the active vector
    backend (Weaviate/Chroma/FAISS) — never a hardcoded or postgres-corpus sum.

    Role-scoped principals: hide postgres corpus totals that can leak hidden
    restricted documents; index count still comes from the active backend probe.
    """
    live_n = _live_active_index_chunk_count(kb, retrieval_ops)
    backend = kb.active_retrieval_backend
    index_scope = "active_backend"

    visible_aggregate: dict[str, Any] = {
        "documents_count": len(items),
        "scope": "role_visible" if role_scoped else "corpus",
    }

    scoped_retrieval_ops = {
        **retrieval_ops,
        "active_collection_count": live_n,
        "collection_count_scope": index_scope,
    }

    if not role_scoped:
        pg_sum = kb.postgres_chunks_sum
        vector_n = kb.collection_count
        global_mismatch = (
            kb.postgres_available
            and pg_sum is not None
            and live_n is not None
            and pg_sum != live_n
        )
        global_index_sync = {
            "chroma_collection_chunks": vector_n,
            "vector_index_chunks": kb.vector_index_chunk_count or vector_n,
            "active_retrieval_backend": backend,
            "postgres_chunks_sum_active_versions": pg_sum,
            "postgres_available": kb.postgres_available,
            "global_chunks_mismatch": global_mismatch,
            "collection_count_scope": index_scope,
            "active_index_chunk_count": live_n,
        }
        return global_index_sync, scoped_retrieval_ops, visible_aggregate

    global_index_sync = {
        "chroma_collection_chunks": live_n,
        "vector_index_chunks": live_n,
        "active_retrieval_backend": backend,
        "postgres_chunks_sum_active_versions": None,
        "postgres_available": kb.postgres_available,
        "global_chunks_mismatch": None,
        "collection_count_scope": index_scope,
        "active_index_chunk_count": live_n,
    }
    return global_index_sync, scoped_retrieval_ops, visible_aggregate


def _preprocessing_public_from_upload(details: dict[str, Any]) -> dict[str, Any] | None:
    """Subset of upload log for Documents UI (no secrets)."""
    pre = details.get("preprocessing")
    if not isinstance(pre, dict) or not pre:
        return None
    status = str(pre.get("status") or ("ok" if pre.get("extraction_success") else "error"))
    ob = details.get("original_size_bytes")
    if ob is None:
        ob = details.get("size_bytes")
    out: dict[str, Any] = {
        "status": status,
        "original_format": pre.get("original_format"),
        "original_bytes": ob,
        "cleaned_bytes": details.get("cleaned_size_bytes", details.get("cleaned_bytes")),
        "removed_line_count": pre.get("removed_line_count"),
        "original_upload_filename": details.get("original_upload_filename"),
        "indexed_target_filename": details.get("indexed_target_filename"),
    }
    if pre.get("preview_raw"):
        out["preview_raw"] = pre.get("preview_raw")
    if pre.get("preview_cleaned"):
        out["preview_cleaned"] = pre.get("preview_cleaned")
    if pre.get("error"):
        out["error"] = pre.get("error")
    if pre.get("extractor") is not None:
        out["extractor"] = pre.get("extractor")
    if pre.get("page_count") is not None:
        out["page_count"] = pre.get("page_count")
    if pre.get("extracted_characters") is not None:
        out["extracted_characters"] = pre.get("extracted_characters")
    return out


@router.get("/documents")
def api_documents(
    limit: int = Query(default=200, ge=1, le=_DOCS_CAP),
    principal: PrincipalContext = Depends(require_permission(PERM_DOCUMENTS_READ)),
) -> dict[str, Any]:
    svc = get_admin_service()
    docs_raw = svc.get_documents_with_versions()
    docs_limited = docs_raw[: min(limit, _DOCS_CAP)]
    sec_ctx = retrieval_security_from_principal(principal)
    if sec_ctx is not None and not sec_ctx.is_fully_unrestricted():
        docs_limited = filter_documents_by_retrieval_context(docs_limited, sec_ctx)

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
            "admin_document_uploaded_raw",
            "document_preprocessing_started",
            "document_preprocessing_done",
            "document_preprocessing_error",
            "document_processed_artifact_saved",
            "document_compatibility_file_written",
            "document_indexing_started",
            "document_indexing_done",
            "document_indexing_error",
            "document_upload_pipeline_done",
            "admin_document_uploaded",
            "document_edit_started",
            "document_edit_saved",
            "document_reindex_started",
            "document_reindex_done",
            "document_reindex_error",
            "admin_document_reindex_started",
            "admin_document_reindex_done",
            "admin_document_reindex_error",
        )
    ][:120]

    timeline_by_file: dict[str, dict[str, Any]] = {}
    for ev in docs_timeline:
        details = ev.get("details") if isinstance(ev.get("details"), dict) else {}
        keys = [
            str((details or {}).get("indexed_target_filename") or "").strip().lower(),
            str((details or {}).get("filename") or "").strip().lower(),
            str((details or {}).get("original_upload_filename") or "").strip().lower(),
        ]
        for key in keys:
            if key and key not in timeline_by_file:
                timeline_by_file[key] = ev

    preprocess_by_indexed: dict[str, dict[str, Any]] = {}
    for ev in logs_entries:
        st = str(ev.get("stage") or "")
        if st not in ("document_upload_pipeline_done", "admin_document_uploaded"):
            continue
        details = ev.get("details") if isinstance(ev.get("details"), dict) else {}
        pub = _preprocessing_public_from_upload(details)
        if pub is None:
            continue
        itn = str(details.get("indexed_target_filename") or "").strip().lower()
        fn = str(details.get("filename") or "").strip().lower()
        ouf = str(details.get("original_upload_filename") or "").strip().lower()
        for key in (itn, fn, ouf):
            if key and key not in preprocess_by_indexed:
                preprocess_by_indexed[key] = pub

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
        preprocessing = preprocess_by_indexed.get(filename.lower())
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
                "preprocessing": preprocessing,
                "document_visibility": str(row.get("document_visibility") or "unspecified"),
            },
        )

    kb = svc.get_knowledge_base_status()
    role_scoped = sec_ctx is not None and not sec_ctx.is_fully_unrestricted()
    retrieval_ops = svc.get_retrieval_platform_compact()
    global_index_sync, retrieval_ops, visible_aggregate = _role_scope_documents_aggregates(
        items,
        role_scoped=role_scoped,
        kb=kb,
        retrieval_ops=retrieval_ops,
    )

    return {
        "count": len(items),
        "limit": min(limit, _DOCS_CAP),
        "items": items,
        "embedding_model": getattr(svc.app_config, "openai_embedding_model", None),
        "visible_aggregate": visible_aggregate,
        "global_index_sync": global_index_sync,
        "retrieval_operational": retrieval_ops,
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


class DocumentTextEditRequest(BaseModel):
    text: str = Field(default="", max_length=12_000_000)
    editor_source: str = Field(default="admin_ui", max_length=64)


@router.post("/documents/upload")
async def api_documents_upload(
    request: Request,
    file: UploadFile = File(...),
    visibility: str = Form(default="internal"),
    principal: PrincipalContext = Depends(require_permission(PERM_DOCUMENTS_WRITE)),
) -> dict[str, Any]:
    svc = get_admin_service()
    max_bytes = svc.upload_max_bytes()
    # Heavy RAG safeguard: не читаем произвольно большой файл целиком в RAM.
    # file.size известен заранее (multipart); на всякий случай чтение тоже ограничено.
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {declared} bytes (limit {max_bytes}).",
        )
    chunks: list[bytes] = []
    received = 0
    while True:
        part = await file.read(1024 * 1024)
        if not part:
            break
        received += len(part)
        if received > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: >{max_bytes} bytes (ADMIN_UPLOAD_MAX_MB).",
            )
        chunks.append(part)
    raw = b"".join(chunks)
    name = file.filename or "upload.txt"
    try:
        result = svc.upload_txt_and_index(name, raw, document_visibility=visibility)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="documents.upload",
        principal=principal,
        request=request,
        target_type="document",
        target_id=str(result.get("document_id") or ""),
        details={"filename": name, "visibility": visibility},
    )
    return result


@router.post("/documents/reindex")
def api_documents_reindex(
    request: Request,
    body: ReindexRequest,
    principal: PrincipalContext = Depends(require_permission(PERM_DOCUMENTS_REINDEX)),
) -> dict[str, Any]:
    svc = get_admin_service()
    scope = (body.scope or "document").strip().lower()
    if scope == "all":
        report = svc.run_reindex()
        result = {
            "scope": "all",
            "success": report.success,
            "error": report.error_message,
            "chunks_created": report.chunks_created,
            "collection_count": report.collection_count,
            "files_indexed_ok": report.files_indexed_ok,
            "files_found": report.files_found,
        }
        get_audit_service().log_privileged_action(
            action="documents.reindex",
            principal=principal,
            request=request,
            target_type="corpus",
            details={"scope": "all", "success": report.success},
        )
        return result
    if scope != "document":
        raise HTTPException(status_code=400, detail="scope must be 'all' or 'document'")
    did = (body.document_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="document_id required for scope=document")
    try:
        uid = uuid.UUID(did)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid document_id") from exc
    out = svc.reindex_document_file(uid)
    get_audit_service().log_privileged_action(
        action="documents.reindex",
        principal=principal,
        request=request,
        target_type="document",
        target_id=did,
        details={"scope": "document"},
    )
    return out


@router.get("/documents/{document_id}/detail")
def api_document_detail(
    request: Request,
    document_id: str,
    version_number: int | None = Query(default=None, ge=1),
    full_canonical_text: bool = Query(default=False),
    full_preprocessing_raw: bool = Query(default=False),
    principal: PrincipalContext = Depends(require_permission(PERM_DOCUMENTS_READ)),
) -> dict[str, Any]:
    try:
        uid = uuid.UUID(document_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid document_id") from exc
    svc = get_admin_service()
    sec_ctx = retrieval_security_from_principal(principal)
    if sec_ctx is not None and not sec_ctx.is_fully_unrestricted():
        doc_vis = svc.get_document_visibility(uid)
        meta = {"visibility": doc_vis, "document_visibility": doc_vis}
        if not document_visible_to_context(meta, sec_ctx):
            get_audit_service().log_document_detail_visibility_denied(
                principal=principal,
                request=request,
                document_id=str(uid),
                document_visibility=doc_vis,
                retrieval_role=sec_ctx.role,
                retrieval_scope=sec_ctx.retrieval_scope,
            )
            # 404: не раскрываем факт существования restricted doc (как в list filter)
            raise HTTPException(status_code=404, detail="document not found")
    bundle = svc.get_document_detail_bundle(
        uid,
        version_number=version_number,
        include_full_canonical_text=full_canonical_text,
        include_full_preprocessing_raw=full_preprocessing_raw,
    )
    err = bundle.get("error")
    if err == "not_found":
        raise HTTPException(status_code=404, detail="document not found")
    if err == "postgres_unavailable":
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    if err == "load_failed":
        msg = str(bundle.get("message") or "load_failed")
        code = 413 if "too large" in msg.lower() else 500
        raise HTTPException(status_code=code, detail=msg)

    raw_rows = bundle.pop("timeline_rows", [])
    timeline = [log_row_to_entry(r) for r in raw_rows]
    # chronological for lifecycle reading (oldest first)
    timeline.sort(key=lambda e: str(e.get("created_at") or ""))
    bundle["timeline"] = timeline
    return bundle


@router.post("/documents/{document_id}/edit-text")
def api_document_edit_text(
    request: Request,
    document_id: str,
    body: DocumentTextEditRequest,
    principal: PrincipalContext = Depends(require_permission(PERM_DOCUMENTS_WRITE)),
) -> dict[str, Any]:
    try:
        uid = uuid.UUID(document_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid document_id") from exc
    svc = get_admin_service()
    result = svc.save_canonical_document_text_edit(
        uid,
        new_text=body.text,
        editor_source=body.editor_source,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=str(result.get("error") or "edit failed"),
        )
    get_audit_service().log_privileged_action(
        action="documents.edit_text",
        principal=principal,
        request=request,
        target_type="document",
        target_id=document_id,
        details={
            "editor_source": body.editor_source,
            "edited_characters": result.get("edited_characters"),
        },
    )
    return result


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return None
