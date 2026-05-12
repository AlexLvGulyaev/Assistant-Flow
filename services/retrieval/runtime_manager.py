"""
P6.9 / P6.10: runtime retrieval backend resolution, lazy construction, FAISS stale detection,
DB-backed active backend (PostgreSQL ``platform_settings``) with env bootstrap fallback.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from services.retrieval.base import RetrievalBackend, RetrievalHealth
from services.retrieval.factory import (
    build_retrieval_backend,
    effective_rag_backend_from_sources,
    normalize_rag_backend,
)
from services.retrieval.faiss_backend import faiss_disk_fingerprint, resolve_faiss_index_dir
from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
from utils.config import AppConfig

_STALE_LOG_MIN_INTERVAL_S = 30.0
_DB_DEGRADED_LOG_MIN_INTERVAL_S = 30.0
_EFFECTIVE_CACHE_TTL_S = 2.5


class RetrievalBackendManager:
    """
    Управляет жизненным циклом активного ``RetrievalBackend``:
    lazy build, reload FAISS при изменении файлов на диске, без полного reload на каждый HTTP-запрос.
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        project_root: Path,
        chroma_persist_directory: Path,
        tuning_resolver: RetrievalTuningResolver | None = None,
    ) -> None:
        self._config = config
        self._tuning = tuning_resolver
        self._project_root = Path(project_root).resolve()
        self._chroma_dir = Path(chroma_persist_directory).resolve()
        self._embeddings: Any = None
        self._emb_sig: tuple[Any, ...] | None = None
        self._backend: RetrievalBackend | None = None
        self._built_key: str | None = None
        self._faiss_fp: tuple[int, int, int] | None = None
        self._last_stale_log_mono: float = 0.0
        self._eff_cached_backend: str | None = None
        self._eff_cache_mono: float = 0.0
        self._last_db_degraded_log_mono: float = 0.0

    def _embeddings_fn(self) -> Any:
        eff = self._tuning.effective_config() if self._tuning is not None else self._config
        sig = (
            float(eff.rag_embedding_request_timeout),
            str(eff.openai_embedding_model or ""),
            bool((eff.openai_api_key or "").strip()),
        )
        if self._embeddings is None or self._emb_sig != sig:
            from providers.rag_embeddings import build_openai_embeddings

            self._embeddings = build_openai_embeddings(eff)
            self._emb_sig = sig
        return self._embeddings

    def _maybe_log_db_degraded(self, detail: str) -> None:
        now = time.monotonic()
        if now - self._last_db_degraded_log_mono >= _DB_DEGRADED_LOG_MIN_INTERVAL_S:
            print(
                "[assistant-flow] retrieval_manager: db_unavailable "
                f"using_env_fallback detail={detail!r}",
                flush=True,
            )
            self._last_db_degraded_log_mono = now

    def effective_backend_name(self) -> str:
        """Активный backend: PostgreSQL ``active_rag_backend`` при валидной строке, иначе env."""
        env_default = normalize_rag_backend(self._config.rag_backend)
        now = time.monotonic()
        if (
            self._eff_cached_backend is not None
            and (now - self._eff_cache_mono) < _EFFECTIVE_CACHE_TTL_S
        ):
            return self._eff_cached_backend
        if not (self._config.database_url or "").strip():
            resolved = env_default
            self._eff_cached_backend = resolved
            self._eff_cache_mono = now
            return resolved
        try:
            from repositories.connection import get_connection
            from repositories.platform_settings_repository import PlatformSettingsRepository

            with get_connection() as conn:
                repo = PlatformSettingsRepository()
                db_v = repo.peek_active_rag_backend(conn)
            resolved = effective_rag_backend_from_sources(
                env_backend=env_default,
                db_backend=db_v,
            )
        except Exception as exc:
            self._maybe_log_db_degraded(f"{type(exc).__name__}: {exc}")
            resolved = env_default
        self._eff_cached_backend = resolved
        self._eff_cache_mono = now
        return resolved

    def _maybe_log_stale(self, msg: str) -> None:
        now = time.monotonic()
        if now - self._last_stale_log_mono >= _STALE_LOG_MIN_INTERVAL_S:
            print(f"[assistant-flow] retrieval_manager: {msg}", flush=True)
            self._last_stale_log_mono = now

    def _faiss_disk_changed(self) -> bool:
        if self.effective_backend_name() != "faiss":
            return False
        if self._faiss_fp is None:
            return False
        idx = resolve_faiss_index_dir(self._config, project_root=self._project_root)
        return faiss_disk_fingerprint(idx) != self._faiss_fp

    def _build_backend(self) -> RetrievalBackend:
        name = self.effective_backend_name()
        base_eff = self._tuning.effective_config() if self._tuning is not None else self._config
        cfg = replace(base_eff, rag_backend=name)
        emb = self._embeddings_fn()
        if name == "chroma":
            from services.rag_chroma_store import ChromaRagStore

            if not cfg.chroma_use_http:
                self._chroma_dir.mkdir(parents=True, exist_ok=True)
            store = ChromaRagStore(
                cfg,
                emb,
                persist_directory=self._chroma_dir,
            )
            self._faiss_fp = None
            return build_retrieval_backend(
                cfg,
                chroma_store=store,
                embeddings=emb,
            )
        backend = build_retrieval_backend(
            cfg,
            chroma_store=None,
            embeddings=emb,
        )
        if name == "faiss":
            idx = resolve_faiss_index_dir(cfg, project_root=self._project_root)
            self._faiss_fp = faiss_disk_fingerprint(idx)
        else:
            self._faiss_fp = None
        return backend

    def _ensure_fresh(self) -> None:
        key = self.effective_backend_name()
        if self._backend is None or self._built_key != key:
            self._backend = self._build_backend()
            self._built_key = key
            print(
                "[assistant-flow] retrieval_manager: "
                f"backend_built effective={key} active_backend={key}",
                flush=True,
            )
            return

        if self._faiss_disk_changed():
            self._maybe_log_stale(
                "faiss_disk_stale_detected reloading in-memory index "
                f"(fp_was={self._faiss_fp!r})"
            )
            self._backend = self._build_backend()
            idx = resolve_faiss_index_dir(self._config, project_root=self._project_root)
            self._faiss_fp = faiss_disk_fingerprint(idx)
            print(
                "[assistant-flow] retrieval_manager: faiss_reload_done "
                f"fp_now={self._faiss_fp!r}",
                flush=True,
            )

    def get_retrieval(self) -> RetrievalBackend:
        self._ensure_fresh()
        if self._backend is None:
            raise RuntimeError("RetrievalBackendManager: internal state without backend")
        return self._backend

    def note_access_before_retrieval(self) -> None:
        """Вызывать перед vector query; дешёвая проверка mtime для FAISS."""
        self._ensure_fresh()

    def refresh(self, *, reason: str) -> None:
        """Сбросить кэш backend (ручной refresh / после ошибок)."""
        print(
            f"[assistant-flow] retrieval_manager: manual_refresh reason={reason!r}",
            flush=True,
        )
        self._backend = None
        self._built_key = None
        self._faiss_fp = None
        self._eff_cached_backend = None
        self._embeddings = None
        self._emb_sig = None

    def snapshot_health_active(self) -> RetrievalHealth:
        return self.get_retrieval().healthcheck()
