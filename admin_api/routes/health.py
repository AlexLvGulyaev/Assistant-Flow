from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from admin_api.deps import (
    config_readiness_summary,
    run_health_report,
    snapshot_to_public_dict,
)
from admin_api.schemas.common import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    cfg, rep = run_health_report()
    now = datetime.now(timezone.utc)
    overall = "ok"
    if rep.postgres.status != "ok":
        overall = "degraded"
    elif rep.rag.status == "error":
        overall = "degraded"

    return HealthResponse(
        status=overall,
        app="assistant-flow-admin-api",
        timestamp=now,
        version=os.getenv("APP_VERSION"),
        build=os.getenv("BUILD_SHA") or os.getenv("GIT_COMMIT"),
        dependencies={
            "postgres": snapshot_to_public_dict(rep.postgres),
            "chroma": snapshot_to_public_dict(rep.chroma),
            "rag": snapshot_to_public_dict(rep.rag),
            "llm": {k: snapshot_to_public_dict(v) for k, v in rep.llm.items()},
        },
        config_readiness=config_readiness_summary(cfg),
    )
