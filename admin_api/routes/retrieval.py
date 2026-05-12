"""Admin API: retrieval backend overview, active backend (P6.10), tuning (P6.12)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from admin_api.deps import get_admin_service

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


@router.get("/overview")
def api_retrieval_overview() -> dict[str, Any]:
    svc = get_admin_service()
    return svc.get_retrieval_overview()


@router.put("/active-backend")
def api_retrieval_active_backend(body: ActiveBackendBody) -> dict[str, Any]:
    svc = get_admin_service()
    try:
        return svc.set_active_retrieval_backend((body.backend or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tuning")
def api_retrieval_tuning_get() -> dict[str, Any]:
    return get_admin_service().get_retrieval_tuning()


@router.put("/tuning")
def api_retrieval_tuning_put(body: TuningPutBody) -> dict[str, Any]:
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not patch:
        raise HTTPException(
            status_code=400,
            detail="empty body: provide at least one tuning field",
        )
    svc = get_admin_service()
    try:
        return svc.put_retrieval_tuning(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tuning")
def api_retrieval_tuning_delete() -> dict[str, Any]:
    svc = get_admin_service()
    try:
        return svc.delete_retrieval_tuning()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
