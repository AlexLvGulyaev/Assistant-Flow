#!/usr/bin/env python3
"""
P6.10: smoke DB-backed active RAG backend + manager resolution (без pytest).

Проверяет:
- effective_rag_backend_from_sources (DB vs env);
- repository set invalid → ValueError;
- при DATABASE_URL: set/peek + RetrievalBackendManager effective после refresh;
- нет «тихого» игнорирования явного DB backend (валидная строка перекрывает env).

Запуск из корня репозитория:
  python scripts/test_retrieval_runtime_switch_smoke.py

Без DATABASE_URL: только unit-части без Postgres.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msgs: list[str]) -> int:
    print("FAIL:", file=sys.stderr)
    for m in msgs:
        print(f"  - {m}", file=sys.stderr)
    return 1


def main() -> int:
    failed: list[str] = []

    from services.retrieval.factory import effective_rag_backend_from_sources

    if effective_rag_backend_from_sources(env_backend="chroma", db_backend=None) != "chroma":
        failed.append("env chroma + no db → chroma")
    if effective_rag_backend_from_sources(env_backend="chroma", db_backend="weaviate") != "weaviate":
        failed.append("db weaviate must override env chroma")
    if effective_rag_backend_from_sources(env_backend="faiss", db_backend=None) != "faiss":
        failed.append("env faiss + no db")

    try:
        import psycopg  # noqa: F401, PLC0415
    except ImportError:
        print(
            "[runtime_switch_smoke] SKIP repository/manager DB tests: psycopg not installed",
            flush=True,
        )
        if failed:
            return _fail(failed)
        print("OK: test_retrieval_runtime_switch_smoke (factory only)")
        return 0

    from repositories.platform_settings_repository import (
        KEY_ACTIVE_RAG_BACKEND,
        PlatformSettingsRepository,
    )

    repo = PlatformSettingsRepository()
    try:
        repo.set_active_rag_backend(MagicMock(), "nope")  # type: ignore[arg-type]
        failed.append("set_active invalid must raise")
    except ValueError:
        pass
    except Exception as exc:
        failed.append(f"set_active unexpected: {exc}")

    from utils.config import AppConfig, load_config

    cfg = load_config()
    env_du = (os.getenv("DATABASE_URL") or "").strip()
    if env_du:
        got = (cfg.database_url or "").strip()
        if not got:
            failed.append("load_config: database_url missing while DATABASE_URL is set")
        elif got != env_du:
            failed.append("load_config: database_url must match DATABASE_URL")
    db_url = (cfg.database_url or "").strip()
    if not db_url:
        print(
            "[runtime_switch_smoke] SKIP postgres-backed checks: DATABASE_URL unset",
            flush=True,
        )
        if failed:
            return _fail(failed)
        print("OK: test_retrieval_runtime_switch_smoke (no DB)")
        return 0

    try:
        from repositories.connection import get_connection
        from services.retrieval.runtime_manager import RetrievalBackendManager

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM platform_settings WHERE key = %s",
                (KEY_ACTIVE_RAG_BACKEND,),
            )
            conn.commit()

        mini = AppConfig(
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
            database_url=db_url,
            rag_backend="chroma",
            faiss_index_dir=str(Path(tempfile.mkdtemp(prefix="af_rt_sw_faiss_"))),
        )
        chroma_tmp = Path(tempfile.mkdtemp(prefix="af_rt_sw_chroma_"))
        mgr = RetrievalBackendManager(
            mini,
            project_root=ROOT,
            chroma_persist_directory=chroma_tmp,
        )
        emb = MagicMock()
        emb.embed_query.return_value = [0.0] * 4
        emb.embed_documents.return_value = [[0.0] * 4]
        with patch("providers.rag_embeddings.build_openai_embeddings", return_value=emb):
            e0 = mgr.effective_backend_name()
            if e0 != "chroma":
                failed.append(f"no db row: effective expected chroma, got {e0!r}")
            with get_connection() as conn:
                repo.set_active_rag_backend(conn, "faiss")
                conn.commit()
            mgr.refresh(reason="smoke_switch")
            mgr._eff_cached_backend = None  # noqa: SLF001
            e1 = mgr.effective_backend_name()
            if e1 != "faiss":
                failed.append(f"after db=faiss effective expected faiss, got {e1!r}")
            with get_connection() as conn:
                repo.set_active_rag_backend(conn, "chroma")
                conn.commit()
            mgr.refresh(reason="smoke_reset")
            mgr._eff_cached_backend = None  # noqa: SLF001
            e2 = mgr.effective_backend_name()
            if e2 != "chroma":
                failed.append(f"after db=chroma effective expected chroma, got {e2!r}")

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM platform_settings WHERE key = %s",
                (KEY_ACTIVE_RAG_BACKEND,),
            )
            conn.commit()
    except Exception as exc:
        failed.append(f"postgres branch: {type(exc).__name__}: {exc}")

    if failed:
        return _fail(failed)
    print("OK: test_retrieval_runtime_switch_smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
