#!/usr/bin/env python3
"""
Smoke-тесты фабрики retrieval backend (P6.1 / P6.2a).

Проверяет:
- RAG_BACKEND не задан → chroma;
- chroma + chroma_store → ChromaBackend;
- chroma без store → ValueError;
- faiss без embeddings → ValueError;
- faiss без файлов индекса → ValueError (без fallback на Chroma);
- неизвестный backend → ValueError.

Запуск из корня репозитория:
  python scripts/test_retrieval_backend_factory.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.retrieval.chroma_backend import ChromaBackend
from services.retrieval.factory import build_retrieval_backend, normalize_rag_backend
from utils.config import AppConfig


def _minimal_app_config(
    *,
    rag_backend: str = "chroma",
    faiss_index_dir: str | None = None,
) -> AppConfig:
    fid = faiss_index_dir if faiss_index_dir is not None else "storage/faiss"
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
        rag_backend=rag_backend,
        faiss_index_dir=fid,
    )


def _fake_chroma_store() -> MagicMock:
    store = MagicMock()
    store.collection_count.return_value = 0
    store.native_similarity_search_with_score.return_value = []
    return store


def main() -> int:
    failed: list[str] = []

    if normalize_rag_backend(None) != "chroma":
        failed.append("normalize_rag_backend(None) должен быть chroma")
    if normalize_rag_backend("") != "chroma":
        failed.append("normalize_rag_backend('') должен быть chroma")
    if normalize_rag_backend("  CHROMA  ") != "chroma":
        failed.append("normalize_rag_backend должен trim/lowercase")

    store = _fake_chroma_store()

    b1 = build_retrieval_backend(_minimal_app_config(rag_backend="chroma"), chroma_store=store)
    if not isinstance(b1, ChromaBackend):
        failed.append("rag_backend=chroma → ChromaBackend")
    if b1.backend_name != "chroma":
        failed.append("backend_name chroma")

    try:
        build_retrieval_backend(_minimal_app_config(rag_backend="chroma"), chroma_store=None)
        failed.append("chroma без chroma_store должен raise ValueError")
    except ValueError as e:
        if "chroma_store" not in str(e).lower():
            failed.append("chroma без store: ожидалось упоминание chroma_store")

    try:
        build_retrieval_backend(_minimal_app_config(rag_backend="faiss"), chroma_store=store)
        failed.append("faiss без embeddings должен raise ValueError")
    except ValueError as e:
        if "embeddings" not in str(e).lower():
            failed.append("faiss без embeddings: ожидалось упоминание embeddings")

    empty_faiss = tempfile.mkdtemp(prefix="af_faiss_empty_")
    try:
        build_retrieval_backend(
            _minimal_app_config(rag_backend="faiss", faiss_index_dir=empty_faiss),
            chroma_store=None,
            embeddings=MagicMock(),
        )
        failed.append("faiss без vectors.faiss должен raise ValueError")
    except ValueError as e:
        msg = str(e).lower()
        if "faiss" not in msg and "индекс" not in msg:
            failed.append("faiss без индекса: ожидалось понятное сообщение")

    try:
        build_retrieval_backend(_minimal_app_config(rag_backend="unknown_xyz"), chroma_store=store)
        failed.append("unknown backend должен raise ValueError")
    except ValueError:
        pass

    old = os.environ.pop("RAG_BACKEND", None)
    try:
        from utils.config import load_config

        cfg = load_config()
        if cfg.rag_backend != "chroma":
            failed.append(
                f"без RAG_BACKEND в env ожидается rag_backend=chroma, получено {cfg.rag_backend!r}"
            )
    finally:
        if old is not None:
            os.environ["RAG_BACKEND"] = old

    if failed:
        print("FAIL:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: test_retrieval_backend_factory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
