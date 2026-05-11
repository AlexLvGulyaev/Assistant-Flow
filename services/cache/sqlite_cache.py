"""
SQLite-backed local cache. Отдельно от PostgreSQL SoT.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.cache.base import CacheEntry, CacheStats


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class SqliteCacheStore:
    """Минимальный persistent cache; таблица создаётся при инициализации."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_entries (
                        namespace TEXT NOT NULL,
                        key_hash TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT,
                        hit_count INTEGER NOT NULL DEFAULT 0,
                        last_hit_at TEXT,
                        PRIMARY KEY (namespace, key_hash)
                    )
                    """
                )
                conn.commit()

    def get(self, namespace: str, key_hash: str) -> CacheEntry | None:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    SELECT value_json, metadata_json, created_at, expires_at, hit_count, last_hit_at
                    FROM cache_entries
                    WHERE namespace = ? AND key_hash = ?
                    """,
                    (namespace, key_hash),
                )
                row = cur.fetchone()
        if not row:
            return None
        value_json, meta_json, created_s, expires_s, hits, last_hit_s = row
        expires_at = _parse_iso(expires_s)
        if expires_at is not None and expires_at < _utcnow():
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM cache_entries WHERE namespace = ? AND key_hash = ?",
                        (namespace, key_hash),
                    )
                    conn.commit()
            return None
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE cache_entries
                    SET hit_count = hit_count + 1, last_hit_at = ?
                    WHERE namespace = ? AND key_hash = ?
                    """,
                    (_iso(_utcnow()), namespace, key_hash),
                )
                conn.commit()
        return CacheEntry(
            value=json.loads(value_json),
            metadata=json.loads(meta_json) if meta_json else {},
            created_at=_parse_iso(created_s),
            expires_at=expires_at,
            hit_count=int(hits) + 1,
            last_hit_at=_utcnow(),
        )

    def set(
        self,
        namespace: str,
        key_hash: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        now = _utcnow()
        exp: datetime | None = None
        if ttl_seconds is not None and ttl_seconds > 0:
            from datetime import timedelta

            exp = now + timedelta(seconds=int(ttl_seconds))
        meta = dict(metadata or {})
        payload = json.dumps(value, ensure_ascii=False)
        meta_json = json.dumps(meta, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO cache_entries (
                        namespace, key_hash, value_json, metadata_json,
                        created_at, expires_at, hit_count, last_hit_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
                    ON CONFLICT(namespace, key_hash) DO UPDATE SET
                        value_json = excluded.value_json,
                        metadata_json = excluded.metadata_json,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        hit_count = 0,
                        last_hit_at = NULL
                    """,
                    (
                        namespace,
                        key_hash,
                        payload,
                        meta_json,
                        _iso(now),
                        _iso(exp),
                    ),
                )
                conn.commit()

    def delete(self, namespace: str, key_hash: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM cache_entries WHERE namespace = ? AND key_hash = ?",
                    (namespace, key_hash),
                )
                conn.commit()

    def clear_namespace(self, namespace: str) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM cache_entries WHERE namespace = ?", (namespace,)
                )
                conn.commit()
                return int(cur.rowcount or 0)

    def stats(self) -> CacheStats:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM cache_entries"
                )
                total, hits = cur.fetchone() or (0, 0)
                cur = conn.execute(
                    "SELECT namespace, COUNT(*) FROM cache_entries GROUP BY namespace"
                )
                by_ns = {str(r[0]): int(r[1]) for r in cur.fetchall()}
        return CacheStats(
            entries_total=int(total or 0),
            hits_total=int(hits or 0),
            by_namespace=by_ns,
        )


_STORES: dict[str, SqliteCacheStore] = {}
_STORES_LOCK = threading.Lock()


def get_sqlite_cache_store(db_path: str | Path) -> SqliteCacheStore:
    """Один экземпляр на нормализованный путь (избегаем дублирования соединений/схем)."""
    key = str(Path(db_path).resolve())
    with _STORES_LOCK:
        if key not in _STORES:
            _STORES[key] = SqliteCacheStore(key)
        return _STORES[key]
