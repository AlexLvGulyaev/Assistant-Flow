"""
P6.9: runtime retrieval backend resolution, lazy construction, FAISS stale detection.

Effective backend сейчас = ``normalize_rag_backend(config.rag_backend)`` (env bootstrap).
В следующей фазе сюда добавится чтение PostgreSQL platform_settings без смены публичного API.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from services.retrieval.base import RetrievalBackend, RetrievalHealth
from services.retrieval.factory import build_retrieval_backend, normalize_rag_backend
from services.retrieval.faiss_backend import faiss_disk_fingerprint, resolve_faiss_index_dir
from utils.config import AppConfig

_STALE_LOG_MIN_INTERVAL_S = 30.0


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
    ) -> None:
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._chroma_dir = Path(chroma_persist_directory).resolve()
        self._embeddings: Any = None
        self._backend: RetrievalBackend | None = None
        self._built_key: str | None = None
        self._faiss_fp: tuple[int, int, int] | None = None
        self._last_stale_log_mono: float = 0.0

    def _embeddings_fn(self) -> Any:
        if self._embeddings is None:
            from providers.rag_embeddings import build_openai_embeddings

            self._embeddings = build_openai_embeddings(self._config)
        return self._embeddings

    def effective_backend_name(self) -> str:
        """Идентификатор backend (chroma / faiss / weaviate). P6.10+: читать из DB."""
        return normalize_rag_backend(self._config.rag_backend)

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
        emb = self._embeddings_fn()
        if name == "chroma":
            from services.rag_chroma_store import ChromaRagStore

            if not self._config.chroma_use_http:
                self._chroma_dir.mkdir(parents=True, exist_ok=True)
            store = ChromaRagStore(
                self._config,
                emb,
                persist_directory=self._chroma_dir,
            )
            self._faiss_fp = None
            return build_retrieval_backend(
                self._config,
                chroma_store=store,
                embeddings=emb,
            )
        backend = build_retrieval_backend(
            self._config,
            chroma_store=None,
            embeddings=emb,
        )
        if name == "faiss":
            idx = resolve_faiss_index_dir(self._config, project_root=self._project_root)
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

    def snapshot_health_active(self) -> RetrievalHealth:
        return self.get_retrieval().healthcheck()
