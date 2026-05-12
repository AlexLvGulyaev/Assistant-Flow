from __future__ import annotations

from pydantic import BaseModel, Field


class SummaryEvents(BaseModel):
    total: int
    success: int
    error: int
    other: int


class SummarySessions(BaseModel):
    unique_execution_ids: int


class SummaryRoutes(BaseModel):
    text: int
    rag: int
    images: int
    audio_voice: int
    documents: int = 0
    other_unknown: int


class LifecycleEventRow(BaseModel):
    stage: str
    events: int


class TelemetrySample(BaseModel):
    scope: str
    cap: int
    rows_considered: int
    rows_in_window: int
    unique_execution_ids_in_sample: int
    tokens_total: int | None = None
    avg_latency_ms: float | None = None
    max_latency_ms: float | None = None
    top_provider_model: str | None = None
    by_provider_row_counts: dict[str, int] = Field(default_factory=dict)


class AudioVoiceCounts(BaseModel):
    sessions_route_bucket: int
    voice_pipeline_stage_events: int


class SummaryResponse(BaseModel):
    hours: int
    events: SummaryEvents
    sessions: SummarySessions
    routes: SummaryRoutes
    lifecycle_events: list[LifecycleEventRow]
    telemetry_sample: TelemetrySample
    admin_events: int
    reindex_starts: int
    audio_voice_counts: AudioVoiceCounts
