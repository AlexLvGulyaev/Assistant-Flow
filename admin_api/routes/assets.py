from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from admin_api.deps import get_admin_service
from admin_api.security.deps import require_permission
from services.security.rbac import PERM_DOCUMENTS_READ

router = APIRouter(prefix="/api/assets", tags=["assets"])
_PREVIEW_ALLOWED_PREFIXES = ("image/", "audio/")


@router.get("/preview")
def api_asset_preview(
    asset_ref: str = Query(..., min_length=4, description="Asset relative ref"),
    _principal=Depends(require_permission(PERM_DOCUMENTS_READ)),
) -> FileResponse:
    svc = get_admin_service()
    try:
        path, content_type = svc.get_media_asset_preview(
            asset_ref,
            allowed_prefixes=_PREVIEW_ALLOWED_PREFIXES,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="asset_not_found") from exc
        raise HTTPException(status_code=400, detail="invalid_asset_ref") from exc
    # filename= без inline даёт Content-Disposition: attachment — HTML5 <audio> часто не играет такой ответ.
    return FileResponse(
        path=path,
        media_type=content_type,
        filename=path.name,
        content_disposition_type="inline",
    )

