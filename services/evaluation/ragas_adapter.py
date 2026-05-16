"""
RAGAS evaluation adapter for Assistant Flow Evaluation Layer.

Adapted from ideas in ``legacy/PEr06_source/evaluate_rag.py`` (dataset shape, metric set,
Langchain wrappers) — not a direct copy. Does not run from Telegram/RAG hot path.
"""

from __future__ import annotations

import math
import os
from typing import Any

__all__ = [
    "build_ragas_single_row",
    "check_ragas_dependencies",
    "run_ragas_evaluation",
    "try_run_ragas_metrics",
]

RAGAS_METRIC_KEYS = (
    "ragas.faithfulness",
    "ragas.answer_relevancy",
    "ragas.context_precision",
)

_SHORT_TO_KEY = {
    "faithfulness": "ragas.faithfulness",
    "answer_relevancy": "ragas.answer_relevancy",
    "context_precision": "ragas.context_precision",
}


def build_ragas_single_row(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None,
) -> dict[str, Any]:
    """One row compatible with RAGAS / HuggingFace ``Dataset``."""
    return {
        "question": question,
        "answer": answer,
        "contexts": contexts,
        "ground_truth": ground_truth or "",
    }


def check_ragas_dependencies() -> dict[str, Any]:
    """Report whether optional RAGAS stack is importable."""
    out: dict[str, Any] = {"ragas": False, "datasets": False, "langchain_openai": False}
    try:
        import ragas  # noqa: F401

        out["ragas"] = True
        out["ragas_version"] = getattr(ragas, "__version__", "unknown")
    except ImportError as exc:
        out["ragas_error"] = str(exc)
    try:
        import datasets  # noqa: F401

        out["datasets"] = True
    except ImportError as exc:
        out["datasets_error"] = str(exc)
    try:
        import langchain_openai  # noqa: F401

        out["langchain_openai"] = True
    except ImportError as exc:
        out["langchain_openai_error"] = str(exc)
    out["ready"] = bool(out["ragas"] and out["datasets"] and out["langchain_openai"])
    return out


def try_run_ragas_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible stub entry; delegates to :func:`run_ragas_evaluation`."""
    if not rows:
        return {"status": "skipped", "detail": "no rows", "scores": None}
    dep = check_ragas_dependencies()
    if not dep.get("ready"):
        return {
            "status": "skipped",
            "detail": "ragas stack not ready; pip install -r requirements-ragas.txt",
            "scores": None,
        }
    return run_ragas_evaluation(rows)


def _nan_mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _build_metrics(openai_api_key: str | None):
    """Construct RAGAS metric instances (legacy PEr06 pattern with wrappers)."""
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.metrics import AnswerRelevancy, ContextPrecision, Faithfulness

    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY") or ""
    if not api_key.strip():
        raise ValueError("OPENAI_API_KEY required for RAGAS judge metrics")

    os.environ.setdefault("OPENAI_API_KEY", api_key)

    embeddings = OpenAIEmbeddings(openai_api_key=api_key)
    llm = ChatOpenAI(model=os.environ.get("RAGAS_CHAT_MODEL", "gpt-4o-mini"), temperature=0)

    try:
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper

        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)
        ragas_llm = LangchainLLMWrapper(llm)
        faithfulness_metric = Faithfulness(llm=ragas_llm)
        answer_relevancy_metric = AnswerRelevancy(
            llm=ragas_llm, embeddings=ragas_embeddings
        )
        try:
            context_precision_metric = ContextPrecision(
                llm=ragas_llm, embeddings=ragas_embeddings
            )
        except TypeError:
            context_precision_metric = ContextPrecision(llm=ragas_llm)
        return [
            ("faithfulness", faithfulness_metric),
            ("answer_relevancy", answer_relevancy_metric),
            ("context_precision", context_precision_metric),
        ]
    except ImportError:
        from ragas.metrics import answer_relevancy, context_precision, faithfulness

        return [
            ("faithfulness", faithfulness),
            ("answer_relevancy", answer_relevancy),
            ("context_precision", context_precision),
        ]


def run_ragas_evaluation(
    rows: list[dict[str, Any]],
    *,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Run RAGAS ``evaluate()`` on prepared rows.

    Each row: question, answer, contexts (list[str]), ground_truth (str, may be empty).

    Returns per-item scores, run-level means, and explicit gaps for unavailable metrics.
    """
    dep = check_ragas_dependencies()
    if not dep.get("ready"):
        return {
            "status": "skipped",
            "detail": dep,
            "per_item": [],
            "run_means": {},
            "unavailable_metrics": list(_SHORT_TO_KEY.values()),
        }

    from datasets import Dataset
    from ragas import evaluate

    dataset = Dataset.from_dict(
        {
            "question": [r["question"] for r in rows],
            "answer": [r["answer"] for r in rows],
            "contexts": [r["contexts"] for r in rows],
            "ground_truth": [r.get("ground_truth") or "" for r in rows],
        }
    )

    unavailable: list[str] = []
    metric_specs: list[tuple[str, Any]] = []
    build_error: str | None = None
    try:
        metric_specs = _build_metrics(openai_api_key)
    except Exception as exc:
        build_error = f"{type(exc).__name__}: {exc}"
        unavailable = list(_SHORT_TO_KEY.values())

    if not metric_specs:
        return {
            "status": "failed",
            "detail": build_error or "no metrics constructed",
            "per_item": [],
            "run_means": {},
            "unavailable_metrics": unavailable,
        }

    metrics_only = [m for _, m in metric_specs]
    short_names = [n for n, _ in metric_specs]

    # context_precision needs non-empty ground_truth for meaningful scores
    if all(not (r.get("ground_truth") or "").strip() for r in rows):
        unavailable.append("ragas.context_precision")
        short_names = [n for n in short_names if n != "context_precision"]
        metrics_only = [m for n, m in metric_specs if n != "context_precision"]
        cp_note = "all rows lack ground_truth; context_precision skipped"
    else:
        cp_note = None

    evaluate_error: str | None = None
    result_ds = None
    try:
        result_ds = evaluate(dataset=dataset, metrics=metrics_only)
    except Exception as exc:
        evaluate_error = f"{type(exc).__name__}: {exc}"

    per_item: list[dict[str, Any]] = []
    run_means: dict[str, float | None] = {}

    if result_ds is not None:
        for i, row in enumerate(rows):
            item_scores: dict[str, Any] = {}
            item_errors: dict[str, str] = {}
            for short in short_names:
                key = _SHORT_TO_KEY[short]
                try:
                    col = result_ds[short]
                    val = col[i] if i < len(col) else None
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        item_errors[key] = "nan_or_missing"
                        item_scores[key] = None
                    else:
                        item_scores[key] = round(float(val), 6)
                except (KeyError, TypeError, IndexError) as exc:
                    item_errors[key] = str(exc)
                    item_scores[key] = None
            per_item.append(
                {
                    "ordinal": row.get("ordinal"),
                    "question": row["question"],
                    "scores": item_scores,
                    "errors": item_errors,
                }
            )

        for short in short_names:
            key = _SHORT_TO_KEY[short]
            try:
                col = result_ds[short]
                vals = [
                    float(v)
                    for v in col
                    if v is not None and not (isinstance(v, float) and math.isnan(v))
                ]
                run_means[key] = _nan_mean(vals)
            except (KeyError, TypeError, ValueError):
                run_means[key] = None

    status = "ok"
    if evaluate_error:
        status = "failed" if not per_item else "partial"
    elif cp_note:
        status = "partial"

    detail_parts = [p for p in (build_error, evaluate_error, cp_note) if p]
    return {
        "status": status,
        "detail": "; ".join(detail_parts) if detail_parts else None,
        "per_item": per_item,
        "run_means": run_means,
        "unavailable_metrics": sorted(set(unavailable)),
    }
