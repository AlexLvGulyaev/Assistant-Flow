from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from admin_api.security.deps import require_permission
from services.security.audit_service import get_audit_service
from services.security.principal import PrincipalContext
from services.security.rbac import PERM_LOGS_READ, PERM_SETTINGS_WRITE

from admin_api.schemas.evaluation import (
    EvaluationImportBody,
    EvaluationItemPatchBody,
    EvaluationRagasRunBody,
)
from services.evaluation_admin_service import (
    get_rag_turn_detail,
    get_run_detail,
    get_run_metrics_grouped,
    import_turns,
    list_rag_turns,
    list_runs,
    patch_evaluation_item,
    run_ragas,
)

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

_CAP = 200


@router.get("/rag-turns")
def api_evaluation_rag_turns(
    limit: int = Query(default=50, ge=1, le=_CAP),
    since_hours: int = Query(default=24, ge=1, le=24 * 7),
    fallback: str | None = Query(default=None),
    has_ragas_metrics: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    _principal=Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    return list_rag_turns(
        limit=limit,
        since_hours=since_hours,
        fallback=fallback,
        has_ragas_metrics=has_ragas_metrics,
        search=search,
    )


@router.get("/rag-turns/{execution_id}")
def api_evaluation_rag_turn_detail(
    execution_id: str,
    _principal=Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    detail = get_rag_turn_detail(execution_id=execution_id.strip())
    if detail is None:
        raise HTTPException(status_code=404, detail="rag_turn_not_found")
    return detail


@router.post("/import")
def api_evaluation_import(
    request: Request,
    body: EvaluationImportBody,
    principal: PrincipalContext = Depends(require_permission(PERM_SETTINGS_WRITE)),
) -> dict:
    try:
        out = import_turns(
            execution_ids=body.execution_ids,
            dataset=body.dataset,
            run_name=body.run_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="settings.evaluation.import",
        principal=principal,
        request=request,
        details={"count": len(body.execution_ids), "run_name": body.run_name},
    )
    return out


@router.post("/ragas/run")
def api_evaluation_ragas_run(
    request: Request,
    body: EvaluationRagasRunBody,
    principal: PrincipalContext = Depends(require_permission(PERM_SETTINGS_WRITE)),
) -> dict:
    try:
        rid = uuid.UUID(body.run_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_run_id") from exc
    try:
        out = run_ragas(run_id=rid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_service().log_privileged_action(
        action="settings.evaluation.ragas_run",
        principal=principal,
        request=request,
        target_type="evaluation_run",
        target_id=str(rid),
    )
    return out


@router.get("/runs")
def api_evaluation_runs(
    limit: int = Query(default=50, ge=1, le=_CAP),
    offset: int = Query(default=0, ge=0),
    _principal=Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    return list_runs(limit=limit, offset=offset)


@router.get("/runs/{run_id}")
def api_evaluation_run_detail(
    run_id: str,
    _principal=Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    try:
        rid = uuid.UUID(run_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_run_id") from exc
    detail = get_run_detail(run_id=rid)
    if detail is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return detail


@router.get("/runs/{run_id}/metrics")
def api_evaluation_run_metrics(
    run_id: str,
    _principal=Depends(require_permission(PERM_LOGS_READ)),
) -> dict:
    try:
        rid = uuid.UUID(run_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_run_id") from exc
    data = get_run_metrics_grouped(run_id=rid)
    if data is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return data


@router.patch("/items/{item_id}")
def api_evaluation_item_patch(
    request: Request,
    item_id: str,
    body: EvaluationItemPatchBody,
    principal: PrincipalContext = Depends(require_permission(PERM_SETTINGS_WRITE)),
) -> dict:
    try:
        iid = uuid.UUID(item_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_item_id") from exc
    result = patch_evaluation_item(
        item_id=iid,
        ground_truth=body.ground_truth,
        notes=body.notes,
        manual_score=body.manual_score,
    )
    if result.get("error") == "item_not_found":
        raise HTTPException(status_code=404, detail="item_not_found")
    get_audit_service().log_privileged_action(
        action="settings.evaluation.item_patch",
        principal=principal,
        request=request,
        target_type="evaluation_item",
        target_id=item_id,
    )
    return result
