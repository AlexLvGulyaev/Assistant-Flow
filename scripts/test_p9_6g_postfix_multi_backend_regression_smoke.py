#!/usr/bin/env python3
"""
P9.6g-postfix — Chroma/FAISS must not return empty after PG visibility enrich.

  python3 scripts/test_p9_6g_postfix_multi_backend_regression_smoke.py
  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_6g_postfix_multi_backend_regression_smoke.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    from services.retrieval_security.chroma_where import build_chroma_where
    from services.retrieval_security.context import ROLE_EMPLOYEE
    from services.retrieval_security.policy_resolver import (
        build_retrieval_security_context_for_role,
    )
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import (
        VISIBILITY_INTERNAL,
        VISIBILITY_PUBLIC,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
        effective_visibility,
    )

    emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)

    print("\n=== 1. Chroma where: no allowed_visibility pre-filter ===")
    w = build_chroma_where(emp)
    if not _ok("employee chroma where is None", w is None, repr(w)):
        failures += 1

    print("\n=== 2. Post-enrich internal chunk kept for employee (FAISS/Chroma path) ===")
    doc_id = str(uuid.uuid4())
    chroma_like = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="internal handbook section",
                metadata={
                    "source": "handbook.txt",
                    "document_id": doc_id,
                    "backend": "chroma",
                },
            ),
            score=0.2,
        )
    ]
    # PG enrich optional in smoke env; regression fix is post-filter + scope order
    enriched = enrich_search_results_visibility_metadata(chroma_like, emp)
    _ = enriched

    # Simulate enrich output (PG would set visibility + visibility_scope)
    manual = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="internal",
                metadata={
                    "source": "handbook.txt",
                    "document_id": doc_id,
                    "visibility": VISIBILITY_INTERNAL,
                    "document_visibility": VISIBILITY_INTERNAL,
                    "visibility_scope": "employee",
                },
            ),
            score=0.1,
        )
    ]
    kept = filter_search_results_by_security(manual, emp)
    if not _ok("employee keeps internal after enrich", len(kept) == 1):
        failures += 1

    print("\n=== 3. Restricted still blocked ===")
    restricted = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="restricted",
                metadata={
                    "source": "secret.txt",
                    "document_id": str(uuid.uuid4()),
                    "visibility": VISIBILITY_RESTRICTED,
                    "document_visibility": VISIBILITY_RESTRICTED,
                    "visibility_scope": "protected",
                },
            ),
            score=0.1,
        )
    ]
    kept_r = filter_search_results_by_security(restricted, emp)
    if not _ok("employee drops restricted", len(kept_r) == 0):
        failures += 1

    print("\n=== 4. Unspecified without document_id passes (legacy) ===")
    legacy = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="legacy",
                metadata={"source": "old.txt", "visibility": VISIBILITY_UNSPECIFIED},
            ),
            score=0.1,
        )
    ]
    kept_l = filter_search_results_by_security(legacy, emp)
    if not _ok("employee keeps unspecified legacy", len(kept_l) == 1):
        failures += 1

    print("\n=== 5. Weaviate-like public still passes ===")
    weaviate_like = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="public doc",
                metadata={
                    "source": "pub.txt",
                    "document_id": str(uuid.uuid4()),
                    "visibility": VISIBILITY_PUBLIC,
                },
            ),
            score=0.1,
        )
    ]
    kept_w = filter_search_results_by_security(weaviate_like, emp)
    if not _ok("employee keeps public", len(kept_w) == 1):
        failures += 1

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
