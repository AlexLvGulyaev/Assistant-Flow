"""
RAGAS-ready структуры данных и опциональный запуск метрик.

Пакет ``ragas`` не обязателен: при отсутствии или ошибке — status ``skipped`` / ``failed``,
без падения основного smoke pipeline.
"""

from __future__ import annotations

from typing import Any


def build_ragas_single_row(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None,
) -> dict[str, Any]:
    """Одна строка в форме, совместимой с RAGAS / HF datasets."""
    return {
        "question": question,
        "answer": answer,
        "contexts": contexts,
        "ground_truth": ground_truth or "",
    }


def try_run_ragas_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Если ``ragas`` установлен и импорт успешен — можно расширить вызовом evaluate().
    По умолчанию не тянем тяжёлые зависимости и не вызываем LLM-as-judge без явного включения.

    Returns:
        ``{"status": "skipped"|"enabled"|"failed", "detail": str, "scores": dict|None}``
    """
    try:
        import ragas  # noqa: F401
    except ImportError:
        return {
            "status": "skipped",
            "detail": "ragas package not installed",
            "scores": None,
        }

    # Пакет есть, но полноценный RAGAS pipeline (datasets, judge LLM) на P6.5 не включаем.
    return {
        "status": "skipped",
        "detail": "ragas installed but full evaluate() intentionally deferred (P6.5)",
        "scores": None,
    }
