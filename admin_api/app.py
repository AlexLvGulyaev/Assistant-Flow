from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from admin_api.routes.health import router as health_router
from admin_api.routes.logs import router as logs_router
from admin_api.routes.overview import router as overview_router
from admin_api.routes.summary import router as summary_router

logger = logging.getLogger(__name__)


def create_admin_api_app() -> FastAPI:
    application = FastAPI(
        title="Assistant Flow Admin API",
        description="JSON API for future React admin UI. Streamlit admin_ui unchanged.",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(overview_router)
    application.include_router(summary_router)
    application.include_router(logs_router)

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
