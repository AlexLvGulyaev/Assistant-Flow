"""
Типы evaluation layer (P6.5): offline/diagnostic, не production monitoring.

Идеи уровня «вопрос → ответ → контексты → метрики» согласованы с типичным RAGAS input
(question, answer, contexts, ground_truth), без обязательной зависимости от пакета ragas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationQuestion:
    """Один вопрос из JSON dataset (smoke / regression)."""

    id: str
    question: str
    expected_answer: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    should_have_answer: bool = True


@dataclass(frozen=True)
class EvaluationSample:
    """Фактический прогон по вопросу (read-only вызов RAG path)."""

    question: EvaluationQuestion
    actual_answer: str
    contexts: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]
    used_fallback_without_context: bool
    diagnostics_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationMetricResult:
    """Одна внутренняя метрика (детерминированная проверка)."""

    name: str
    passed: bool
    detail: str | float | int | bool = ""


@dataclass(frozen=True)
class EvaluationResult:
    """Итог по одному вопросу: метрики + предупреждения."""

    question_id: str
    metrics: tuple[EvaluationMetricResult, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    answer_preview: str = ""
    context_previews: tuple[str, ...] = field(default_factory=tuple)
    source_list: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class RagEvaluationRunSummary:
    """Сводка прогона smoke evaluation."""

    total_questions: int = 0
    internal_checks_passed: int = 0
    warnings: list[str] = field(default_factory=list)
    avg_context_count: float = 0.0
    avg_source_count: float = 0.0
    no_answer_summary: str = ""
    ragas_status: str = "skipped"
    ragas_detail: str = ""
