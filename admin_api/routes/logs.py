from __future__ import annotations

from fastapi import APIRouter, Query

from admin_api.deps import get_admin_service, log_row_to_entry

router = APIRouter(prefix="/api", tags=["logs"])

_LOG_CAP = 200


@router.get("/logs/recent")
def api_logs_recent(limit: int = Query(default=50, ge=1, le=_LOG_CAP)) -> dict:
    svc = get_admin_service()
    rows = svc.get_recent_logs(limit=min(limit, _LOG_CAP))
    return {
        "limit": min(limit, _LOG_CAP),
        "count": len(rows),
        "items": [log_row_to_entry(r) for r in rows],
    }
