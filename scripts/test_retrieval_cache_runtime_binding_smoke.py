#!/usr/bin/env python3
"""
Smoke: DB-backed enable_retrieval_cache binds to runtime CachingRetrievalBackend.

- Resolver + wrapper: live ON/OFF without rebuild (mock inner backend).
- Optional DATABASE_URL: PUT tuning + manager wrapper class check.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _mini_config(*, database_url: str = "") -> "AppConfig":
    from utils.config import AppConfig

    return AppConfig(
        telegram_bot_token="",
        gigachat_auth_key="",
        gigachat_scope="GIGACHAT_API_PERS",
        gigachat_model="GigaChat",
        gigachat_max_tokens=512,
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_image_model="gpt-image-1",
        proxy_api_key="",
        proxy_openai_base_url=None,
        proxy_image_model="gpt-image-1",
        database_url=database_url or None,
        rag_backend="chroma",
        enable_retrieval_cache=False,
        cache_db_path=str(
            Path(tempfile.mkdtemp(prefix="af_cache_bind_")) / "cache.sqlite3"
        ),
        faiss_index_dir=str(Path(tempfile.mkdtemp(prefix="af_cache_bind_faiss_"))),
    )


def _mock_inner() -> MagicMock:
    inner = MagicMock()
    inner.backend_name = "chroma"
    inner.collection_count.return_value = 1
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult

    chunk = RetrievalChunk(page_content="smoke", metadata={"source": "t.txt"})
    inner.search.return_value = [RetrievalSearchResult(chunk=chunk, score=0.1)]
    return inner


def _wrapper_live_toggle() -> list[str]:
    failed: list[str] = []
    from dataclasses import replace

    from services.cache.caching_retrieval_backend import (
        CachingRetrievalBackend,
        take_retrieval_cache_thread_diag,
    )
    from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver

    base = _mini_config()
    resolver = RetrievalTuningResolver(base)
    inner = _mock_inner()
    wrapped = CachingRetrievalBackend(inner, config=base, tuning_resolver=resolver)

    with patch.object(resolver, "_load_db_uncached", return_value={}):
        resolver.invalidate()
        wrapped.search("same query", top_k=3)
        if inner.search.call_count != 1:
            failed.append("cache OFF: inner.search must run once")
        diag_off = take_retrieval_cache_thread_diag()
        if diag_off.get("retrieval_cache_hit") or diag_off.get("retrieval_cache_miss"):
            failed.append("cache OFF: must not set hit/miss telemetry")

    with patch.object(
        resolver, "_load_db_uncached", return_value={"enable_retrieval_cache": True}
    ):
        resolver.invalidate()
        inner_on = _mock_inner()
        wrapped_on = CachingRetrievalBackend(
            inner_on, config=base, tuning_resolver=resolver
        )
        wrapped_on.search("same query", top_k=3)
        if inner_on.search.call_count != 1:
            failed.append("cache ON: first query must call inner once (miss)")
        diag_miss = take_retrieval_cache_thread_diag()
        if diag_miss.get("retrieval_cache_miss") is not True:
            failed.append("cache ON: first search should record miss")
        wrapped_on.search("same query", top_k=3)
        if inner_on.search.call_count != 1:
            failed.append("cache ON: HIT must not call inner again")
        diag_hit = take_retrieval_cache_thread_diag()
        if diag_hit.get("retrieval_cache_hit") is not True:
            failed.append("cache ON: second identical search should HIT")

    with patch.object(
        resolver, "_load_db_uncached", return_value={"enable_retrieval_cache": False}
    ):
        resolver.invalidate()
        cfg_off = replace(base, enable_retrieval_cache=True)
        wrapped2 = CachingRetrievalBackend(
            _mock_inner(), config=cfg_off, tuning_resolver=resolver
        )
        wrapped2.search("q", top_k=1)
        if wrapped2._inner.search.call_count != 1:
            failed.append("DB false must disable cache even if build-time config true")

    return failed


def _manager_wrapper_class_db() -> list[str]:
    failed: list[str] = []
    from utils.config import load_config

    cfg = load_config()
    db_url = (cfg.database_url or "").strip()
    if not db_url:
        return failed

    try:
        import psycopg  # noqa: F401, PLC0415
    except ImportError:
        print("[cache_runtime_binding] SKIP DB: psycopg missing")
        return failed

    from repositories.connection import get_connection
    from repositories.platform_settings_repository import KEY_RETRIEVAL_TUNING, PlatformSettingsRepository
    from services.admin_service import AdminService
    from services.cache.caching_retrieval_backend import CachingRetrievalBackend
    from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
    from services.retrieval.runtime_manager import RetrievalBackendManager

    repo = PlatformSettingsRepository()
    with get_connection() as conn:
        repo.delete_setting(conn, KEY_RETRIEVAL_TUNING)
        conn.commit()

    svc = AdminService(cfg)
    mini = _mini_config(database_url=db_url)
    tuning = RetrievalTuningResolver(mini)
    chroma_tmp = Path(tempfile.mkdtemp(prefix="af_cache_bind_chroma_"))
    mgr = RetrievalBackendManager(
        mini,
        project_root=ROOT,
        chroma_persist_directory=chroma_tmp,
        tuning_resolver=tuning,
    )
    emb = MagicMock()
    emb.embed_query.return_value = [0.0] * 4
    emb.embed_documents.return_value = [[0.0] * 4]

    with patch("providers.rag_embeddings.build_openai_embeddings", return_value=emb):
        with patch.object(mgr, "_build_backend") as mock_build:
            mock_build.side_effect = lambda: CachingRetrievalBackend(
                _mock_inner(), config=mini, tuning_resolver=tuning
            )
            be0 = mgr.get_retrieval()
            if not isinstance(be0, CachingRetrievalBackend):
                failed.append("manager must return CachingRetrievalBackend wrapper")

        svc.put_retrieval_tuning({"enable_retrieval_cache": True})
        tuning.invalidate()
        if not tuning.effective_config().enable_retrieval_cache:
            failed.append("PUT enable_retrieval_cache=true not in effective config")

        with patch("providers.rag_embeddings.build_openai_embeddings", return_value=emb):
            with patch(
                "services.retrieval.runtime_manager.RetrievalBackendManager._build_backend",
                return_value=CachingRetrievalBackend(
                    _mock_inner(), config=mini, tuning_resolver=tuning
                ),
            ):
                be1 = mgr.get_retrieval()
                if not isinstance(be1, CachingRetrievalBackend):
                    failed.append("after PUT wrapper must remain CachingRetrievalBackend")

    with get_connection() as conn:
        repo.delete_setting(conn, KEY_RETRIEVAL_TUNING)
        conn.commit()
    svc.delete_retrieval_tuning()

    return failed


def main() -> int:
    failed = _wrapper_live_toggle()
    failed.extend(_manager_wrapper_class_db())
    if failed:
        print("FAIL:", file=sys.stderr)
        for m in failed:
            print(f"  - {m}", file=sys.stderr)
        return 1
    print("OK: test_retrieval_cache_runtime_binding_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
