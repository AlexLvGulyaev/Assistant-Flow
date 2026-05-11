"""
Foundation для answer cache (P6.6): контракт без обязательной интеграции в RagQueryService.

При ``ENABLE_ANSWER_CACHE=false`` (default) runtime RAG не использует этот слой.
Интеграция в LLM path — отдельный этап (риск смены семантики ответов / PII).
"""

from __future__ import annotations

from typing import Any

from services.cache.base import CacheNamespaces, CachePolicy
from services.cache.sqlite_cache import get_sqlite_cache_store
from utils.config import AppConfig


class AnswerCacheService:
    """Get/set ответов по стабильному fingerprint (namespace ``answer``)."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._store = get_sqlite_cache_store(config.cache_db_path)
        self._policy = CachePolicy(default_ttl_seconds=config.answer_cache_ttl_seconds)

    @property
    def enabled(self) -> bool:
        return bool(self._config.enable_answer_cache)

    def get(self, key_hash: str) -> Any | None:
        if not self.enabled:
            return None
        ent = self._store.get(CacheNamespaces.ANSWER, key_hash)
        return ent.value if ent else None

    def set(self, key_hash: str, value: Any, *, metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        ttl = self._policy.default_ttl_seconds
        self._store.set(
            CacheNamespaces.ANSWER,
            key_hash,
            value,
            metadata=metadata,
            ttl_seconds=ttl if ttl and ttl > 0 else None,
        )
