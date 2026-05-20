"""Admin API: retrieval backend overview, active backend (P6.10), tuning (P6.12)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from admin_api.deps import get_admin_service
from admin_api.security.deps import require_permission
from services.security.audit_service import get_audit_service
from services.security.principal import PrincipalContext
from services.security.rbac import PERM_RETRIEVAL_ADMIN, PERM_RETRIEVAL_READ

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


class ActiveBackendBody(BaseModel):
    backend: str = Field(..., description="chroma | faiss | weaviate")


class TuningPutBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rag_top_k: int | None = None
    rag_max_distance: float | None = None
    rag_answer_max_tokens: int | None = None
    rag_retrieval_timeout: int | float | None = None
    rag_embedding_request_timeout: int | float | None = None
    rag_chunk_size: int | None = None
    rag_chunk_overlap: int | None = None
    enable_retrieval_cache: bool | None = Field(
        default=None,
        description="Retrieval cache ON/OFF; stored in platform_settings.retrieval_tuning",
    )


def _tuning_put_patch_from_body(body: TuningPutBody) -> dict[str, Any]:
    """
    Fields present in the JSON body only (exclude_unset).
    Preserves explicit ``false`` for booleans — must not use truthiness filters.
    """
    patch: dict[str, Any] = {}
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        patch[key] = value
    return patch


@router.get("/overview")
def api_retrieval_overview(
    _principal=Depends(require_permission(PERM_RETRIEVAL_READ)),
) -> dict[str, Any]:
    svc = get_admin_service()
    return svc.get_retrieval_overview()


@router.put("/active-backend")
def api_retrieval_active_backend(
    request: Request,
    body: ActiveBackendBody,
    principal: PrincipalContext = Depends(require_permission(PERM_RETRIEVAL_ADMIN)),
) -> dict[str, Any]:
    svc = get_admin_service()
    try:
        out = svc.set_active_retrieval_backend((body.backend or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="retrieval.backend.switch",
        principal=principal,
        request=request,
        target_type="retrieval_backend",
        details={"backend": (body.backend or "").strip()},
    )
    return out


@router.get("/tuning")
def api_retrieval_tuning_get(
    _principal=Depends(require_permission(PERM_RETRIEVAL_READ)),
) -> dict[str, Any]:
    return get_admin_service().get_retrieval_tuning()


@router.put("/tuning")
def api_retrieval_tuning_put(
    request: Request,
    body: TuningPutBody,
    principal: PrincipalContext = Depends(require_permission(PERM_RETRIEVAL_ADMIN)),
) -> dict[str, Any]:
    patch = _tuning_put_patch_from_body(body)
    if not patch:
        raise HTTPException(
            status_code=400,
            detail="empty body: provide at least one tuning field",
        )
    svc = get_admin_service()
    try:
        out = svc.put_retrieval_tuning(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="retrieval.settings.update",
        principal=principal,
        request=request,
        target_type="retrieval_tuning",
        details={"patch_keys": sorted(patch.keys())},
    )
    return out


@router.delete("/tuning")
def api_retrieval_tuning_delete(
    request: Request,
    principal: PrincipalContext = Depends(require_permission(PERM_RETRIEVAL_ADMIN)),
) -> dict[str, Any]:
    svc = get_admin_service()
    try:
        out = svc.delete_retrieval_tuning()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="retrieval.settings.delete",
        principal=principal,
        request=request,
        target_type="retrieval_tuning",
    )
    return out
