#!/usr/bin/env python3
"""
Smoke: SQLite cache foundation (P6.6). Без DB/Chroma — можно на host.

Для retrieval integration см. scripts/test_retrieval_cache_smoke.py (portfolio container).
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import os

    os.chdir(ROOT)
    os.environ.pop("ENABLE_RETRIEVAL_CACHE", None)
    os.environ.pop("ENABLE_ANSWER_CACHE", None)
    from utils.config import load_config

    cfg = load_config()
    assert cfg.enable_retrieval_cache is False, "default retrieval cache must be off"
    assert cfg.enable_answer_cache is False, "default answer cache must be off"

    from services.cache.base import CacheNamespaces
    from services.cache.retrieval_cache_key import (
        build_retrieval_fingerprint,
        fingerprint_to_key_hash,
    )
    from services.cache.sqlite_cache import SqliteCacheStore

    deep = Path(f"/tmp/af_cache_smoke_{uuid.uuid4().hex}/nested")
    db_path = deep / "cache.sqlite3"
    store = SqliteCacheStore(db_path)

    h1 = "abc"
    store.set(CacheNamespaces.QUERY, h1, {"x": 1}, metadata={"t": 1}, ttl_seconds=None)
    ent = store.get(CacheNamespaces.QUERY, h1)
    assert ent is not None and ent.value == {"x": 1}

    assert store.get(CacheNamespaces.RETRIEVAL, h1) is None

    h_ttl = "ttl_row"
    store.set(CacheNamespaces.EVALUATION, h_ttl, [1], ttl_seconds=1)
    time.sleep(2.1)
    assert store.get(CacheNamespaces.EVALUATION, h_ttl) is None

    store.set(CacheNamespaces.QUERY, h1, {"x": 2}, ttl_seconds=None)
    store.get(CacheNamespaces.QUERY, h1)
    st = store.stats()
    assert st.entries_total >= 1

    n = store.clear_namespace(CacheNamespaces.QUERY)
    assert n >= 1
    assert store.get(CacheNamespaces.QUERY, h1) is None

    mock_cfg = SimpleNamespace(
        rag_backend="chroma",
        openai_embedding_model="emb-a",
        enable_hybrid_retrieval=False,
    )
    fp1 = build_retrieval_fingerprint(mock_cfg, query="  hello  world  ", top_k=3)
    fp2 = build_retrieval_fingerprint(mock_cfg, query="hello world", top_k=5)
    assert fingerprint_to_key_hash(fp1) != fingerprint_to_key_hash(fp2)

    mock_cfg_b = SimpleNamespace(
        rag_backend="faiss",
        openai_embedding_model="emb-a",
        enable_hybrid_retrieval=False,
    )
    fp3 = build_retrieval_fingerprint(mock_cfg_b, query="hello world", top_k=3)
    assert fingerprint_to_key_hash(fp1) != fingerprint_to_key_hash(fp3)

    print("OK: test_cache_foundation_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
