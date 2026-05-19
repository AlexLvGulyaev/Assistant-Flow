#!/usr/bin/env python3
"""
P8.4 — bounded security verification (guest/employee/admin, diagnostics, sanitization).

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_4_security_verification_smoke.py

Прогоняет сценарии P8.4 и делегирует регрессию P8.1–P8.3.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mixed_visibility_results():
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.visibility import (
        VISIBILITY_INTERNAL,
        VISIBILITY_PUBLIC,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
    )

    return [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="pub",
                metadata={"source": "public.md", "visibility": VISIBILITY_PUBLIC},
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="int",
                metadata={"source": "internal.md", "visibility": VISIBILITY_INTERNAL},
            ),
            score=0.2,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="leg",
                metadata={"source": "legacy.md", "visibility": VISIBILITY_UNSPECIFIED},
            ),
            score=0.3,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="sec",
                metadata={
                    "source": "restricted.md",
                    "visibility": VISIBILITY_RESTRICTED,
                },
            ),
            score=0.4,
        ),
    ]


def verify_role_matrix() -> None:
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST
    from services.retrieval_security.policy_resolver import (
        build_retrieval_security_context_for_role,
    )
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import VISIBILITY_PUBLIC

    mixed = _mixed_visibility_results()
    guest_ctx = build_retrieval_security_context_for_role(ROLE_GUEST)
    emp_ctx = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
    admin_ctx = build_retrieval_security_context_for_role(ROLE_ADMIN)

    g = filter_search_results_by_security(list(mixed), guest_ctx)
    assert len(g) == 1
    assert g[0].chunk.metadata["visibility"] == VISIBILITY_PUBLIC

    e = filter_search_results_by_security(list(mixed), emp_ctx)
    e_src = {r.chunk.metadata["source"] for r in e}
    assert e_src == {"public.md", "internal.md", "legacy.md"}

    a = filter_search_results_by_security(list(mixed), admin_ctx)
    assert len(a) == 4
    assert admin_ctx.is_fully_unrestricted()


def verify_diagnostics_and_sanitization() -> None:
    from services.rag_types import RagRequestDiagnostics, RagRetrievedChunkDiagnostics
    from services.retrieval_security.context import ROLE_GUEST, ROLE_ADMIN
    from services.retrieval_security.retrieval_diagnostics import (
        build_retrieval_security_summary,
        visibility_distribution,
    )
    from services.security.log_sanitizer import (
        POLICY_FORENSIC_ADMIN,
        POLICY_OPERATIONAL,
        sanitize_log_details,
    )

    try:
        from langchain_core.documents import Document

        dist = visibility_distribution(
            [
                (Document(page_content="a", metadata={"visibility": "public"}), 0.1),
                (Document(page_content="b", metadata={"visibility": "internal"}), 0.2),
            ]
        )
    except ImportError:
        dist = {"public": 1, "internal": 1}
    assert dist.get("public", 0) >= 1

    summary = build_retrieval_security_summary(
        security_role=ROLE_GUEST,
        retrieval_scope="public_only",
        retrieved_count=4,
        filtered_count=1,
        visibility_before=dist,
        visibility_after_relevance={"public": 1},
        security_filtered_count=3,
    )
    assert summary["security_role"] == ROLE_GUEST
    assert "visibility_distribution_retrieved" in summary

    secret = "user@corp.ru +79991234567"
    diag = RagRequestDiagnostics(
        query_preview="q",
        top_k=3,
        retrieved_count=1,
        filtered_count=1,
        relevance_threshold=1.0,
        chunks_missing_score=0,
        unique_sources_count=1,
        scores=(0.1,),
        context_chars=10,
        fallback_reason=None,
        retrieved_chunks=(
            RagRetrievedChunkDiagnostics(
                source="x.md",
                score=0.1,
                passed_filter=True,
                text_preview="prev",
                chunk_text_full=secret,
                visibility="internal",
            ),
        ),
        retrieval_ready_query=secret,
        security_role=ROLE_GUEST,
        retrieval_scope_applied="public_only",
        visibility_distribution_retrieved=dist,
        retrieval_security_summary=summary,
    )

    op = diag.to_log_details(forensic=False)
    assert op.get("sanitized") is True
    assert op.get("sanitization_policy") == POLICY_OPERATIONAL
    assert "retrieval_ready_query" not in op
    assert "retrieval_ready_query_len" in op
    chunk0 = op["retrieved_chunks"][0]
    assert "chunk_text_full" not in chunk0
    assert chunk0.get("text_preview")  # safe preview сохраняется
    assert "retrieval_security_summary" in op

    admin_log = diag.to_log_details(forensic=True)
    admin_log["retrieval_security_role"] = ROLE_ADMIN
    assert admin_log.get("sanitization_policy") == POLICY_FORENSIC_ADMIN
    assert "retrieval_ready_query" in admin_log
    assert secret.split("@")[0] not in admin_log.get("retrieval_ready_query", "")

    api_payload = sanitize_log_details(
        {
            "route": "rag",
            "retrieval_security_role": ROLE_GUEST,
            "retrieval_security_summary": summary,
            "user_input": secret,
            "retrieved_chunks": [{"chunk_text_full": secret, "text_preview": "p"}],
        },
        forensic=False,
    )
    assert api_payload.get("sanitized") is True
    assert "user_input" not in api_payload
    api_summary = api_payload.get("retrieval_security_summary") or {}
    assert api_summary.get("security_role") == ROLE_GUEST
    assert api_summary.get("visibility_distribution_retrieved")


def verify_ingestion_defaults() -> None:
    from services.retrieval_security.document_security import (
        DEFAULT_NEW_DOCUMENT_VISIBILITY,
        normalize_upload_visibility,
    )
    from services.retrieval_security.visibility import VISIBILITY_INTERNAL, VISIBILITY_PUBLIC

    assert DEFAULT_NEW_DOCUMENT_VISIBILITY == VISIBILITY_INTERNAL
    assert normalize_upload_visibility("public") == VISIBILITY_PUBLIC
    assert normalize_upload_visibility(None) == VISIBILITY_INTERNAL


def run_prior_smokes() -> None:
    scripts = [
        "test_p8_1_retrieval_security_wiring_smoke.py",
        "test_p8_2_security_aware_document_ingestion_smoke.py",
        "test_p8_3_logging_sanitization_smoke.py",
    ]
    for name in scripts:
        path = ROOT / "scripts" / name
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise AssertionError(f"{name} failed with code {proc.returncode}")


def main() -> int:
    os.chdir(ROOT)
    print("[assistant-flow] P8.4: role matrix …")
    verify_role_matrix()
    print("[assistant-flow] P8.4: diagnostics + sanitization …")
    verify_diagnostics_and_sanitization()
    print("[assistant-flow] P8.4: ingestion defaults …")
    verify_ingestion_defaults()
    print("[assistant-flow] P8.4: regression P8.1–P8.3 …")
    run_prior_smokes()
    print("[assistant-flow] test_p8_4_security_verification_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
