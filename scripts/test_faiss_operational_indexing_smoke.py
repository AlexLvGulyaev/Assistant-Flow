#!/usr/bin/env python3
"""
Operational FAISS indexing smoke (без pytest).

Проверяет AdminKnowledgeIndexer → FAISS persistence → retrieval, идемпотентность full reindex.

Требуется OPENAI_API_KEY (эмбеддинги). Запуск из корня репозитория:
  python scripts/test_faiss_operational_indexing_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print(
            "SKIP test_faiss_operational_indexing_smoke: OPENAI_API_KEY not set",
            flush=True,
        )
        return 0

    failed: list[str] = []

    from providers.rag_embeddings import build_openai_embeddings
    from services.admin_knowledge_indexer import AdminKnowledgeIndexer
    from services.retrieval.faiss_backend import (
        CHUNKS_FILENAME,
        MANIFEST_FILENAME,
        FaissBackend,
        VECTORS_FILENAME,
        resolve_faiss_index_dir,
    )
    from utils.config import load_config

    with tempfile.TemporaryDirectory(prefix="af_faiss_op_") as tmp:
        tmp_root = Path(tmp)
        docs = tmp_root / "docs"
        docs.mkdir()
        phrase = "UniqueOperationalFAISSSmokePhrase_7f3a9c2e"
        (docs / "one.txt").write_text(
            f"{phrase} alpha beta gamma.\nSecond line for chunking.\n", encoding="utf-8"
        )
        (docs / "two.txt").write_text("Other doc content zzz.\n", encoding="utf-8")

        base = load_config()
        faiss_dir = tmp_root / "faiss_idx"
        cfg = replace(
            base,
            rag_backend="faiss",
            faiss_index_dir=str(faiss_dir),
            rag_documents_dir=str(docs),
        )

        indexer = AdminKnowledgeIndexer(
            cfg,
            documents_dir=docs,
            chroma_dir=tmp_root / "chroma_unused",
            use_postgres=False,
        )

        r1 = indexer.run(reindex=True)
        if r1.vector_index_chunk_count <= 0:
            failed.append("first reindex: vector_index_chunk_count > 0")
        if r1.chunks_created <= 0:
            failed.append("first reindex: chunks_created > 0")

        idx_abs = resolve_faiss_index_dir(cfg, project_root=ROOT)
        if not (idx_abs / VECTORS_FILENAME).is_file():
            failed.append("vectors.faiss missing")
        if not (idx_abs / CHUNKS_FILENAME).is_file():
            failed.append("chunks.json missing")
        if not (idx_abs / MANIFEST_FILENAME).is_file():
            failed.append("manifest.json missing")

        chunks_raw = json.loads((idx_abs / CHUNKS_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(chunks_raw, list) or len(chunks_raw) == 0:
            failed.append("chunks.json must be non-empty list")

        manifest = json.loads((idx_abs / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        for key in (
            "backend",
            "embedding_model",
            "embedding_dim",
            "created_at",
            "chunk_count",
            "document_count",
            "source",
        ):
            if key not in manifest:
                failed.append(f"manifest missing key {key!r}")
        if manifest.get("source") != "operational_indexer":
            failed.append("manifest.source must be operational_indexer")
        if manifest.get("backend") != "faiss":
            failed.append("manifest.backend must be faiss")

        emb = build_openai_embeddings(cfg)
        fb = FaissBackend(
            index_dir=idx_abs,
            embeddings=emb,
            app_config=cfg,
            allow_empty=False,
        )
        if fb.collection_count() != r1.vector_index_chunk_count:
            failed.append("FaissBackend.collection_count vs report mismatch")

        hits = fb.search(phrase, top_k=5)
        if not any(phrase in (h.chunk.page_content or "") for h in hits):
            failed.append("retrieval must return chunk containing phrase")
        if not hits or not (hits[0].chunk.metadata.get("source")):
            failed.append("source metadata must be present")

        r2 = indexer.run(reindex=True)
        if r2.vector_index_chunk_count != r1.vector_index_chunk_count:
            failed.append(
                f"second full reindex must not duplicate chunks: "
                f"{r1.vector_index_chunk_count} vs {r2.vector_index_chunk_count}"
            )

    if failed:
        print("FAIL:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK: test_faiss_operational_indexing_smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
