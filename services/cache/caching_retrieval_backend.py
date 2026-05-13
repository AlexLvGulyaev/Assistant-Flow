"""
Обёртка над RetrievalBackend: lookup/set при ``ENABLE_RETRIEVAL_CACHE``.

Пустой результат поиска **не** кэшируется. Ошибки inner.search **не** кэшируются.
Hybrid memory context сюда не попадает (только vector retrieval).
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

from services.cache.base import CacheNamespaces
from services.cache.retrieval_cache_key import (
    build_retrieval_fingerprint,
    fingerprint_to_key_hash,
)
from services.cache.retrieval_serializers import (
    deserialize_search_results,
    serialize_search_results,
)
from services.cache.sqlite_cache import get_sqlite_cache_store
from services.cache.invalidate import invalidate_retrieval_cache
from services.retrieval.base import RetrievalBackend, RetrievalHealth, RetrievalSearchResult
from services.retrieval_security.context import RetrievalSecurityContext

if TYPE_CHECKING:
    from utils.config import AppConfig


# Диагностика последнего search в потоке (RAG вызывает search из worker ThreadPoolExecutor).
_tls = threading.local()


def clear_retrieval_cache_thread_diag() -> None:
    """Сбросить маркеры retrieval cache в текущем потоке (перед vector search)."""
    _tls.rag_cache_hit = None
    _tls.rag_cache_key_prefix = None
    _tls.rag_cache_fp_backend = None


def _record_retrieval_cache_thread_diag(
    *,
    hit: bool | None,
    key_hash: str,
    fingerprint_backend_line: str,
) -> None:
    _tls.rag_cache_hit = hit
    _tls.rag_cache_key_prefix = (key_hash or "")[:16] or None
    _tls.rag_cache_fp_backend = (fingerprint_backend_line or "").strip() or None


def take_retrieval_cache_thread_diag() -> dict[str, Any]:
    """Забрать и очистить маркеры retrieval cache в текущем потоке."""
    d: dict[str, Any] = {
        "retrieval_cache_hit": getattr(_tls, "rag_cache_hit", None),
        "retrieval_cache_key_hash_prefix": getattr(_tls, "rag_cache_key_prefix", None),
        "retrieval_cache_fingerprint_backend": getattr(_tls, "rag_cache_fp_backend", None),
    }
    clear_retrieval_cache_thread_diag()
    return d


class CachingRetrievalBackend:
    """Делегирует inner backend; при включённом флаге — SQLite retrieval namespace."""

    def __init__(
        self,
        inner: RetrievalBackend,
        *,
        config: "AppConfig",
    ) -> None:
        self._inner = inner
        self._config = config
        self._store = get_sqlite_cache_store(config.cache_db_path)

    @property
    def backend_name(self) -> str:
        return self._inner.backend_name

    def collection_count(self) -> int:
        return int(self._inner.collection_count())

    def reset_for_full_reindex(self) -> None:
        self._inner.reset_for_full_reindex()
        if self._config.enable_retrieval_cache:
            invalidate_retrieval_cache("retrieval_backend_reset_for_full_reindex")

    def add_documents(self, documents: list[Any]) -> list[str]:
        ids = list(self._inner.add_documents(documents))
        if self._config.enable_retrieval_cache and ids:
            invalidate_retrieval_cache("retrieval_backend_add_documents")
        return ids

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        self._inner.delete_vectors_for_document_before_reindex(
            document_id=document_id,
            source_filename=source_filename,
        )
        if self._config.enable_retrieval_cache:
            invalidate_retrieval_cache("retrieval_backend_delete_vectors")

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[RetrievalSearchResult]:
        if not (query or "").strip():
            return []
        if not self._config.enable_retrieval_cache:
            return self._inner.search(
                query, top_k=top_k, security_context=security_context
            )

        ctx = security_context or RetrievalSecurityContext.permissive_default()
        sec_extra = ctx.to_cache_fingerprint_extra()
        fp = build_retrieval_fingerprint(
            self._config,
            query=query,
            top_k=top_k,
            security_fingerprint_extra=sec_extra,
        )
        fp_lines = fp.split("\n")
        fp_backend_line = fp_lines[1].strip() if len(fp_lines) > 1 else ""
        kh = fingerprint_to_key_hash(fp)
        t0 = time.monotonic()
        ent = self._store.get(CacheNamespaces.RETRIEVAL, kh)
        if ent is not None:
            results = deserialize_search_results(ent.value)
            _record_retrieval_cache_thread_diag(
                hit=True,
                key_hash=kh,
                fingerprint_backend_line=fp_backend_line,
            )
            self._log(
                outcome="hit",
                key_hash=kh,
                latency_ms=int((time.monotonic() - t0) * 1000),
                reason="",
            )
            return results

        try:
            results = self._inner.search(
                query, top_k=top_k, security_context=security_context
            )
        except Exception:
            _record_retrieval_cache_thread_diag(
                hit=False,
                key_hash=kh,
                fingerprint_backend_line=fp_backend_line,
            )
            self._log(
                outcome="miss",
                key_hash=kh,
                latency_ms=int((time.monotonic() - t0) * 1000),
                reason="inner_error_not_cached",
            )
            raise

        lat = int((time.monotonic() - t0) * 1000)
        if not results:
            _record_retrieval_cache_thread_diag(
                hit=False,
                key_hash=kh,
                fingerprint_backend_line=fp_backend_line,
            )
            self._log(
                outcome="miss",
                key_hash=kh,
                latency_ms=lat,
                reason="empty_not_cached",
            )
            return []

        ttl = self._config.retrieval_cache_ttl_seconds
        self._store.set(
            CacheNamespaces.RETRIEVAL,
            kh,
            serialize_search_results(results),
            metadata={
                "backend": self.backend_name,
                "top_k": int(top_k),
            },
            ttl_seconds=ttl if ttl and ttl > 0 else None,
        )
        _record_retrieval_cache_thread_diag(
            hit=False,
            key_hash=kh,
            fingerprint_backend_line=fp_backend_line,
        )
        self._log(outcome="miss_set", key_hash=kh, latency_ms=lat, reason="")
        return results

    def healthcheck(self) -> RetrievalHealth:
        return self._inner.healthcheck()

    def _log(self, *, outcome: str, key_hash: str, latency_ms: int, reason: str) -> None:
        prefix = key_hash[:16] if key_hash else ""
        rs = f" reason_skip={reason}" if reason else ""
        print(
            "[assistant-flow] cache: "
            f"cache_enabled=true namespace={CacheNamespaces.RETRIEVAL} "
            f"outcome={outcome} key_hash_prefix={prefix} latency_ms={latency_ms}"
            f"{rs}",
            flush=True,
        )
