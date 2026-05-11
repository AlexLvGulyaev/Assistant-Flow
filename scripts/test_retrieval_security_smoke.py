#!/usr/bin/env python3
"""
Smoke: retrieval security groundwork (P6.7).

Проверки безопасности retrieval, Chroma where, post-filter, masking.
Рекомендуется запуск в portfolio-контейнере:

  docker exec portfolio-test-assistant-flow-1 python scripts/test_retrieval_security_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval.chroma_backend import ChromaBackend
    from services.retrieval_security.chroma_where import build_chroma_where
    from services.retrieval_security.context import (
        ROLE_GUEST,
        RetrievalSecurityContext,
    )
    from services.retrieval_security.masking import (
        mask_common_pii_with_telemetry,
        mask_email,
        mask_phone,
    )
    from services.retrieval_security.result_filter import filter_search_results_by_security

    # --- build_chroma_where ---
    w_none = build_chroma_where(RetrievalSecurityContext.permissive_default())
    assert w_none is None, "permissive default не должен задавать where"

    ctx_guest = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset({"public.md"}),
        retrieval_scope="kb_public",
    )
    w_src = build_chroma_where(ctx_guest)
    assert w_src == {"source": {"$in": ["public.md"]}}

    ctx_meta = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset({"x.md"}),
        metadata_filters=(("visibility", "public"),),
    )
    w_and = build_chroma_where(ctx_meta)
    assert "$and" in w_and
    assert len(w_and["$and"]) == 2

    # --- post-filter: denied source ---
    results_mixed = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="p1",
                metadata={"source": "allowed.md", "visibility": "public"},
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="p2",
                metadata={"source": "secret.md", "visibility": "public"},
            ),
            score=0.2,
        ),
    ]
    ctx_allow_one = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset({"allowed.md"}),
        retrieval_scope="kb_public",
    )
    filt = filter_search_results_by_security(results_mixed, ctx_allow_one)
    assert len(filt) == 1
    assert filt[0].chunk.metadata["source"] == "allowed.md"

    # --- metadata_filters + tags ---
    with_tags = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="t1",
                metadata={
                    "source": "a.md",
                    "visibility": "internal",
                    "tags": ["hr", "policy"],
                },
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="t2",
                metadata={
                    "source": "a.md",
                    "visibility": "public",
                    "tags": ["public"],
                },
            ),
            score=0.2,
        ),
    ]
    ctx_vis = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset({"a.md"}),
        metadata_filters=(("visibility", "public"),),
        required_tags=frozenset({"public"}),
    )
    ftags = filter_search_results_by_security(with_tags, ctx_vis)
    assert len(ftags) == 1
    assert "public" in ftags[0].chunk.metadata.get("tags", [])

    # --- masking ---
    assert "[PHONE]" in mask_phone("call +7 999 123-45-67 now")
    assert "[EMAIL]" in mask_email("write user@example.com please")
    masked = mask_common_pii_with_telemetry("x@y.co 12345678")
    assert "[EMAIL]" in masked or "[PII]" in masked

    # --- ChromaBackend + fake store: where passed + post-filter ---
    class FakeStore:
        def __init__(self) -> None:
            self.last_where: dict[str, Any] | None = None

        def native_similarity_search_with_score(
            self,
            query: str,
            k: int,
            *,
            where: dict[str, Any] | None = None,
        ) -> list[tuple[Any, float]]:
            self.last_where = where
            return [
                (
                    SimpleNamespace(
                        page_content="ok",
                        metadata={"source": "public.md", "visibility": "public"},
                    ),
                    0.05,
                ),
                (
                    SimpleNamespace(
                        page_content="leak",
                        metadata={"source": "other.md", "visibility": "public"},
                    ),
                    0.06,
                ),
            ]

        def collection_count(self) -> int:
            return 2

    fake = FakeStore()
    backend = ChromaBackend(fake)  # type: ignore[arg-type]
    out_all = backend.search("q", top_k=5)
    assert len(out_all) == 2

    ctx_only_public = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset({"public.md"}),
        retrieval_scope="kb_public",
    )
    out_f = backend.search("q", top_k=5, security_context=ctx_only_public)
    assert fake.last_where is not None
    assert "public.md" in str(fake.last_where)
    assert len(out_f) == 1
    assert out_f[0].chunk.page_content == "ok"

    # пустой allowed_sources: Chroma не получает $in:[] (ValueError); where=None, post-filter
    ctx_empty = RetrievalSecurityContext(
        role=ROLE_GUEST,
        allowed_sources=frozenset(),
        retrieval_scope="locked",
    )
    w_empty = build_chroma_where(ctx_empty)
    assert w_empty is None
    fake2 = FakeStore()
    backend2 = ChromaBackend(fake2)  # type: ignore[arg-type]
    out_empty = backend2.search("q", top_k=5, security_context=ctx_empty)
    assert fake2.last_where is None
    assert out_empty == []

    print("[assistant-flow] test_retrieval_security_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
