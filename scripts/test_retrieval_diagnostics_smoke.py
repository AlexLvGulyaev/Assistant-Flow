#!/usr/bin/env python3
"""
Smoke: retrieval diagnostics layer (P6.8). Offline-only, не меняет Telegram/RAG runtime.

После rebuild portfolio:

  docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
  docker exec -it portfolio-test-assistant-flow-1 python scripts/test_retrieval_diagnostics_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = ROOT / "evaluation/datasets/retrieval_diagnostics_smoke.json"
REPORT_REL = Path("outputs/evaluation/retrieval_diagnostics_report.json")


def _bootstrap_retrieval():
    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore
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
    retrieval = build_retrieval_backend(config, chroma_store=store, embeddings=embeddings)
    return config, retrieval


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.retrieval_diagnostics.diagnostics_service import RetrievalDiagnosticsService
    from services.retrieval_diagnostics.ragas_placeholder import try_retrieval_ragas_row

    ds_path = Path(
        os.getenv("RETRIEVAL_DIAGNOSTICS_DATASET_PATH") or str(DEFAULT_DATASET)
    )
    if not ds_path.is_absolute():
        ds_path = ROOT / ds_path
    if not ds_path.is_file():
        print(f"ERROR: dataset not found: {ds_path}", flush=True)
        return 2

    try:
        samples = RetrievalDiagnosticsService.load_samples(ds_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR: invalid dataset: {exc}", flush=True)
        return 2

    if len(samples) < 5:
        print(f"ERROR: need at least 5 cases, got {len(samples)}", flush=True)
        return 2

    try:
        config, retrieval = _bootstrap_retrieval()
    except Exception as exc:
        print(
            f"ERROR: retrieval backend bootstrap failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return 2

    out_dir = Path(config.rag_eval_output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / REPORT_REL.name

    top_k = int(config.rag_top_k)
    per_case: list[dict] = []
    passed_n = 0
    warn_n = 0
    total_retrieved = 0
    src_hits = 0
    kw_hits = 0
    src_cases = 0
    kw_cases = 0

    for sample in samples:
        sec = sample.security_context
        try:
            raw = retrieval.search(sample.query, top_k=top_k, security_context=sec)
        except TypeError:
            # совместимость со старым backend без keyword (не должно случиться в portfolio)
            raw = retrieval.search(sample.query, top_k=top_k)
        try_retrieval_ragas_row(
            query=sample.query,
            contexts=[r.chunk.page_content or "" for r in raw[:3]],
            enable=bool(getattr(config, "enable_ragas_evaluation", False)),
        )
        res = RetrievalDiagnosticsService.analyze(
            sample=sample,
            results=raw,
            security_context=sec,
            extra_metadata={"rag_backend": config.rag_backend, "top_k": top_k},
        )
        if res.passed:
            passed_n += 1
        warn_n += len(res.warnings)
        total_retrieved += res.retrieved_count
        if res.expected_source_hit is True:
            src_hits += 1
        if res.expected_source_hit is not None:
            src_cases += 1
        if res.expected_keyword_hit is True:
            kw_hits += 1
        if res.expected_keyword_hit is not None:
            kw_cases += 1

        per_case.append(
            {
                **{k: v for k, v in asdict(res).items() if k != "metadata"},
                "metadata": res.metadata,
            }
        )

    n = len(samples)
    avg_retrieved = round(total_retrieved / n, 3) if n else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(ds_path),
        "total_cases": n,
        "passed_cases": passed_n,
        "warnings_total": warn_n,
        "avg_retrieved_count": avg_retrieved,
        "expected_source_hits": src_hits,
        "expected_source_cases_with_constraint": src_cases,
        "expected_keyword_hits": kw_hits,
        "expected_keyword_cases_with_constraint": kw_cases,
        "report_path": str(report_path),
        "per_case": per_case,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "[assistant-flow] retrieval_diagnostics: "
        f"total_cases={n} passed={passed_n} warnings={warn_n} "
        f"avg_retrieved_count={avg_retrieved} "
        f"source_hit_count={src_hits} keyword_hit_count={kw_hits} "
        f"report={report_path}",
        flush=True,
    )
    print("[assistant-flow] retrieval_diagnostics_smoke: OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
