"""
Offline RAG smoke evaluation через существующий ``RagQueryService`` (без изменения retrieval/prompt).

Не вызывать из Telegram runtime. См. legacy ``legacy/PEr06_source/evaluate_rag.py``,
``legacy/PEr08_source/assistant_api/evaluate_ragas.py`` только как reference — не копипаста.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.evaluation.base import (
    EvaluationMetricResult,
    EvaluationQuestion,
    EvaluationResult,
    EvaluationSample,
    RagEvaluationRunSummary,
)
from services.evaluation.ragas_adapter import build_ragas_single_row, try_run_ragas_metrics
from services.rag_query_service import RagQueryService
from services.rag_types import RagQueryResult


_NO_INFO_RE = re.compile(
    r"(нет\s+(информации|данных|сведений)|не\s+найдено|недостаточно\s+релевантн)",
    re.IGNORECASE | re.UNICODE,
)


class RagEvaluationService:
    """Загрузка dataset, прогон RAG, внутренние метрики, RAGAS-ready rows."""

    @staticmethod
    def load_questions(path: Path) -> list[EvaluationQuestion]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("dataset root must be a JSON array")
        out: list[EvaluationQuestion] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            qid = str(row.get("id") or "").strip()
            qtext = str(row.get("question") or "").strip()
            if not qid or not qtext:
                continue
            tags = row.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            out.append(
                EvaluationQuestion(
                    id=qid,
                    question=qtext,
                    expected_answer=(str(row["expected_answer"]).strip() or None)
                    if row.get("expected_answer") is not None
                    else None,
                    tags=tuple(str(t) for t in tags),
                    should_have_answer=bool(row.get("should_have_answer", True)),
                )
            )
        return out

    @staticmethod
    def sample_from_rag_result(
        question: EvaluationQuestion,
        result: RagQueryResult,
    ) -> EvaluationSample:
        contexts = RagEvaluationService._contexts_from_result(result)
        sources: list[dict[str, Any]] = []
        for s in result.sources:
            sources.append(
                {
                    "source": s.source,
                    "score": s.score,
                    "content_preview": _preview(s.content, 400),
                }
            )
        diag = result.diagnostics
        diag_summary: dict[str, Any] = {}
        if diag is not None:
            diag_summary = {
                "retrieved_count": diag.retrieved_count,
                "filtered_count": diag.filtered_count,
                "fallback_reason": diag.fallback_reason,
                "context_chars": diag.context_chars,
            }
        return EvaluationSample(
            question=question,
            actual_answer=result.answer or "",
            contexts=contexts,
            sources=tuple(sources),
            used_fallback_without_context=result.used_fallback_without_context,
            diagnostics_summary=diag_summary,
        )

    @staticmethod
    def _contexts_from_result(result: RagQueryResult) -> tuple[str, ...]:
        if result.sources:
            return tuple((s.content or "").strip() for s in result.sources if (s.content or "").strip())
        diag = result.diagnostics
        if diag is None:
            return ()
        chunks: list[str] = []
        for c in diag.retrieved_chunks:
            if c.passed_filter and (c.text_preview or "").strip():
                chunks.append(c.text_preview.strip())
        return tuple(chunks)

    @staticmethod
    def compute_internal_metrics(sample: EvaluationSample) -> tuple[EvaluationMetricResult, ...]:
        q = sample.question
        ans = (sample.actual_answer or "").strip()
        ctxs = [c for c in sample.contexts if (c or "").strip()]
        metrics: list[EvaluationMetricResult] = []

        answer_non_empty = len(ans) > 0
        metrics.append(
            EvaluationMetricResult(
                "answer_non_empty",
                answer_non_empty,
                len(ans),
            )
        )

        contexts_non_empty = len(ctxs) > 0
        if q.should_have_answer:
            metrics.append(
                EvaluationMetricResult(
                    "contexts_non_empty",
                    contexts_non_empty,
                    len(ctxs),
                )
            )
        else:
            metrics.append(
                EvaluationMetricResult(
                    "no_context_when_should_not_have_answer",
                    not contexts_non_empty,
                    len(ctxs),
                )
            )

        source_count = len(sample.sources)
        metrics.append(
            EvaluationMetricResult(
                "source_count",
                True,
                source_count,
            )
        )

        context_count = len(ctxs)
        metrics.append(
            EvaluationMetricResult(
                "context_count",
                True,
                context_count,
            )
        )

        max_ctx = max((len(c) for c in ctxs), default=0)
        total_ctx = sum(len(c) for c in ctxs)
        metrics.append(
            EvaluationMetricResult(
                "max_context_chars",
                True,
                max_ctx,
            )
        )
        metrics.append(
            EvaluationMetricResult(
                "total_context_chars",
                True,
                total_ctx,
            )
        )

        mentions_no_info = bool(_NO_INFO_RE.search(ans))
        if not q.should_have_answer:
            ok_no_answer = (
                (not contexts_non_empty)
                or mentions_no_info
                or sample.used_fallback_without_context
            )
            metrics.append(
                EvaluationMetricResult(
                    "answer_mentions_no_info_or_empty_kb",
                    ok_no_answer,
                    mentions_no_info,
                )
            )
        else:
            metrics.append(
                EvaluationMetricResult(
                    "answer_mentions_no_info",
                    not mentions_no_info,
                    mentions_no_info,
                )
            )

        return tuple(metrics)

    @staticmethod
    def evaluate_question(
        rag: RagQueryService,
        question: EvaluationQuestion,
    ) -> tuple[EvaluationSample, EvaluationResult]:
        warnings: list[str] = []
        try:
            result = rag.answer(question.question)
        except Exception as exc:
            warnings.append(f"rag.answer failed: {type(exc).__name__}: {exc}")
            empty = RagQueryResult(
                answer="",
                sources=(),
                used_fallback_without_context=True,
                diagnostics=None,
            )
            result = empty

        sample = RagEvaluationService.sample_from_rag_result(question, result)
        metrics = RagEvaluationService.compute_internal_metrics(sample)

        previews = tuple(_preview(c, 500) for c in sample.contexts)
        src_list = tuple(str(s.get("source", "")) for s in sample.sources)

        ev = EvaluationResult(
            question_id=question.id,
            metrics=metrics,
            warnings=tuple(warnings),
            answer_preview=_preview(sample.actual_answer, 600),
            context_previews=previews,
            source_list=src_list,
        )
        return sample, ev

    @staticmethod
    def run_smoke(
        rag: RagQueryService,
        questions: list[EvaluationQuestion],
        *,
        enable_ragas: bool,
    ) -> tuple[list[tuple[EvaluationSample, EvaluationResult]], RagEvaluationRunSummary]:
        rows: list[dict[str, Any]] = []
        pairs: list[tuple[EvaluationSample, EvaluationResult]] = []
        all_warnings: list[str] = []
        internal_ok = 0
        ctx_counts: list[int] = []
        src_counts: list[int] = []
        no_answer_behaviors: list[str] = []

        for q in questions:
            sample, ev = RagEvaluationService.evaluate_question(rag, q)
            pairs.append((sample, ev))
            all_warnings.extend(ev.warnings)
            ctx_counts.append(len(sample.contexts))
            src_counts.append(len(sample.sources))
            if not q.should_have_answer:
                no_answer_behaviors.append(
                    f"{q.id}:fallback={sample.used_fallback_without_context},ctx={len(sample.contexts)}"
                )

            req = _REQUIRED_PASS_METRICS(q)
            if all(m.passed for m in ev.metrics if m.name in req):
                internal_ok += 1

            rows.append(
                build_ragas_single_row(
                    question=q.question,
                    answer=sample.actual_answer,
                    contexts=list(sample.contexts),
                    ground_truth=q.expected_answer,
                )
            )

        summary = RagEvaluationRunSummary(
            total_questions=len(questions),
            internal_checks_passed=internal_ok,
            warnings=all_warnings,
            avg_context_count=(sum(ctx_counts) / len(ctx_counts)) if ctx_counts else 0.0,
            avg_source_count=(sum(src_counts) / len(src_counts)) if src_counts else 0.0,
            no_answer_summary="; ".join(no_answer_behaviors) if no_answer_behaviors else "n/a",
            ragas_status="skipped",
        )

        if enable_ragas:
            ragas_out = try_run_ragas_metrics(rows)
            summary.ragas_status = str(ragas_out.get("status", "skipped"))
            summary.ragas_detail = str(ragas_out.get("detail", ""))
        else:
            summary.ragas_detail = "ENABLE_RAGAS_EVALUATION=false"
        return pairs, summary


def _REQUIRED_PASS_METRICS(q: EvaluationQuestion) -> frozenset[str]:
    base = frozenset({"answer_non_empty"})
    if q.should_have_answer:
        return base | frozenset({"contexts_non_empty", "answer_mentions_no_info"})
    return base | frozenset(
        {"no_context_when_should_not_have_answer", "answer_mentions_no_info_or_empty_kb"}
    )


def _preview(text: str, max_len: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."
