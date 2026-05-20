"""Security audit API (P9.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from admin_api.security.deps import require_permission
from services.security.audit_service import get_audit_service
from services.security.rbac import PERM_AUDIT_READ

router = APIRouter(prefix="/api/security/audit", tags=["security-audit"])


@router.get("/recent")
def api_audit_recent(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal_email: str | None = Query(default=None),
    since_hours: int | None = Query(default=24, ge=1, le=24 * 90),
    _principal=Depends(require_permission(PERM_AUDIT_READ)),
) -> dict:
    items = get_audit_service().get_recent(
        limit=limit,
        offset=offset,
        event_type=event_type,
        status=status,
        principal_email=principal_email,
        since_hours=since_hours,
    )
    return {"limit": limit, "offset": offset, "count": len(items), "items": items}


@router.get("/summary")
def api_audit_summary(
    since_hours: int = Query(default=24, ge=1, le=24 * 90),
    _principal=Depends(require_permission(PERM_AUDIT_READ)),
) -> dict:
    return get_audit_service().get_summary(since_hours=since_hours)
