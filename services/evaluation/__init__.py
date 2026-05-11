"""RAG evaluation foundation (P6.5): offline smoke, RAGAS-ready shapes, internal metrics."""

from services.evaluation.base import (
    EvaluationMetricResult,
    EvaluationQuestion,
    EvaluationResult,
    EvaluationSample,
    RagEvaluationRunSummary,
)
from services.evaluation.rag_evaluation_service import RagEvaluationService
from services.evaluation.ragas_adapter import build_ragas_single_row, try_run_ragas_metrics

__all__ = [
    "EvaluationMetricResult",
    "EvaluationQuestion",
    "EvaluationResult",
    "EvaluationSample",
    "RagEvaluationRunSummary",
    "RagEvaluationService",
    "build_ragas_single_row",
    "try_run_ragas_metrics",
]
