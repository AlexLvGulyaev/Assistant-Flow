from __future__ import annotations

from fastapi import APIRouter, Query

from admin_api.deps import get_admin_service, log_row_to_entry

router = APIRouter(prefix="/api", tags=["logs"])

_LOG_CAP = 2000


@router.get("/logs/recent")
def api_logs_recent(
    limit: int = Query(default=50, ge=1, le=_LOG_CAP),
    offset: int = Query(default=0, ge=0),
    since_hours: int | None = Query(default=None, ge=1, le=24 * 365),
) -> dict:
    svc = get_admin_service()
    rows = svc.get_recent_logs(
        limit=min(limit, _LOG_CAP),
        offset=offset,
        since_hours=since_hours,
    )
    return {
        "limit": min(limit, _LOG_CAP),
        "offset": offset,
        "count": len(rows),
        "items": [log_row_to_entry(r) for r in rows],
    }
