#!/usr/bin/env python3
"""
P9.6j — production RAG pipeline trace: why admin loses restricted recall.

  docker cp scripts/p9_6j_restricted_recall_forensic.py portfolio-test-assistant-flow-1:/app/scripts/
  docker exec portfolio-test-assistant-flow-1 python scripts/p9_6j_restricted_recall_forensic.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESTRICTED_MARKER = "P9.6B_RESTRICTED_VERIFICATION_DOC"
RESTRICTED_SOURCE = "p9_6b_restricted_handbook.txt"

QUERIES = [
    "Какой документ содержит confidential HR policy notes?",
    "Расскажи содержание документа P9.6B_RESTRICTED_VERIFICATION_DOC",
]


def _is_restricted(doc: Any, score: float | None = None) -> bool:
    text = getattr(doc, "page_content", "") or ""
    meta = getattr(doc, "metadata", None) or {}
    src = str(meta.get("source") or "")
    return RESTRICTED_MARKER in text or RESTRICTED_SOURCE in src


def _rank_table(raw: list[tuple[Any, float]], limit: int = 50) -> list[dict[str, Any]]:
    rows = []
    for i, (doc, score) in enumerate(raw[:limit]):
        meta = dict(getattr(doc, "metadata", None) or {})
        rows.append(
            {
                "rank": i,
                "score": score,
                "restricted": _is_restricted(doc, score),
                "source": meta.get("source"),
                "visibility": meta.get("visibility") or meta.get("document_visibility"),
                "preview": (getattr(doc, "page_content", "") or "")[:70],
            }
        )
    return rows


def _backend_raw_top_n(be, query: str, n: int, ctx) -> list[tuple[Any, float]]:
    """Raw vector hits without backend post-filter slice (direct store access where possible)."""
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval.chunk_metadata import apply_retrieval_metadata_contract

    name = be.backend_name
    if name == "chroma":
        store = be._store  # noqa: SLF001
        raw = store.native_similarity_search_with_score(query, k=n, where=None)
        out = []
        for rank, (doc, score) in enumerate(raw):
            meta = dict(getattr(doc, "metadata", None) or {})
            meta = apply_retrieval_metadata_contract(meta, backend="chroma", result_rank=rank)
            out.append(
                (
                    type("D", (), {"page_content": getattr(doc, "page_content", ""), "metadata": meta})(),
                    float(score),
                )
            )
        return out
    if name == "faiss":
        import numpy as np

        vec = be._embeddings.embed_query(query.strip())  # noqa: SLF001
        arr = np.array([vec], dtype=np.float32)
        ntotal = int(be._index.ntotal)  # noqa: SLF001
        k = min(n, ntotal)
        distances, indices = be._index.search(arr, k)  # noqa: SLF001
        out = []
        for i in range(k):
            idx = int(indices[0][i])
            if idx < 0:
                continue
            row = be._chunks[idx]  # noqa: SLF001
            meta = dict(row.get("metadata") or {})
            meta = apply_retrieval_metadata_contract(meta, backend="faiss", result_rank=i)
            out.append(
                (
                    type("D", (), {"page_content": row.get("page_content", ""), "metadata": meta})(),
                    float(distances[0][i]),
                )
            )
        return out
    # weaviate: use search with permissive + high top_k
    from services.retrieval_security.context import RetrievalSecurityContext

    admin = RetrievalSecurityContext.permissive_default()
    results = be.search(query, top_k=n, security_context=admin)
    return [
        (type("D", (), {"page_content": r.chunk.page_content, "metadata": r.chunk.metadata})(), r.score)
        for r in results
    ]


def _trace_rag_pipeline(rag, query: str, ctx) -> dict[str, Any]:
    from services.rag_query_service import _filter_chunks_by_max_distance

    k = rag._eff().rag_top_k  # noqa: SLF001
    thr = float(rag._eff().rag_max_distance)  # noqa: SLF001
    raw, _cache = rag._retrieve_raw(query, k, security_context=ctx)  # noqa: SLF001
    after_dist, miss = _filter_chunks_by_max_distance(raw, thr)
    result = rag.answer(query, top_k=k, security_context=ctx)
    return {
        "rag_top_k": k,
        "rag_max_distance": thr,
        "after_backend_search": len(raw),
        "restricted_after_backend": sum(1 for d, _ in raw if _is_restricted(d)),
        "after_max_distance": len(after_dist),
        "restricted_after_max_distance": sum(1 for d, _ in after_dist if _is_restricted(d)),
        "chunks_missing_score": miss,
        "answer_preview": (result.answer or "")[:120],
        "sources_count": len(result.sources),
        "fallback": result.used_fallback_without_context,
        "diag_fallback": getattr(result.diagnostics, "fallback_reason", None),
        "raw_rank_top10": _rank_table(raw, 10),
    }


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from dataclasses import replace

    from providers.rag_embeddings import build_openai_embeddings
    from services.retrieval.factory import build_retrieval_backend
    from services.retrieval_security.context import RetrievalSecurityContext
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
    from utils.config import load_config

    try:
        from interfaces.telegram_bot import build_rag_query_service
    except ImportError as exc:
        print(f"SKIP rag pipeline: {exc}")
        build_rag_query_service = None

    cfg = load_config()
    admin = build_retrieval_security_context_for_role("admin")
    emp = build_retrieval_security_context_for_role("employee")
    print("admin is_fully_unrestricted:", admin.is_fully_unrestricted())
    print("employee is_fully_unrestricted:", emp.is_fully_unrestricted())

    for q in QUERIES:
        print("\n" + "=" * 72)
        print("QUERY:", q)
        for backend in ("weaviate", "chroma", "faiss"):
            print(f"\n--- {backend} ---")
            cfg_b = replace(cfg, rag_backend=backend)
            emb = build_openai_embeddings(cfg_b)
            if backend == "chroma":
                from services.rag_chroma_store import ChromaRagStore

                be = build_retrieval_backend(
                    cfg_b,
                    chroma_store=ChromaRagStore(cfg_b, emb, persist_directory=ROOT / "storage" / "chroma"),
                    embeddings=emb,
                )
            else:
                be = build_retrieval_backend(cfg_b, chroma_store=None, embeddings=emb)

            raw50 = _backend_raw_top_n(be, q, 50, admin)
            pos = next((i for i, (d, _) in enumerate(raw50) if _is_restricted(d)), None)
            print(f"raw_top50: n={len(raw50)} restricted_position={pos}")
            if pos is not None and pos < 10:
                print(f"  restricted score={raw50[pos][1]}")

            be_admin = be.search(q, top_k=cfg_b.rag_top_k, security_context=admin)
            print(
                f"backend.search(admin, top_k={cfg_b.rag_top_k}): "
                f"n={len(be_admin)} restricted={sum(1 for r in be_admin if RESTRICTED_MARKER in r.chunk.page_content)}"
            )

            if build_rag_query_service and backend == os.getenv("P9_6J_RAG_BACKEND", "weaviate"):
                rag = build_rag_query_service(replace(cfg, rag_backend=backend))
                tr = _trace_rag_pipeline(rag, q, admin)
                print("RagQueryService.answer(admin):", {k: v for k, v in tr.items() if k != "raw_rank_top10"})
                for row in tr.get("raw_rank_top10") or []:
                    mark = " *RESTRICTED*" if row.get("restricted") else ""
                    print(f"  [{row['rank']}] dist={row['score']} src={row['source']!r}{mark}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
