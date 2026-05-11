"""Local SQLite cache foundation (P6.6): namespaces, retrieval wrapper, invalidation hooks."""

from services.cache.base import (
    CacheEntry,
    CacheKey,
    CacheNamespaces,
    CachePolicy,
    CacheStats,
    CacheStore,
)
from services.cache.answer_cache_service import AnswerCacheService
from services.cache.caching_retrieval_backend import CachingRetrievalBackend
from services.cache.invalidate import invalidate_retrieval_cache
from services.cache.retrieval_cache_key import (
    build_retrieval_fingerprint,
    fingerprint_to_key_hash,
    normalize_query_text,
)
from services.cache.sqlite_cache import SqliteCacheStore, get_sqlite_cache_store

__all__ = [
    "AnswerCacheService",
    "CacheEntry",
    "CacheKey",
    "CacheNamespaces",
    "CachePolicy",
    "CacheStats",
    "CacheStore",
    "CachingRetrievalBackend",
    "SqliteCacheStore",
    "build_retrieval_fingerprint",
    "fingerprint_to_key_hash",
    "get_sqlite_cache_store",
    "invalidate_retrieval_cache",
    "normalize_query_text",
]
