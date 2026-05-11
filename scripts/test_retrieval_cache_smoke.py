#!/usr/bin/env python3
"""
Smoke: retrieval cache через CachingRetrievalBackend + Chroma.

Только внутри portfolio-test-assistant-flow-1 после rebuild (см. PROJECT_STATE §32).
Переопределяет env процесса для включения кэша и изолированного SQLite файла.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()
    os.environ["ENABLE_RETRIEVAL_CACHE"] = "true"
    os.environ["CACHE_DB_PATH"] = f"/tmp/af_retrieval_cache_smoke_{uuid.uuid4().hex}.sqlite3"

    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore
    from services.retrieval.factory import build_retrieval_backend
    from utils.config import load_config

    cfg = load_config()
    assert cfg.enable_retrieval_cache is True

    chroma_path = Path(cfg.chroma_persist_dir)
    if not chroma_path.is_absolute():
        chroma_path = ROOT / chroma_path

    embeddings = build_openai_embeddings(cfg)
    store = ChromaRagStore(cfg, embeddings, persist_directory=chroma_path)
    if store.collection_count() <= 0:
        print("SKIP: Chroma collection empty — retrieval cache smoke пропущен")
        return 0

    retrieval = build_retrieval_backend(cfg, chroma_store=store, embeddings=embeddings)
    q = "Кратко: что описано в базе знаний?"
    k = min(3, int(cfg.rag_top_k))

    r1 = retrieval.search(q, top_k=k)
    r2 = retrieval.search(q, top_k=k)
    assert len(r1) == len(r2)
    if r1:
        assert r1[0].chunk.page_content == r2[0].chunk.page_content

    print("OK: test_retrieval_cache_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
