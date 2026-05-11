"""
Типы слоя diagnostics retrieval (P6.8): offline-only, без влияния на ranking/runtime Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.retrieval_security.context import RetrievalSecurityContext


@dataclass(frozen=True)
class RetrievalDiagnosticSample:
    """Один кейс из smoke-dataset (не production benchmark)."""

    id: str
    query: str
    should_have_answer: bool = True
    expected_keywords: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    security_context: RetrievalSecurityContext | None = None
    # Произвольные метки прогона (dataset_version, suite, …).
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalDiagnosticMetric:
    """Отдельная smoke-проверка."""

    name: str
    passed: bool
    detail: str | None = None


@dataclass(frozen=True)
class RetrievalDiagnosticResult:
    """Результат анализа одного retrieval для одного sample."""

    sample_id: str
    query_preview: str
    retrieved_count: int
    source_count: int
    has_context: bool
    expected_source_hit: bool | None
    expected_keyword_hit: bool | None
    score_min: float | None
    score_max: float | None
    score_avg: float | None
    warnings: tuple[str, ...]
    passed: bool
    metrics: tuple[RetrievalDiagnosticMetric, ...]
    metadata: dict[str, Any]
