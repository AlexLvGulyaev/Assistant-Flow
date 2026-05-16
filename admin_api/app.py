from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from admin_api.routes.evaluation import router as evaluation_router
from admin_api.routes.assets import router as assets_router
from admin_api.routes.documents import router as documents_router
from admin_api.routes.health import router as health_router
from admin_api.routes.logs import router as logs_router
from admin_api.routes.overview import router as overview_router
from admin_api.routes.retrieval import router as retrieval_router
from admin_api.routes.sessions import router as memory_router
from admin_api.routes.summary import router as summary_router

logger = logging.getLogger(__name__)

_DEFAULT_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://216.57.108.80:5173",
]


def _cors_origins() -> list[str]:
    """Merge explicit env origins with default local dev origins."""
    raw = os.getenv("ADMIN_API_CORS_ORIGINS", "")
    env_origins = [s.strip() for s in raw.split(",") if s.strip()]
    merged: list[str] = []
    for origin in [*env_origins, *_DEFAULT_DEV_ORIGINS]:
        if origin not in merged:
            merged.append(origin)
    return merged


def create_admin_api_app() -> FastAPI:
    application = FastAPI(
        title="Assistant Flow Admin API",
        description="JSON API for future React admin UI. Streamlit admin_ui unchanged.",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(overview_router)
    application.include_router(retrieval_router)
    application.include_router(summary_router)
    application.include_router(logs_router)
    application.include_router(memory_router)
    application.include_router(assets_router)
    application.include_router(documents_router)
    application.include_router(evaluation_router)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Admin API error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_error", "message": str(exc)[:300]},
        )

    return application


app = create_admin_api_app()
