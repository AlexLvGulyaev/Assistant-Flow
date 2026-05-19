#!/usr/bin/env python3
"""
Smoke: P8.3 retrieval-aware logging sanitization.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_3_logging_sanitization_smoke.py
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

    from services.rag_types import RagRequestDiagnostics
    from services.security.log_sanitizer import (
        POLICY_FORENSIC_ADMIN,
        POLICY_OPERATIONAL,
        sanitize_log_details,
        sanitize_text_for_log,
    )

    assert hasattr(RagRequestDiagnostics, "emit_stdout")

    email = "client@example.com"
    phone = "+7 999 123-45-67"
    long_num = "1234567890123456"
    payload = (
        f"Contact {email} or {phone}, card {long_num}. "
        + ("x" * 5000)
    )

    masked = sanitize_text_for_log(payload, max_len=500)
    assert email not in masked
    assert phone.replace(" ", "") not in masked.replace(" ", "")
    assert long_num not in masked

    op = sanitize_log_details(
        {
            "route": "rag",
            "user_input": payload,
            "retrieval_ready_query": payload,
            "transcript": payload,
            "chunk_text_full": "secret chunk " + payload,
            "retrieved_chunks": [
                {
                    "source": "doc.txt",
                    "score": 0.9,
                    "text_preview": payload[:120],
                    "chunk_text_full": payload,
                }
            ],
            "query_preview": "short",
        },
        forensic=False,
    )
    assert op.get("sanitized") is True
    assert op.get("sanitization_policy") == POLICY_OPERATIONAL
    assert "user_input" not in op
    assert "retrieval_ready_query" not in op
    assert "transcript" not in op
    assert "chunk_text_full" not in op
    assert "transcript_preview" in op or "transcript_chars" in op
    redacted = op.get("redacted_fields") or []
    assert "user_input" in redacted
    assert "retrieval_ready_query" in redacted
    chunks = op.get("retrieved_chunks") or []
    assert chunks and chunks[0].get("chunk_text_full_redacted") is True
    assert "chunk_text_full" not in (chunks[0] or {})

    admin = sanitize_log_details(
        {
            "retrieval_security_role": "admin",
            "user_input": email + " " + phone,
            "retrieval_ready_query": "follow-up: " + email,
            "retrieved_chunks": [{"chunk_text_full": "full " + email}],
        },
        forensic=False,
    )
    assert admin.get("sanitization_policy") == POLICY_FORENSIC_ADMIN
    assert email not in str(admin.get("user_input") or "")
    assert "user_input" in admin

    diag = RagRequestDiagnostics(
        query_preview="q",
        top_k=3,
        retrieved_count=1,
        filtered_count=1,
        relevance_threshold=0.0,
        chunks_missing_score=0,
        unique_sources_count=1,
        scores=[0.5],
        context_chars=10,
        fallback_reason=None,
        retrieved_chunks=[],
        retrieval_ready_query=payload,
    )
    log_op = diag.to_log_details(forensic=False)
    assert log_op.get("sanitized") is True
    assert "retrieval_ready_query" not in log_op

    log_admin = diag.to_log_details(forensic=True)
    assert log_admin.get("sanitization_policy") == POLICY_FORENSIC_ADMIN
    assert "retrieval_ready_query" in log_admin
    assert email not in log_admin.get("retrieval_ready_query", "")

    # Имитация финального шага Admin API (truncate_details → sanitize_log_details).
    api_like = sanitize_log_details(
        {
            "route": "rag",
            "user_input": payload,
            "retrieval_ready_query": payload,
            "retrieved_chunks": [{"chunk_text_full": payload, "text_preview": "p"}],
        },
        forensic=False,
    )
    assert api_like.get("sanitized") is True
    assert "user_input" not in api_like
    api_chunks = api_like.get("retrieved_chunks") or []
    assert api_chunks and "chunk_text_full" not in (api_chunks[0] or {})

    print("OK: P8.3 logging sanitization smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
