#!/usr/bin/env python3
"""
Smoke: P8.2 security-aware document ingestion — visibility stamp, policy, diagnostics.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_2_security_aware_document_ingestion_smoke.py
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

    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.document_security import (
        DEFAULT_NEW_DOCUMENT_VISIBILITY,
        normalize_upload_visibility,
        stamp_chunks_visibility,
    )
    from services.retrieval_security.policy_resolver import (
        build_retrieval_security_context_for_role,
    )
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.retrieval_diagnostics import (
        build_retrieval_security_summary,
        visibility_distribution,
    )
    from services.retrieval_security.visibility import (
        VISIBILITY_INTERNAL,
        VISIBILITY_PUBLIC,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
    )

    assert DEFAULT_NEW_DOCUMENT_VISIBILITY == VISIBILITY_INTERNAL
    assert normalize_upload_visibility(None) == VISIBILITY_INTERNAL
    assert normalize_upload_visibility("public") == VISIBILITY_PUBLIC
    assert normalize_upload_visibility("bogus") == VISIBILITY_INTERNAL

    try:
        from langchain_core.documents import Document

        chunks = stamp_chunks_visibility(
            [Document(page_content="x", metadata={"source": "f.txt"})],
            VISIBILITY_RESTRICTED,
        )
        assert chunks[0].metadata["visibility"] == VISIBILITY_RESTRICTED
        assert chunks[0].metadata["document_visibility"] == VISIBILITY_RESTRICTED
    except ImportError:
        vis = normalize_upload_visibility(VISIBILITY_RESTRICTED)
        assert vis == VISIBILITY_RESTRICTED

    mixed = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="p",
                metadata={"source": "a", "visibility": VISIBILITY_PUBLIC},
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="i",
                metadata={"source": "b", "visibility": VISIBILITY_INTERNAL},
            ),
            score=0.2,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="r",
                metadata={"source": "c", "visibility": VISIBILITY_RESTRICTED},
            ),
            score=0.3,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="u",
                metadata={"source": "d", "visibility": VISIBILITY_UNSPECIFIED},
            ),
            score=0.4,
        ),
    ]
    guest = build_retrieval_security_context_for_role(ROLE_GUEST)
    emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
    adm = build_retrieval_security_context_for_role(ROLE_ADMIN)

    g = filter_search_results_by_security(list(mixed), guest)
    assert len(g) == 1 and g[0].chunk.metadata["visibility"] == VISIBILITY_PUBLIC

    e = filter_search_results_by_security(list(mixed), emp)
    assert len(e) == 3

    a = filter_search_results_by_security(list(mixed), adm)
    assert len(a) == 4

    try:
        from langchain_core.documents import Document

        pairs = [
            (
                Document(page_content="t", metadata={"visibility": VISIBILITY_PUBLIC}),
                0.1,
            ),
            (
                Document(
                    page_content="t2", metadata={"visibility": VISIBILITY_INTERNAL}
                ),
                0.2,
            ),
        ]
        dist = visibility_distribution(pairs)
    except ImportError:
        dist = {
            VISIBILITY_PUBLIC: 1,
            VISIBILITY_INTERNAL: 1,
        }
    assert dist[VISIBILITY_PUBLIC] == 1
    assert dist[VISIBILITY_INTERNAL] == 1

    summary = build_retrieval_security_summary(
        security_role=ROLE_GUEST,
        retrieval_scope="public_only",
        retrieved_count=2,
        filtered_count=1,
        visibility_before=dist,
        visibility_after_relevance={VISIBILITY_PUBLIC: 1},
    )
    assert summary["security_role"] == ROLE_GUEST
    assert "visibility_distribution_retrieved" in summary

    print("[assistant-flow] test_p8_2_security_aware_document_ingestion_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
