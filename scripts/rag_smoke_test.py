"""
Local RAG smoke test: query Chroma and print an answer.

Run from repository root:
  python scripts/rag_smoke_test.py                       # query-only (безопасно против живого индекса)
  python scripts/rag_smoke_test.py --index               # ПЕРЕЗАПИШЕТ индекс: full rebuild (как admin --reindex)
  python scripts/rag_smoke_test.py --index --question "Ваш вопрос"

Requires OPENAI_API_KEY for embeddings and chat (direct OpenAI). Image generation uses ProxyAPI separately (PROXY_API_KEY).

Раньше скрипт по умолчанию ДОБАВЛЯЛ векторы поверх существующего индекса
(duplicate chunks / inflated collection count) — против живого HTTP-Chroma это
засоряло демо-базу. Теперь индексация только под явным --index.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _resolve_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Chroma smoke test (local only).")
    parser.add_argument(
        "--index",
        action="store_true",
        help="Full reindex before query: remote collection (CHROMA_USE_HTTP) or "
             "local CHROMA_PERSIST_DIR wiped, then rebuilt. По умолчанию выключено: "
             "скрипт только спрашивает индекс, ничего не записывая.",
    )
    parser.add_argument(
        "--question",
        type=str,
        default="Кратко: что описано в базе знаний?",
        help="Question to ask after indexing.",
    )
    parser.add_argument(
        "--documents-dir",
        type=str,
        default=None,
        help="Override document directory (default: RAG_DOCUMENTS_DIR from env/config).",
    )
    args = parser.parse_args()

    from providers.openai_chat_provider import OpenAIChatProvider
    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import (
        ChromaRagStore,
        count_chroma_chunks,
        reset_chroma_for_reindex,
    )
    from services.rag_local_indexer import LocalRagIndexer
    from services.rag_query_service import RagQueryService
    from services.retrieval.chroma_backend import ChromaBackend
    from services.retrieval.factory import build_retrieval_backend
    from utils.config import load_config

    config = load_config()
    chroma_dir = _resolve_path(config.chroma_persist_dir)
    docs_dir = _resolve_path(args.documents_dir or config.rag_documents_dir)

    if args.index:
        reset_chroma_for_reindex(config, persist_directory=chroma_dir)
    if not config.chroma_use_http:
        chroma_dir.mkdir(parents=True, exist_ok=True)

    embeddings = build_openai_embeddings(config)
    store = ChromaRagStore(
        config,
        embeddings,
        persist_directory=chroma_dir,
    )

    if args.index:
        indexer = LocalRagIndexer(config, ChromaBackend(store))
        print(f"Indexing from: {docs_dir}")
        n = indexer.index_documents_dir(docs_dir)
        print(f"Chunks indexed: {n}")
        print(f"Collection count: {store.collection_count()}")
        if n == 0:
            print(
                "No documents indexed. Add .txt, .md, or .pdf under the documents directory.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        existing_chunks = count_chroma_chunks(config, persist_path=chroma_dir)
        print(f"Query-only mode: collection holds {existing_chunks} chunk(s), nothing written.")
        if existing_chunks == 0:
            print(
                "Index is empty. Run with --index to rebuild it.",
                file=sys.stderr,
            )
            sys.exit(1)

    chat = OpenAIChatProvider(config)
    retrieval = build_retrieval_backend(config, chroma_store=store, embeddings=embeddings)
    rag = RagQueryService(retrieval, chat, config)

    print(f"\nQuestion: {args.question}\n")
    retrieved = rag.retrieve(args.question)
    print("--- Retrieved sources ---")
    for i, src in enumerate(retrieved, 1):
        score = f"{src.score:.4f}" if src.score is not None else "n/a"
        preview = src.content[:200].replace("\n", " ")
        if len(src.content) > 200:
            preview += "…"
        print(f"  [{i}] source={src.source!r} score={score}\n      {preview}")

    result = rag.answer(args.question)
    print("\n--- Answer ---")
    print(result.answer)
    if result.used_fallback_without_context:
        print("\n(note: fallback path — no chunks retrieved for query)")


if __name__ == "__main__":
    main()
