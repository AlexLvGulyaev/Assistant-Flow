#!/usr/bin/env python3
"""
Smoke: P8.1 retrieval security wiring — policy resolver, visibility, cache fingerprint, masking.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_1_retrieval_security_wiring_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.cache.retrieval_cache_key import build_retrieval_fingerprint
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.context import (
        ROLE_ADMIN,
        ROLE_EMPLOYEE,
        ROLE_GUEST,
        RetrievalSecurityContext,
    )
    from services.retrieval_security.masking import mask_common_pii_with_telemetry
    from services.retrieval_security.policy_resolver import (
        build_retrieval_security_context_for_role,
        resolve_role_for_telegram_user,
    )
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import (
        VISIBILITY_INTERNAL,
        VISIBILITY_PUBLIC,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
    )
    from utils.config import load_config

    # --- policy resolver roles ---
    os.environ.pop("TELEGRAM_ADMIN_USER_IDS", None)
    os.environ.pop("TELEGRAM_GUEST_USER_IDS", None)
    os.environ["TELEGRAM_DEFAULT_RETRIEVAL_ROLE"] = "employee"
    assert resolve_role_for_telegram_user(999001) == ROLE_EMPLOYEE

    os.environ["TELEGRAM_ADMIN_USER_IDS"] = "42,100"
    assert resolve_role_for_telegram_user(42) == ROLE_ADMIN
    assert resolve_role_for_telegram_user(100) == ROLE_ADMIN

    os.environ["TELEGRAM_GUEST_USER_IDS"] = "7"
    assert resolve_role_for_telegram_user(7) == ROLE_GUEST
    assert resolve_role_for_telegram_user(42) == ROLE_ADMIN  # admin wins

    guest_ctx = build_retrieval_security_context_for_role(ROLE_GUEST)
    emp_ctx = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
    admin_ctx = build_retrieval_security_context_for_role(ROLE_ADMIN)
    assert guest_ctx.is_fully_unrestricted() is False
    assert emp_ctx.is_fully_unrestricted() is False
    assert admin_ctx.is_fully_unrestricted() is True
    assert guest_ctx.allowed_visibility == frozenset({VISIBILITY_PUBLIC})
    assert VISIBILITY_RESTRICTED not in (emp_ctx.allowed_visibility or frozenset())

    # --- visibility post-filter ---
    mixed = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="pub",
                metadata={"source": "a.md", "visibility": VISIBILITY_PUBLIC},
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="int",
                metadata={"source": "b.md", "visibility": VISIBILITY_INTERNAL},
            ),
            score=0.2,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="legacy",
                metadata={"source": "c.md", "visibility": VISIBILITY_UNSPECIFIED},
            ),
            score=0.3,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="sec",
                metadata={"source": "d.md", "document_visibility": VISIBILITY_RESTRICTED},
            ),
            score=0.4,
        ),
    ]

    g_out = filter_search_results_by_security(list(mixed), guest_ctx)
    assert len(g_out) == 1
    assert g_out[0].chunk.metadata["source"] == "a.md"

    e_out = filter_search_results_by_security(list(mixed), emp_ctx)
    e_src = {r.chunk.metadata["source"] for r in e_out}
    assert e_src == {"a.md", "b.md", "c.md"}

    a_out = filter_search_results_by_security(list(mixed), admin_ctx)
    assert len(a_out) == 4

    # --- cache fingerprint isolation ---
    cfg = load_config()
    fp_guest = build_retrieval_fingerprint(
        cfg,
        query="same query",
        top_k=5,
        security_fingerprint_extra=guest_ctx.to_cache_fingerprint_extra(),
    )
    fp_emp = build_retrieval_fingerprint(
        cfg,
        query="same query",
        top_k=5,
        security_fingerprint_extra=emp_ctx.to_cache_fingerprint_extra(),
    )
    fp_admin = build_retrieval_fingerprint(
        cfg,
        query="same query",
        top_k=5,
        security_fingerprint_extra=admin_ctx.to_cache_fingerprint_extra(),
    )
    assert fp_guest != fp_emp
    assert "retrieval_security=" in fp_guest
    assert "retrieval_security=" in fp_emp
    assert "retrieval_security=" not in fp_admin

    # --- pre-LLM masking ---
    masked = mask_common_pii_with_telemetry(
        "contact user@corp.ru tel +79991234567 id 123456789012"
    )
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked or "[PII]" in masked

    # --- log sanitization tier ---
    from services.rag_types import RagRequestDiagnostics, RagRetrievedChunkDiagnostics

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
        fallback_reason="none",
        retrieved_chunks=(
            RagRetrievedChunkDiagnostics(
                source="x.md",
                score=0.1,
                passed_filter=True,
                text_preview="prev",
                chunk_text_full="full secret body",
            ),
        ),
        retrieval_ready_query="full query string",
        security_role=ROLE_GUEST,
        retrieval_scope_applied="public_only",
    )
    summary = diag.to_log_details(forensic=False)
    assert "retrieval_ready_query" not in summary
    assert "chunk_text_full" not in summary["retrieved_chunks"][0]
    forensic = diag.to_log_details(forensic=True)
    assert forensic.get("retrieval_ready_query") == "full query string"
    assert forensic["retrieved_chunks"][0].get("chunk_text_full") == "full secret body"

    print("[assistant-flow] test_p8_1_retrieval_security_wiring_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
