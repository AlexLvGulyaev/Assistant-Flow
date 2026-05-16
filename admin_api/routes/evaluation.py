from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

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
) -> dict:
    return list_rag_turns(
        limit=limit,
        since_hours=since_hours,
        fallback=fallback,
        has_ragas_metrics=has_ragas_metrics,
        search=search,
    )


@router.get("/rag-turns/{execution_id}")
def api_evaluation_rag_turn_detail(execution_id: str) -> dict:
    detail = get_rag_turn_detail(execution_id=execution_id.strip())
    if detail is None:
        raise HTTPException(status_code=404, detail="rag_turn_not_found")
    return detail


@router.post("/import")
def api_evaluation_import(body: EvaluationImportBody) -> dict:
    try:
        return import_turns(
            execution_ids=body.execution_ids,
            dataset=body.dataset,
            run_name=body.run_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ragas/run")
def api_evaluation_ragas_run(body: EvaluationRagasRunBody) -> dict:
    try:
        rid = uuid.UUID(body.run_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_run_id") from exc
    try:
        return run_ragas(run_id=rid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
def api_evaluation_runs(
    limit: int = Query(default=50, ge=1, le=_CAP),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return list_runs(limit=limit, offset=offset)


@router.get("/runs/{run_id}")
def api_evaluation_run_detail(run_id: str) -> dict:
    try:
        rid = uuid.UUID(run_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_run_id") from exc
    detail = get_run_detail(run_id=rid)
    if detail is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return detail


@router.get("/runs/{run_id}/metrics")
def api_evaluation_run_metrics(run_id: str) -> dict:
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
    item_id: str, body: EvaluationItemPatchBody
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
    return result
