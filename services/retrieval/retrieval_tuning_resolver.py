"""TTL-cached effective ``AppConfig`` slice for retrieval tuning (PostgreSQL overrides)."""

from __future__ import annotations

import time

from repositories.connection import get_connection
from services.retrieval.retrieval_tuning import (
    apply_db_overrides_to_config,
    load_retrieval_tuning_db,
)
from utils.config import AppConfig

_DEFAULT_TTL_S = 2.5


class RetrievalTuningResolver:
    """
    Resolves env + ``platform_settings.retrieval_tuning`` into an effective ``AppConfig``.

    Does not mutate the frozen base config; returns ``dataclasses.replace`` views.
    """

    def __init__(self, base: AppConfig, *, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._base = base
        self._ttl_s = ttl_s
        self._cached: AppConfig | None = None
        self._mono: float = 0.0

    def invalidate(self) -> None:
        self._cached = None

    def _load_db_uncached(self) -> dict:
        if not (self._base.database_url or "").strip():
            return {}
        try:
            with get_connection() as conn:
                return load_retrieval_tuning_db(conn)
        except Exception:
            return {}

    def effective_config(self) -> AppConfig:
        now = time.monotonic()
        if self._cached is not None and (now - self._mono) < self._ttl_s:
            return self._cached
        db = self._load_db_uncached()
        self._cached = apply_db_overrides_to_config(self._base, db)
        self._mono = now
        return self._cached
