from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from admin_api.deps import get_admin_service, log_row_to_entry
from admin_api.security.deps import require_permission
from services.security.principal import PrincipalContext
from services.security.rbac import PERM_LOGS_READ

router = APIRouter(prefix="/api", tags=["logs"])

_LOG_CAP = 2000


@router.get("/logs/recent")
def api_logs_recent(
    limit: int = Query(default=50, ge=1, le=_LOG_CAP),
    offset: int = Query(default=0, ge=0),
    since_hours: int | None = Query(default=None, ge=1, le=24 * 365),
    principal: PrincipalContext = Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    svc = get_admin_service()
    rows = svc.get_recent_logs(
        limit=min(limit, _LOG_CAP),
        offset=offset,
        since_hours=since_hours,
    )
    allow_forensic = principal.has_permission("logs:forensic")
    return {
        "limit": min(limit, _LOG_CAP),
        "offset": offset,
        "count": len(rows),
        "items": [
            log_row_to_entry(r, allow_forensic=allow_forensic) for r in rows
        ],
    }
