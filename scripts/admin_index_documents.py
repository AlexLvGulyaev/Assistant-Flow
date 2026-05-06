"""
Admin CLI: index knowledge-base files from RAG_DOCUMENTS_DIR into ChromaDB
and optionally record metadata in PostgreSQL (documents, document_versions, indexing_jobs).

Run from repository root:
  python scripts/admin_index_documents.py
  python scripts/admin_index_documents.py --reindex
  python scripts/admin_index_documents.py --no-postgres

Does not start Telegram; users cannot upload documents via the bot.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _resolve_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Admin: index local documents into Chroma (and PostgreSQL if configured)."
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Reset RAG Chroma collection (HTTP: delete+recreate; local: wipe persist dir + empty collection) then rebuild.",
    )
    parser.add_argument(
        "--no-postgres",
        action="store_true",
        help="Chroma only; skip documents / document_versions / indexing_jobs even if DATABASE_URL is set.",
    )
    parser.add_argument(
        "--documents-dir",
        type=str,
        default=None,
        help="Override RAG_DOCUMENTS_DIR (default from env / config).",
    )
    args = parser.parse_args()

    from services.admin_knowledge_indexer import AdminKnowledgeIndexer
    from utils.config import load_config

    config = load_config()
    docs_dir = _resolve_path(args.documents_dir or config.rag_documents_dir)
    chroma_dir = _resolve_path(config.chroma_persist_dir)

    use_pg = not args.no_postgres
    db_url = (os.getenv("DATABASE_URL") or "").strip()

    print("=== Admin knowledge base indexing ===")
    print(f"Documents directory: {docs_dir}")
    print(f"Chroma directory:    {chroma_dir}")
    print(f"Reindex (wipe Chroma first): {args.reindex}")
    if use_pg and db_url:
        print("PostgreSQL:          enabled (metadata + jobs)")
    elif use_pg and not db_url:
        print("PostgreSQL:          skipped (DATABASE_URL not set; Chroma only)")
    else:
        print("PostgreSQL:          disabled (--no-postgres)")

    if not args.reindex:
        print(
            "\nNote: without --reindex, new chunks are ADDED to the existing Chroma index "
            "(possible duplicates if the same files were indexed before).\n"
        )

    if not docs_dir.is_dir():
        print(f"ERROR: directory not found: {docs_dir}", file=sys.stderr)
        return 1

    indexer = AdminKnowledgeIndexer(
        config,
        documents_dir=docs_dir,
        chroma_dir=chroma_dir,
        use_postgres=use_pg,
    )

    report = None
    run_failed = False

    try:
        print("before indexer.run", flush=True)
        report = indexer.run(reindex=args.reindex)
        print("after indexer.run", flush=True)
    except BaseException:
        traceback.print_exc()
        run_failed = True
    finally:
        print("\n--- Summary ---", flush=True)
        if report is not None:
            print(f"Files found:              {report.files_found}", flush=True)
            print(f"Files indexed (no error): {report.files_indexed_ok}", flush=True)
            print(f"Chunks created (this run): {report.chunks_created}", flush=True)
            print(f"Chunks in Chroma (total):  {report.chroma_chunk_count}", flush=True)
            print(f"PostgreSQL metadata:       {report.used_postgres}", flush=True)
        else:
            print(
                "Indexing did not complete (no report; see traceback above if any).",
                flush=True,
            )

    if run_failed:
        return 1

    assert report is not None

    if report.errors:
        print(f"\n--- Errors ({len(report.errors)}) ---", flush=True)
        for o in report.errors:
            print(f"  • {o.path}", flush=True)
            print(f"    {o.error}", flush=True)
        return 3

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
