#!/usr/bin/env python3
"""
P6.9: smoke operational Weaviate backend (schema, add, search, metadata, health).

Требует доступный Weaviate (compose) и OPENAI_API_KEY для embeddings.
Использует отдельный класс схемы по умолчанию ``AssistantFlowWeaviateSmoke``,
чтобы не трогать production ``WEAVIATE_CLASS_NAME``.

Переменные:
  WEAVIATE_SMOKE_CLASS_NAME — override имени класса в Weaviate.
  WEAVIATE_URL / WEAVIATE_HOST / WEAVIATE_HTTP_PORT — как в AppConfig.

Запуск из корня репозитория:
  python scripts/test_weaviate_operational_indexing_smoke.py

Exit 0 при SKIP (нет ключа или Weaviate недоступен); exit 1 при FAIL тестов.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SMOKE_CLASS = (os.getenv("WEAVIATE_SMOKE_CLASS_NAME") or "AssistantFlowWeaviateSmoke").strip()


def _fail(msgs: list[str]) -> int:
    print("FAIL:", file=sys.stderr)
    for m in msgs:
        print(f"  - {m}", file=sys.stderr)
    return 1


def main() -> int:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print(
            "[weaviate_smoke] SKIP: нет OPENAI_API_KEY (embeddings обязательны для BYOV)",
            flush=True,
        )
        return 0

    try:
        from langchain_core.documents import Document
        from utils.config import load_config

        from providers.rag_embeddings import build_openai_embeddings
        from services.retrieval.weaviate_backend import WeaviateBackend
    except ImportError as exc:
        print(f"[weaviate_smoke] SKIP: import failed: {exc}", flush=True)
        return 0

    failed: list[str] = []

    base = load_config()
    cfg = replace(
        base,
        rag_backend="weaviate",
        weaviate_class_name=_SMOKE_CLASS or "AssistantFlowWeaviateSmoke",
    )

    try:
        embeddings = build_openai_embeddings(cfg)
        backend = WeaviateBackend(config=cfg, embeddings=embeddings)
    except Exception as exc:
        print(
            f"[weaviate_smoke] SKIP: не удалось подключиться к Weaviate: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return 0

    try:
        hc = backend.healthcheck()
        if hc.backend != "weaviate":
            failed.append(f"healthcheck.backend ожидался weaviate, получено {hc.backend!r}")
        if not hc.ok:
            failed.append(f"healthcheck.ok=False detail={hc.detail!r}")

        backend.reset_for_full_reindex()

        doc_id = str(uuid.uuid4())
        ver_id = str(uuid.uuid4())
        docs = [
            Document(
                page_content="Weaviate operational smoke: unique phrase zebra_alpha_42.",
                metadata={
                    "source": "smoke_weaviate.md",
                    "document_id": doc_id,
                    "document_version_id": ver_id,
                    "chunk_index": 0,
                    "total_chunks": 1,
                },
            )
        ]
        ids = backend.add_documents(docs)
        if len(ids) != 1:
            failed.append(f"add_documents должен вернуть 1 id, получено {len(ids)}")

        n = backend.collection_count()
        if n < 1:
            failed.append(f"collection_count после add ожидался >=1, получено {n}")

        results = backend.search("zebra_alpha_42", top_k=3)
        if not results:
            failed.append("search вернул пустой список")
        else:
            r0 = results[0]
            md = r0.chunk.metadata
            for key in ("source", "chunk_id", "backend", "document_id", "document_version_id"):
                if key not in md:
                    failed.append(f"metadata без обязательного ключа {key!r}")
            if md.get("backend") != "weaviate":
                failed.append("metadata.backend должен быть weaviate")
            if md.get("source") != "smoke_weaviate.md":
                failed.append(f"metadata.source неожидан: {md.get('source')!r}")
            if str(md.get("document_id") or "") != doc_id:
                failed.append("metadata.document_id не совпал с записанным")
            if str(md.get("document_version_id") or "") != ver_id:
                failed.append("metadata.document_version_id не совпал")
            ci = md.get("chunk_index")
            tc = md.get("total_chunks")
            if ci != 0:
                failed.append(f"chunk_index ожидался 0, получено {ci!r}")
            if tc != 1:
                failed.append(f"total_chunks ожидался 1, получено {tc!r}")

        backend.delete_vectors_for_document_before_reindex(
            document_id=uuid.UUID(doc_id),
            source_filename="smoke_weaviate.md",
        )
        after_del = backend.collection_count()
        if after_del != 0:
            failed.append(f"после delete_many count ожидался 0, получено {after_del}")
    finally:
        backend.close()

    if failed:
        return _fail(failed)

    print("OK: test_weaviate_operational_indexing_smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
