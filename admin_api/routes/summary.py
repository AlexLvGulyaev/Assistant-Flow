from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from admin_api.deps import get_admin_service
from admin_api.schemas.summary import SummaryResponse
from admin_api.security.deps import require_permission
from services.security.rbac import PERM_DOCUMENTS_READ

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary", response_model=SummaryResponse)
def api_summary(
    hours: int = Query(
        24,
        ge=1,
        le=24 * 365,
        description="Rolling window in hours (aligned with dashboard stats queries).",
    ),
    _principal=Depends(require_permission(PERM_DOCUMENTS_READ)),
) -> SummaryResponse:
    svc = get_admin_service()
    payload = svc.get_summary_payload(hours=hours)
    return SummaryResponse(**payload)
