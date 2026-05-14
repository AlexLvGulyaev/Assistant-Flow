#!/usr/bin/env python3
"""
Audit duplicate RAG chunks (PostgreSQL metadata, vector search, processing_logs).

Run from repository root (inside portfolio container or local venv with deps):

  python scripts/test_rag_duplicate_chunks_audit.py
  python scripts/test_rag_duplicate_chunks_audit.py --query "Что можете сказать про LLM?"
  python scripts/test_rag_duplicate_chunks_audit.py --source-substr it_ai_glossary_large

Exit codes:
  0 — no **hard** failures (warnings may be printed: legacy logs, historical PG preview duplicates).
  1 — post-dedupe retrieval still has duplicate bodies, dedupe noop on raw dups, hard PG
      integrity (duplicate chunk_index / chroma_id), or duplicate chunk ids in logs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _norm_text(t: str | None) -> str:
    return " ".join((t or "").split())


def _fp16(t: str | None) -> str:
    import hashlib

    s = _norm_text(t)
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _pg_checks() -> tuple[list[str], list[str]]:
    """Returns (hard_errors, warnings). Identical preview rows on active versions → warning only."""
    errs: list[str] = []
    warns: list[str] = []
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        print("[rag_dup_audit] SKIP: DATABASE_URL unset — PostgreSQL checks skipped", flush=True)
        return errs, warns
    try:
        from psycopg.rows import dict_row

        from repositories.connection import get_connection
    except Exception as exc:
        errs.append(f"postgres_import:{type(exc).__name__}:{exc}")
        return errs, warns

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT document_version_id::text AS v, chunk_index, COUNT(*)::bigint AS c
                    FROM document_chunks
                    GROUP BY document_version_id, chunk_index
                    HAVING COUNT(*) > 1
                    LIMIT 20
                    """
                )
                rows = list(cur.fetchall())
                if rows:
                    errs.append(f"pg_dup_chunk_index:{rows}")

                cur.execute(
                    """
                    SELECT chroma_collection, chroma_id, COUNT(*)::bigint AS c
                    FROM document_chunks
                    GROUP BY chroma_collection, chroma_id
                    HAVING COUNT(*) > 1
                    LIMIT 20
                    """
                )
                rows2 = list(cur.fetchall())
                if rows2:
                    errs.append(f"pg_dup_chroma_id:{rows2}")

                cur.execute(
                    """
                    WITH active AS (
                        SELECT id FROM document_versions WHERE is_active = true
                    )
                    SELECT chunk_text_preview, COUNT(*)::bigint AS c
                    FROM document_chunks
                    WHERE document_version_id IN (SELECT id FROM active)
                      AND chunk_text_preview IS NOT NULL
                      AND length(trim(chunk_text_preview)) > 40
                    GROUP BY chunk_text_preview
                    HAVING COUNT(*) > 1
                    LIMIT 10
                    """
                )
                rows3 = list(cur.fetchall())
                if rows3:
                    warns.append(
                        "pg_warn_identical_preview_active_versions (historical / metadata; "
                        "not equivalent to post-dedupe retrieval context): "
                        + json.dumps(rows3, default=str, ensure_ascii=False)[:2000]
                    )
    except Exception as exc:
        errs.append(f"postgres_query:{type(exc).__name__}:{exc}")
    return errs, warns


def _last_rag_log_dupes() -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return errs, warns
    try:
        from repositories.connection import get_connection
        from repositories.processing_logs_repository import ProcessingLogsRepository
    except Exception as exc:
        return [f"log_import:{type(exc).__name__}:{exc}"], []
    try:
        repo = ProcessingLogsRepository()
        with get_connection() as conn:
            rows = repo.list_recent_rag_events(conn, limit=5)
        for row in rows:
            det = row.get("details")
            if not isinstance(det, dict):
                continue
            chunks = det.get("retrieved_chunks")
            if not isinstance(chunks, list) or len(chunks) < 2:
                continue
            fps = []
            cids: list[str] = []
            for c in chunks:
                if not isinstance(c, dict):
                    continue
                fp_i = str(c.get("text_fp") or "").strip()
                if fp_i:
                    fps.append(fp_i[:16])
                else:
                    prev = str(c.get("text_preview") or c.get("chunk_text_full") or "")
                    fps.append(_fp16(prev))
                cid = str(c.get("chunk_id") or c.get("chroma_id") or c.get("vector_id") or "").strip()
                if cid:
                    cids.append(cid)
            dup_fp = len(fps) >= 2 and len(fps) != len(set(fps))
            dedupe_flag = det.get("retrieval_dedupe_applied") is True
            dup_removed = int(det.get("retrieved_duplicate_count") or 0)
            if dup_fp:
                if dedupe_flag and dup_removed > 0:
                    errs.append(
                        f"log_bug_dup_text_fp_after_dedupe:execution_id={row.get('execution_id')!r} "
                        f"removed={dup_removed} fps={fps}"
                    )
                elif dedupe_flag:
                    errs.append(
                        f"log_bug_dup_text_fp_dedupe_flag_no_removed:execution_id="
                        f"{row.get('execution_id')!r} fps={fps}"
                    )
                else:
                    warns.append(
                        f"log_warn_legacy_dup_text_fp (pre-dedupe logging): execution_id="
                        f"{row.get('execution_id')!r} fps={fps[:12]}"
                    )
            if len(cids) >= 2 and len(cids) != len(set(cids)):
                errs.append(
                    f"log_dup_chunk_id:execution_id={row.get('execution_id')!r} "
                    f"ids_sample={cids[:8]}"
                )
            break
    except Exception as exc:
        errs.append(f"log_scan:{type(exc).__name__}:{exc}")
    return errs, warns


def _vector_search_dupes(
    *,
    query: str,
    top_k: int,
    source_substr: str | None,
) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print(
            "[rag_dup_audit] SKIP: OPENAI_API_KEY unset — vector search skipped",
            flush=True,
        )
        return errs, warns

    def _resolve(p: str) -> Path:
        pp = Path(p)
        return pp if pp.is_absolute() else ROOT / pp

    try:
        from langchain_core.documents import Document

        from providers.rag_embeddings import build_openai_embeddings
        from services.rag_chroma_store import ChromaRagStore
        from services.retrieval.factory import build_retrieval_backend, normalize_rag_backend
        from services.rag_query_service import _dedupe_retrieval_raw_results
        from utils.config import load_config
    except Exception as exc:
        return [f"vector_import:{type(exc).__name__}:{exc}"], []

    try:
        cfg = load_config()
        embeddings = build_openai_embeddings(cfg)
        rb = normalize_rag_backend(cfg.rag_backend)
        if rb == "chroma":
            chroma_dir = _resolve(cfg.chroma_persist_dir)
            store = ChromaRagStore(
                cfg,
                embeddings,
                persist_directory=chroma_dir,
            )
            active = build_retrieval_backend(cfg, chroma_store=store, embeddings=embeddings)
        else:
            active = build_retrieval_backend(cfg, chroma_store=None, embeddings=embeddings)
        be = str(getattr(active, "backend_name", "") or "unknown").strip().lower()
        results = active.search(query, top_k=top_k)
        conv = [
            (
                Document(
                    page_content=r.chunk.page_content,
                    metadata=dict(r.chunk.metadata),
                ),
                r.score,
            )
            for r in results
        ]
        texts = [_norm_text(d.page_content) for d, _ in conv]
        raw_dup_body = len(texts) >= 2 and len(texts) != len(set(texts))
        if raw_dup_body:
            sample = next(t for t in texts if texts.count(t) > 1)[:120].replace("\n", " ")
            warns.append(
                f"vector_warn_raw_duplicate_norm_text: raw_hits={len(conv)} "
                f"unique_norm={len(set(texts))} sample={sample!r}"
            )
            print(
                f"[rag_dup_audit] WARN raw vector hits contain duplicate normalized text "
                f"(unique={len(set(texts))}/{len(conv)}) sample={sample!r}",
                flush=True,
            )
        deduped, raw_n, removed = _dedupe_retrieval_raw_results(list(conv), backend_label=be)
        print(
            f"[rag_dup_audit] vector_search backend={be} raw_hits={raw_n} "
            f"after_dedupe={len(deduped)} removed={removed}",
            flush=True,
        )
        texts_d = [_norm_text(d.page_content) for d, _ in deduped]
        fps_d = [_fp16(d.page_content) for d, _ in deduped]
        if raw_dup_body and removed == 0:
            errs.append(
                f"vector_search_dedupe_noop: raw had duplicate normalized text but removed=0 "
                f"backend={be}"
            )
        if len(texts_d) >= 2 and len(texts_d) != len(set(texts_d)):
            errs.append(
                f"vector_search_post_dedupe_dup_norm_text: after_dedupe={len(deduped)} "
                f"unique={len(set(texts_d))}"
            )
        if len(fps_d) >= 2 and len(fps_d) != len(set(fps_d)):
            errs.append(
                f"vector_search_post_dedupe_dup_text_fp: after_dedupe={len(deduped)} "
                f"fps={fps_d}"
            )
        if source_substr:
            for i, (d, sc) in enumerate(conv, 1):
                src = str((d.metadata or {}).get("source") or "")
                if source_substr.lower() in src.lower():
                    prev = _norm_text(d.page_content)[:120]
                    print(
                        f"  raw[{i}] score={sc!r} source={src!r} text_fp={_fp16(d.page_content)!r} "
                        f"preview={prev!r}",
                        flush=True,
                    )
            for j, (d2, sc2) in enumerate(deduped, 1):
                src2 = str((d2.metadata or {}).get("source") or "")
                if source_substr.lower() in src2.lower():
                    p2 = _norm_text(d2.page_content)[:120]
                    print(
                        f"  dedup[{j}] score={sc2!r} source={src2!r} text_fp={_fp16(d2.page_content)!r} "
                        f"preview={p2!r}",
                        flush=True,
                    )
        else:
            for i, (d, sc) in enumerate(conv, 1):
                prev = _norm_text(d.page_content)[:120]
                src = str((d.metadata or {}).get("source") or "")
                print(
                    f"  [{i}] score={sc!r} source={src!r} text_fp={_fp16(d.page_content)!r} "
                    f"preview={prev!r}",
                    flush=True,
                )
    except Exception as exc:
        errs.append(f"vector_search:{type(exc).__name__}:{exc}")
    return errs, warns


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG duplicate chunks audit.")
    parser.add_argument(
        "--query",
        type=str,
        default="Что можете сказать про LLM?",
        help="Query for live vector search (requires OPENAI_API_KEY).",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-K for vector search.")
    parser.add_argument(
        "--source-substr",
        type=str,
        default=None,
        help="If set, print detailed rows only for chunks whose source contains this substring.",
    )
    args = parser.parse_args()

    all_errs: list[str] = []
    all_warns: list[str] = []

    pe, pw = _pg_checks()
    all_errs.extend(pe)
    all_warns.extend(pw)

    le, lw = _last_rag_log_dupes()
    all_errs.extend(le)
    all_warns.extend(lw)

    ve, vw = _vector_search_dupes(
        query=args.query.strip(),
        top_k=max(1, int(args.top_k)),
        source_substr=(args.source_substr or "").strip() or None,
    )
    all_errs.extend(ve)
    all_warns.extend(vw)

    if all_warns:
        print("[rag_dup_audit] WARNINGS (non-fatal):", flush=True)
        for w in all_warns:
            print(f"  - {w}", flush=True)

    if all_errs:
        print("FAIL: duplicate / integrity signals:", flush=True)
        for e in all_errs:
            print(f"  - {e}", flush=True)
        return 1
    print("OK: no hard-fail duplicate signals in executed checks.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
