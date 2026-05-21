#!/usr/bin/env python3
"""
P9.6g — restricted retrieval must not leak into generation context for non-admin.

  docker exec portfolio-test-admin-api-1 python scripts/test_p9_6g_restricted_retrieval_leakage_smoke.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESTRICTED_MARKER = "P9.6B_RESTRICTED_VERIFICATION_DOC"
RESTRICTED_FILENAME = "p9_6b_restricted_handbook.txt"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return cond


def main() -> int:
    os.chdir(ROOT)
    failures = 0

    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.chunk_visibility_enrich import (
        enrich_search_results_visibility_metadata,
    )
    from services.retrieval_security.context import ROLE_EMPLOYEE
    from services.retrieval_security.policy_resolver import (
        build_retrieval_security_context_for_role,
    )
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import VISIBILITY_RESTRICTED

    print("\n=== 1. Weaviate-style metadata + PG enrich → employee filter ===")
    restricted_doc_id: str | None = None
    try:
        from repositories.connection import get_connection
        from repositories.document_repository import DocumentRepository

        with get_connection() as conn:
            repo = DocumentRepository()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.id::text
                    FROM documents d
                    WHERE LOWER(d.source_filename) = LOWER(%s)
                    LIMIT 1
                    """,
                    (RESTRICTED_FILENAME,),
                )
                row = cur.fetchone()
            if row:
                restricted_doc_id = str(row[0])
            conn.commit()
    except Exception as exc:
        print(f"  (skip PG enrich test: {exc})")
        restricted_doc_id = None

    emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
    weaviate_like = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content=f"Secret HR policy notes in {RESTRICTED_MARKER}",
                metadata={
                    "source": RESTRICTED_FILENAME,
                    "document_id": restricted_doc_id or str(uuid.uuid4()),
                    "chunk_id": "w1",
                },
            ),
            score=0.05,
        ),
    ]

    if restricted_doc_id:
        enriched = enrich_search_results_visibility_metadata(weaviate_like, emp)
        vis = enriched[0].chunk.metadata.get("visibility")
        if not _ok("enrich resolves restricted visibility from PG", vis == VISIBILITY_RESTRICTED, vis):
            failures += 1
        filtered = filter_search_results_by_security(enriched, emp)
        if not _ok("employee filter drops restricted after enrich", len(filtered) == 0):
            failures += 1
    else:
        print("  ~ restricted verification doc not in DB — enrich/filter unit checks skipped")

    internal_ok = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="public handbook",
                metadata={"source": "handbook.txt", "visibility": "internal"},
            ),
            score=0.1,
        ),
    ]
    if not _ok(
        "internal chunk passes employee filter",
        len(filter_search_results_by_security(internal_ok, emp)) == 1,
    ):
        failures += 1

    if restricted_doc_id:
        pre_restricted = [
            RetrievalSearchResult(
                chunk=RetrievalChunk(
                    page_content="secret",
                    metadata={
                        "source": RESTRICTED_FILENAME,
                        "visibility": VISIBILITY_RESTRICTED,
                        "document_id": restricted_doc_id,
                    },
                ),
                score=0.05,
            ),
        ]
        if not _ok(
            "restricted visibility always blocked for employee",
            len(filter_search_results_by_security(pre_restricted, emp)) == 0,
        ):
            failures += 1

    print("\n=== 2. Live RAG answer (employee security context) ===")
    try:
        from interfaces.telegram_bot import build_rag_query_service
        from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
        from utils.config import load_config

        cfg = load_config()
        if not (cfg.openai_api_key or "").strip():
            print("  ~ skip live RAG: no OPENAI_API_KEY")
        else:
            svc = build_rag_query_service(cfg)
            emp_ctx = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
            q = "Какой документ содержит confidential HR policy notes?"
            result = svc.answer(q, top_k=8, security_context=emp_ctx)
            ans = (result.answer or "").lower()
            leak = RESTRICTED_MARKER.lower() in ans or "restricted_verification" in ans
            if not _ok("employee answer has no restricted doc name leak", not leak, ans[:120]):
                failures += 1
            if not _ok("employee has no restricted sources", len(result.sources) == 0, str(len(result.sources))):
                failures += 1
            adm_ctx = build_retrieval_security_context_for_role("admin")
            adm = svc.answer(q, top_k=8, security_context=adm_ctx)
            adm_ans = (adm.answer or "").lower()
            if not _ok(
                "admin may retrieve (answer or sources non-empty)",
                len(adm.sources) > 0 or RESTRICTED_MARKER.lower() in adm_ans or len(adm_ans) > 20,
                f"sources={len(adm.sources)}",
            ):
                failures += 1
    except Exception as exc:
        print(f"  ✗ live RAG block failed: {exc}")
        failures += 1

    print(f"\n{'FAIL' if failures else 'PASS'}: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
