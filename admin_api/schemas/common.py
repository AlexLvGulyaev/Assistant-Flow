from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app: str
    timestamp: datetime
    version: str | None = None
    build: str | None = None
    dependencies: dict[str, Any] = Field(default_factory=dict)
    config_readiness: dict[str, Any] = Field(default_factory=dict)


class OverviewResponse(BaseModel):
    database: dict[str, Any] = Field(default_factory=dict)
    chroma: dict[str, Any] = Field(default_factory=dict)
    rag: dict[str, Any] = Field(default_factory=dict)
    supported_modalities: list[str] = Field(default_factory=list)
    providers: dict[str, Any] = Field(default_factory=dict)
    asset_storage: dict[str, Any] = Field(default_factory=dict)
    audio: dict[str, Any] = Field(default_factory=dict)
    config_readiness: dict[str, Any] = Field(default_factory=dict)


class LogEntry(BaseModel):
    execution_id: str | None = None
    stage: str | None = None
    status: str | None = None
    created_at: datetime | str | None = None
    route: str | None = None
    mode: str | None = None
    details: dict[str, Any] | None = None
