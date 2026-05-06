"""
RAG regression checks (no pytest). Run from repository root:

  python scripts/test_rag_regression.py

Requires OPENAI_API_KEY, Chroma (HTTP or local per .env), and documents under RAG_DOCUMENTS_DIR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_EXPECTED_EMBEDDING_DIM = 1536
_RELEVANT_Q = "Кратко: что описано в базе знаний?"
_IRRELEVANT_Q = "Есть ли в базе информация про вакансии?"


def _resolve_path(config_docs: str) -> Path:
    p = Path(config_docs)
    return p if p.is_absolute() else ROOT / p


def _check(name: str, ok: bool, detail: str = "") -> bool:
    suffix = f" ({detail})" if detail else ""
    print(f"{'PASS' if ok else 'FAIL'}: {name}{suffix}", flush=True)
    return ok


def main() -> int:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print("FAIL: OPENAI_API_KEY is not set", flush=True)
        return 1

    from providers.openai_chat_provider import OpenAIChatProvider
    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore, reset_chroma_for_reindex
    from services.rag_document_loader import load_and_split_directory
    from services.rag_local_indexer import LocalRagIndexer
    from services.rag_query_service import RagQueryService
    from utils.config import load_config

    config = load_config()
    chroma_dir = _resolve_path(config.chroma_persist_dir)
    docs_dir = _resolve_path(config.rag_documents_dir)

    failed: list[str] = []

    embeddings = build_openai_embeddings(config)
    vec = embeddings.embed_query("rag regression dimension probe")
    if not _check(
        "embedding_vector_len",
        len(vec) == _EXPECTED_EMBEDDING_DIM,
        f"len={len(vec)} expected={_EXPECTED_EMBEDDING_DIM}",
    ):
        failed.append("embedding_vector_len")

    if not docs_dir.is_dir():
        print(f"FAIL: documents directory missing: {docs_dir}", flush=True)
        return 1

    expected_chunks = len(load_and_split_directory(docs_dir, config))
    if not _check(
        "documents_produce_chunks",
        expected_chunks > 0,
        f"expected_chunks={expected_chunks}",
    ):
        failed.append("documents_produce_chunks")
        return 1

    def _full_reindex() -> tuple[int, int, ChromaRagStore]:
        reset_chroma_for_reindex(config, persist_directory=chroma_dir)
        if not config.chroma_use_http:
            chroma_dir.mkdir(parents=True, exist_ok=True)
        store = ChromaRagStore(
            config,
            embeddings,
            persist_directory=chroma_dir,
        )
        indexer = LocalRagIndexer(config, store)
        n = indexer.index_documents_dir(docs_dir)
        c = store.collection_count()
        return n, c, store

    n1, c1, store1 = _full_reindex()
    if not _check(
        "reindex_chunk_count_matches_expected",
        n1 == expected_chunks,
        f"indexed={n1} expected={expected_chunks}",
    ):
        failed.append("reindex_chunk_count_matches_expected")
    if not _check(
        "reindex_collection_equals_chunks",
        c1 == n1,
        f"collection_count={c1} chunks_indexed={n1}",
    ):
        failed.append("reindex_collection_equals_chunks")

    n2, c2, store2 = _full_reindex()
    if not _check(
        "second_reindex_collection_stable",
        c2 == c1 and c2 == n2,
        f"first_count={c1} second_count={c2} second_chunks={n2}",
    ):
        failed.append("second_reindex_collection_stable")

    chat = OpenAIChatProvider(config)
    rag = RagQueryService(store2, chat, config)

    rel = rag.answer(_RELEVANT_Q)
    srcs = rel.sources
    unique_ok = len(srcs) == len({s.source for s in srcs})
    if not _check(
        "relevant_question_has_sources",
        len(srcs) >= 1,
        f"sources={len(srcs)}",
    ):
        failed.append("relevant_question_has_sources")
    if not _check("relevant_sources_unique", unique_ok, f"count={len(srcs)}"):
        failed.append("relevant_sources_unique")

    irr = rag.answer(_IRRELEVANT_Q)
    low_text = (
        "недостаточно релевантной" in irr.answer
        or "не прошли порог релевантности" in irr.answer
    )
    if not _check(
        "irrelevant_question_relevance_fallback",
        low_text,
        "expected low-relevance fallback wording",
    ):
        failed.append("irrelevant_question_relevance_fallback")

    if failed:
        print(f"\nRegression failed: {', '.join(failed)}", flush=True)
        return 1
    print("\nAll RAG regression checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
