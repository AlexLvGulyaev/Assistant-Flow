from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvaluationImportBody(BaseModel):
    execution_ids: list[str] = Field(..., min_length=1)
    dataset: str = "interactive_eval_ui"
    run_name: str | None = None


class EvaluationRagasRunBody(BaseModel):
    run_id: str


class EvaluationItemPatchBody(BaseModel):
    ground_truth: str | None = None
    notes: str | None = None
    manual_score: float | None = Field(default=None, ge=0.0, le=1.0)
