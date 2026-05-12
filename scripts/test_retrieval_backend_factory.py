#!/usr/bin/env python3
"""
Smoke-тесты фабрики retrieval backend (P6.1 / P6.2a).

Проверяет:
- RAG_BACKEND не задан → chroma;
- chroma + chroma_store → ChromaBackend;
- chroma без store → ValueError;
- faiss без embeddings → ValueError;
- weaviate без embeddings → ValueError;
- faiss пустой индекс (если установлен faiss-cpu) → operational backend с count=0;
- неизвестный backend → ValueError;
- RetrievalBackendManager: FAISS reload при смене mtime manifest (если установлен faiss-cpu).

Запуск из корня репозитория:
  python scripts/test_retrieval_backend_factory.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.retrieval.chroma_backend import ChromaBackend
from services.retrieval.factory import build_retrieval_backend, normalize_rag_backend
from services.retrieval.runtime_manager import RetrievalBackendManager
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

    try:
        build_retrieval_backend(_minimal_app_config(rag_backend="weaviate"), chroma_store=store)
        failed.append("weaviate без embeddings должен raise ValueError")
    except ValueError as e:
        if "embeddings" not in str(e).lower():
            failed.append("weaviate без embeddings: ожидалось упоминание embeddings")

    try:
        import faiss  # noqa: F401, PLC0415

        empty_faiss = tempfile.mkdtemp(prefix="af_faiss_empty_")
        emb = MagicMock()
        emb.embed_query.return_value = [0.0] * 4
        b_faiss = build_retrieval_backend(
            _minimal_app_config(rag_backend="faiss", faiss_index_dir=empty_faiss),
            chroma_store=None,
            embeddings=emb,
        )
        if getattr(b_faiss, "backend_name", None) != "faiss":
            failed.append("faiss без vectors.faiss → backend_name=faiss (пустой operational индекс)")
        if b_faiss.collection_count() != 0:
            failed.append("faiss пустой индекс: collection_count должен быть 0")
    except ImportError:
        print("[factory_smoke] SKIP faiss empty index: нет пакета faiss", flush=True)

    try:
        build_retrieval_backend(_minimal_app_config(rag_backend="unknown_xyz"), chroma_store=store)
        failed.append("unknown backend должен raise ValueError")
    except ValueError as e:
        msg = str(e).lower()
        if "weaviate" not in msg:
            failed.append("unknown backend: ожидалось упоминание weaviate в списке допустимых")

    try:
        import faiss  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import langchain_openai  # noqa: F401, PLC0415
        from unittest.mock import patch

        from services.retrieval.faiss_backend import (
            CHUNKS_FILENAME,
            MANIFEST_FILENAME,
            VECTORS_FILENAME,
        )

        dim = 4
        tmp_idx = Path(tempfile.mkdtemp(prefix="af_mgr_faiss_"))
        index = faiss.IndexFlatL2(dim)
        vecs = np.zeros((1, dim), dtype="float32")
        index.add(vecs)
        faiss.write_index(index, str(tmp_idx / VECTORS_FILENAME))
        (tmp_idx / CHUNKS_FILENAME).write_text(
            json.dumps(
                [
                    {
                        "page_content": "manager reload smoke chunk",
                        "metadata": {"source": "smoke.txt", "chunk_id": "c0"},
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (tmp_idx / MANIFEST_FILENAME).write_text(
            json.dumps({"embedding_dim": dim, "embedding_model": "synthetic"}),
            encoding="utf-8",
        )
        emb2 = MagicMock()
        emb2.embed_query.return_value = [0.0] * dim
        emb2.embed_documents.return_value = [[0.0] * dim]
        cfg_m = _minimal_app_config(rag_backend="faiss", faiss_index_dir=str(tmp_idx))
        with patch("providers.rag_embeddings.build_openai_embeddings", return_value=emb2):
            mgr = RetrievalBackendManager(
                cfg_m,
                project_root=_ROOT,
                chroma_persist_directory=_ROOT / "data" / "chroma_db_factory_smoke",
            )
            r_a = mgr.get_retrieval()
            id_a = id(r_a)
            time.sleep(0.05)
            mf = tmp_idx / MANIFEST_FILENAME
            mf.write_text(
                json.dumps({"embedding_dim": dim, "embedding_model": "synthetic", "bump": 1}),
                encoding="utf-8",
            )
            r_b = mgr.get_retrieval()
            id_b = id(r_b)
            if id_a == id_b:
                failed.append(
                    "RetrievalBackendManager: ожидался reload FAISS после изменения manifest"
                )
    except ImportError:
        print(
            "[factory_smoke] SKIP RetrievalBackendManager FAISS reload: faiss/langchain_openai",
            flush=True,
        )

    old = os.environ.pop("RAG_BACKEND", None)
    try:
        # Пустая строка блокирует подстановку RAG_BACKEND из .env при load_dotenv(override=False).
        os.environ["RAG_BACKEND"] = ""
        from utils.config import load_config

        cfg = load_config()
        if cfg.rag_backend != "chroma":
            failed.append(
                f"без RAG_BACKEND в env ожидается rag_backend=chroma, получено {cfg.rag_backend!r}"
            )
    finally:
        del os.environ["RAG_BACKEND"]
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
