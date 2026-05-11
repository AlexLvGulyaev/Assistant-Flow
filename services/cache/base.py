"""
Локальный cache layer (P6.6): optimization only, не source of truth.

Не Redis, не distributed workers. Namespaces изолируют query / retrieval / answer / evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class CacheNamespaces:
    """Строковые namespace для SQLite cache (контракт, не enum для простоты SQL)."""

    QUERY = "query"
    RETRIEVAL = "retrieval"
    ANSWER = "answer"
    EVALUATION = "evaluation"


@dataclass(frozen=True)
class CacheKey:
    """Логический ключ: namespace + стабильный hash содержимого (не raw query в логах)."""

    namespace: str
    key_hash: str


@dataclass(frozen=True)
class CacheEntry:
    """Значение из кэша (value_json уже распарсен)."""

    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    expires_at: datetime | None = None
    hit_count: int = 0
    last_hit_at: datetime | None = None


@dataclass(frozen=True)
class CacheStats:
    """Агрегированная статистика (без dump значений)."""

    entries_total: int
    hits_total: int
    by_namespace: dict[str, int]


@dataclass(frozen=True)
class CachePolicy:
    """Политика TTL по умолчанию для set (None = без срока)."""

    default_ttl_seconds: int | None = None


@runtime_checkable
class CacheStore(Protocol):
    def get(self, namespace: str, key_hash: str) -> CacheEntry | None: ...
    def set(
        self,
        namespace: str,
        key_hash: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> None: ...
    def delete(self, namespace: str, key_hash: str) -> None: ...
    def clear_namespace(self, namespace: str) -> int: ...
    def stats(self) -> CacheStats: ...
