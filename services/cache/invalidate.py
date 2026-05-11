"""
Хуки инвалидации кэша (correctness-critical). Не полный production workflow.
"""

from __future__ import annotations

from services.cache.base import CacheNamespaces
from services.cache.sqlite_cache import get_sqlite_cache_store
from utils.config import load_config


def invalidate_retrieval_cache(reason: str) -> int:
    """
    Очистить namespace ``retrieval`` (после reindex, смены embedding model, backend, revision).

    Returns:
        Число удалённых строк (best-effort).
    """
    cfg = load_config()
    store = get_sqlite_cache_store(cfg.cache_db_path)
    n = store.clear_namespace(CacheNamespaces.RETRIEVAL)
    safe = (reason or "").replace("\n", " ")[:200]
    print(
        "[assistant-flow] cache: invalidate_retrieval "
        f"namespace={CacheNamespaces.RETRIEVAL} cleared={n} reason={safe!r}",
        flush=True,
    )
    return n
