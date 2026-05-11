#!/usr/bin/env python3
"""
Offline RAG smoke evaluation (P6.5). Не трогает Telegram и не меняет retrieval/prompt.

DB/RAG/runtime: только внутри portfolio-test-assistant-flow-1 после rebuild (см. PROJECT_STATE §32).

  docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
  docker exec portfolio-test-assistant-flow-1 python scripts/evaluate_rag_smoke.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_rag():
    from providers.openai_chat_provider import OpenAIChatProvider
    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore
    from services.rag_query_service import RagQueryService
    from services.retrieval.factory import build_retrieval_backend
    from utils.config import load_config

    config = load_config()
    chroma_path = Path(config.chroma_persist_dir)
    if not chroma_path.is_absolute():
        chroma_path = ROOT / chroma_path

    embeddings = build_openai_embeddings(config)
    store = ChromaRagStore(
        config,
        embeddings,
        persist_directory=chroma_path,
    )
    chat = OpenAIChatProvider(config)
    retrieval = build_retrieval_backend(config, chroma_store=store, embeddings=embeddings)
    rag = RagQueryService(retrieval, chat, config)
    return config, rag


def _metric_to_dict(m) -> dict:
    return {"name": m.name, "passed": m.passed, "detail": m.detail}


def main() -> int:
    import os

    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.evaluation.rag_evaluation_service import RagEvaluationService

    cfg, rag = _bootstrap_rag()
    ds_path = Path(cfg.rag_eval_dataset_path)
    if not ds_path.is_absolute():
        ds_path = ROOT / ds_path
    out_dir = Path(cfg.rag_eval_output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "rag_smoke_report.json"

    questions = RagEvaluationService.load_questions(ds_path)
    if len(questions) < 5:
        print(f"ERROR: dataset must have at least 5 questions, got {len(questions)}", flush=True)
        return 2

    print(
        f"[assistant-flow] rag eval: dataset={ds_path} questions={len(questions)}",
        flush=True,
    )

    pairs, summary = RagEvaluationService.run_smoke(
        rag,
        questions,
        enable_ragas=cfg.enable_ragas_evaluation,
    )

    per_question: list[dict] = []
    for sample, ev in pairs:
        per_question.append(
            {
                "question_id": ev.question_id,
                "question": sample.question.question,
                "answer_preview": ev.answer_preview,
                "source_list": list(ev.source_list),
                "context_previews": list(ev.context_previews),
                "used_fallback_without_context": sample.used_fallback_without_context,
                "diagnostics_summary": sample.diagnostics_summary,
                "metrics": [_metric_to_dict(m) for m in ev.metrics],
                "warnings": list(ev.warnings),
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(ds_path),
        "total_questions": summary.total_questions,
        "internal_checks_passed": summary.internal_checks_passed,
        "warnings": summary.warnings,
        "avg_context_count": round(summary.avg_context_count, 3),
        "avg_source_count": round(summary.avg_source_count, 3),
        "no_answer_behavior_summary": summary.no_answer_summary,
        "ragas_status": summary.ragas_status,
        "ragas_detail": summary.ragas_detail,
        "per_question": per_question,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[assistant-flow] rag eval: total_questions={summary.total_questions} "
        f"internal_checks_passed={summary.internal_checks_passed} "
        f"avg_context_count={summary.avg_context_count:.2f} "
        f"avg_source_count={summary.avg_source_count:.2f}",
        flush=True,
    )
    print(
        f"[assistant-flow] rag eval: ragas_status={summary.ragas_status} "
        f"detail={summary.ragas_detail!r}",
        flush=True,
    )
    print(
        f"[assistant-flow] rag eval: no_answer_summary={summary.no_answer_summary!r}",
        flush=True,
    )
    if summary.warnings:
        print(f"[assistant-flow] rag eval: warnings_count={len(summary.warnings)}", flush=True)
    print(f"[assistant-flow] rag eval: report_written={report_path}", flush=True)
    print("OK: evaluate_rag_smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
