"""Admin API: memory + chat_sessions observability (compact, no raw RAG assembly)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from admin_api.deps import get_memory_observability_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/observability/summary")
def api_memory_observability_summary(
    hours: int = Query(default=24, ge=1, le=24 * 90),
) -> dict:
    svc = get_memory_observability_service()
    return svc.get_summary(hours=hours)


@router.get("/sessions")
def api_memory_sessions_list(
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    svc = get_memory_observability_service()
    return svc.list_sessions(active_only=active_only, limit=limit, offset=offset)


@router.get("/sessions/{session_id}")
def api_memory_session_detail(session_id: str) -> dict:
    svc = get_memory_observability_service()
    detail = svc.get_session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session_not_found_or_db_unavailable")
    return detail
