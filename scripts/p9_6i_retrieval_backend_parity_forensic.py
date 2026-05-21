#!/usr/bin/env python3
"""
P9.6i — forensic: restricted chunk parity across Weaviate/Chroma/FAISS + cache fingerprint.

  docker exec portfolio-test-assistant-flow-1 python scripts/p9_6i_retrieval_backend_parity_forensic.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESTRICTED_FILENAME = "p9_6b_restricted_handbook.txt"
RESTRICTED_MARKER = "P9.6B_RESTRICTED_VERIFICATION_DOC"
DEFAULT_QUERY = "политика конфиденциальности персональных данных restricted verification"


def _summarize_results(
    label: str, results: list[Any], *, limit: int = 5
) -> None:
    print(f"\n--- {label} (n={len(results)}) ---")
    for i, r in enumerate(results[:limit]):
        meta = r.chunk.metadata if hasattr(r, "chunk") else {}
        vis = meta.get("visibility") or meta.get("document_visibility") or "—"
        src = meta.get("source") or "—"
        doc = meta.get("document_id") or "—"
        text = (r.chunk.page_content if hasattr(r, "chunk") else "")[:80]
        score = getattr(r, "score", None)
        hit = RESTRICTED_MARKER in text or RESTRICTED_FILENAME in str(src)
        print(
            f"  [{i}] score={score} vis={vis} src={src!r} doc_id={str(doc)[:8]}… "
            f"restricted_hit={hit} text={text!r}…"
        )


def _chroma_raw_search(store, query: str, k: int, where: dict | None) -> list[Any]:
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval.chunk_metadata import apply_retrieval_metadata_contract

    raw = store.native_similarity_search_with_score(query, k=k, where=where)
    out = []
    for rank, (doc, score) in enumerate(raw):
        meta = dict(getattr(doc, "metadata", None) or {})
        meta = apply_retrieval_metadata_contract(meta, backend="chroma", result_rank=rank)
        out.append(
            RetrievalSearchResult(
                chunk=RetrievalChunk(page_content=getattr(doc, "page_content", "") or "", metadata=meta),
                score=float(score),
            )
        )
    return out


def _probe_postgres_restricted() -> dict[str, Any]:
    out: dict[str, Any] = {"in_pg": False, "document_id": None, "visibility": None, "chunk_count": 0}
    try:
        from repositories.connection import get_connection
        from repositories.document_repository import DocumentRepository

        with get_connection() as conn:
            repo = DocumentRepository()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.id::text,
                           COALESCE(
                               NULLIF(TRIM(dc.metadata->>'visibility'), ''),
                               NULLIF(TRIM(dc.metadata->>'document_visibility'), ''),
                               'unspecified'
                           ) AS vis,
                           COUNT(dc.id) AS n
                    FROM documents d
                    JOIN document_versions dv ON dv.document_id = d.id AND dv.is_active
                    JOIN document_chunks dc ON dc.document_version_id = dv.id
                    WHERE LOWER(d.source_filename) = LOWER(%s)
                    GROUP BY d.id, vis
                    LIMIT 5
                    """,
                    (RESTRICTED_FILENAME,),
                )
                rows = cur.fetchall()
            conn.commit()
        if rows:
            out["in_pg"] = True
            out["document_id"] = rows[0][0]
            out["visibility"] = rows[0][1]
            out["chunk_count"] = sum(int(r[2]) for r in rows)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _probe_backend(name: str, query: str, top_k: int = 5) -> dict[str, Any]:
    from dataclasses import replace

    from providers.rag_embeddings import build_openai_embeddings
    from services.retrieval.base import RetrievalSearchResult
    from services.retrieval.factory import build_retrieval_backend
    from services.retrieval_security.chunk_visibility_enrich import (
        enrich_search_results_visibility_metadata,
    )
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from utils.config import load_config

    cfg = load_config()
    cfg = replace(cfg, rag_backend=name)
    emb = build_openai_embeddings(cfg)
    report: dict[str, Any] = {"backend": name, "collection_count": None, "error": None}

    try:
        if name == "chroma":
            from services.rag_chroma_store import ChromaRagStore

            chroma_dir = ROOT / "storage" / "chroma"
            if not cfg.chroma_use_http:
                chroma_dir.mkdir(parents=True, exist_ok=True)
            store = ChromaRagStore(cfg, emb, persist_directory=chroma_dir)
            be = build_retrieval_backend(cfg, chroma_store=store, embeddings=emb)
            report["collection_count"] = be.collection_count()
            admin = build_retrieval_security_context_for_role(ROLE_ADMIN)
            emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
            # raw chroma (no post-filter)
            k_raw = top_k
            k_over = min(be.collection_count() or top_k, max(top_k * 8, top_k))
            raw_k = _chroma_raw_search(store, query, k_raw, None)
            raw_over = _chroma_raw_search(store, query, k_over, None)
            report["raw_top_k"] = _count_restricted_hits(raw_k)
            report["raw_oversample_8x"] = _count_restricted_hits(raw_over)
            final_admin = be.search(query, top_k=top_k, security_context=admin)
            final_emp = be.search(query, top_k=top_k, security_context=emp)
            report["final_admin"] = _count_restricted_hits(final_admin)
            report["final_employee"] = _count_restricted_hits(final_emp)
            # pipeline breakdown on oversample raw
            enriched = enrich_search_results_visibility_metadata(raw_over, emp)
            filtered = filter_search_results_by_security(raw_over, emp)
            report["pipeline_employee"] = {
                "raw": len(raw_over),
                "after_enrich": len(enriched),
                "after_filter": len(filtered),
                "restricted_in_raw": report["raw_oversample_8x"]["restricted_hits"],
                "restricted_after_filter": _count_restricted_hits(filtered)["restricted_hits"],
            }
        else:
            be = build_retrieval_backend(cfg, chroma_store=None, embeddings=emb)
            report["collection_count"] = be.collection_count()
            admin = build_retrieval_security_context_for_role(ROLE_ADMIN)
            emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
            final_admin = be.search(query, top_k=top_k, security_context=admin)
            final_emp = be.search(query, top_k=top_k, security_context=emp)
            report["final_admin"] = _count_restricted_hits(final_admin)
            report["final_employee"] = _count_restricted_hits(final_emp)
            # admin path = raw-ish (unrestricted)
            report["raw_top_k"] = report["final_admin"]
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report


def _count_restricted_hits(results: list[Any]) -> dict[str, Any]:
    hits = 0
    for r in results:
        text = r.chunk.page_content if hasattr(r, "chunk") else ""
        meta = r.chunk.metadata if hasattr(r, "chunk") else {}
        src = str(meta.get("source") or "")
        if RESTRICTED_MARKER in text or RESTRICTED_FILENAME in src:
            hits += 1
    return {"total": len(results), "restricted_hits": hits}


def _cache_fingerprint_audit() -> None:
    from services.cache.retrieval_cache_key import (
        build_retrieval_fingerprint,
        current_retrieval_generation,
        fingerprint_to_key_hash,
    )
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
    from utils.config import load_config

    cfg = load_config()
    q = "test query"
    admin = build_retrieval_security_context_for_role("admin")
    emp = build_retrieval_security_context_for_role("employee")

    print("\n=== Cache fingerprint audit ===")
    print(f"RAG_RETRIEVAL_GENERATION={current_retrieval_generation()!r}")
    for backend in ("weaviate", "chroma", "faiss"):
        from dataclasses import replace

        cfg_b = replace(cfg, rag_backend=backend)
        fp_a = build_retrieval_fingerprint(
            cfg_b, query=q, top_k=5, security_fingerprint_extra=admin.to_cache_fingerprint_extra()
        )
        fp_e = build_retrieval_fingerprint(
            cfg_b, query=q, top_k=5, security_fingerprint_extra=emp.to_cache_fingerprint_extra()
        )
        print(f"\nbackend={backend}")
        print(fp_a)
        print(f"  admin hash={fingerprint_to_key_hash(fp_a)[:16]}…")
        print(f"  employee hash={fingerprint_to_key_hash(fp_e)[:16]}…")
        print(f"  admin≠employee: {fingerprint_to_key_hash(fp_a) != fingerprint_to_key_hash(fp_e)}")


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()
    query = (os.getenv("P9_6I_QUERY") or DEFAULT_QUERY).strip()
    top_k = int(os.getenv("P9_6I_TOP_K") or "5")

    print("=== P9.6i retrieval backend parity forensic ===")
    print(f"query={query!r} top_k={top_k}")

    pg = _probe_postgres_restricted()
    print("\n=== PostgreSQL restricted doc ===")
    print(pg)

    for backend in ("weaviate", "chroma", "faiss"):
        rep = _probe_backend(backend, query, top_k)
        print(f"\n=== Backend {backend} ===")
        for k, v in rep.items():
            print(f"  {k}: {v}")

    _cache_fingerprint_audit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
