#!/usr/bin/env python3
"""
Сбор изолированного демо FAISS-индекса (P6.2a).

Использует OpenAI embeddings из AF (providers.rag_embeddings), не lesson-local embedders.
Не вызывает production Chroma indexers и не трогает PostgreSQL.

Запуск из корня репозитория (нужен OPENAI_API_KEY):
  python scripts/build_faiss_demo_index.py
  python scripts/build_faiss_demo_index.py --out-dir /tmp/my_faiss
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Небольшой демо-корпус (RU): фиксированные строки, без зависимости от RAG_DOCUMENTS_DIR.
_DEMO_CHUNKS: list[tuple[str, dict[str, str]]] = [
    (
        "Assistant Flow — операционная платформа с RAG, Telegram-ботом и Admin UI.",
        {"source": "faiss_demo:intro"},
    ),
    (
        "Retrieval: Chroma остаётся primary production backend; FAISS — secondary demo.",
        {"source": "faiss_demo:retrieval"},
    ),
    (
        "PostgreSQL хранит метаданные и lifecycle; векторы Chroma/FAISS не заменяют контракт БД.",
        {"source": "faiss_demo:storage"},
    ),
    (
        "Portfolio compose: воспроизводимый контур для регрессий и чистого bootstrap PostgreSQL.",
        {"source": "faiss_demo:deploy"},
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build isolated FAISS demo index for AF.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Каталог для vectors.faiss / chunks.json / manifest.json (иначе из config FAISS_INDEX_DIR).",
    )
    args = parser.parse_args()

    import faiss  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    from providers.rag_embeddings import build_openai_embeddings
    from services.retrieval.faiss_backend import (
        CHUNKS_FILENAME,
        MANIFEST_FILENAME,
        VECTORS_FILENAME,
        resolve_faiss_index_dir,
    )
    from utils.config import load_config

    config = load_config()
    if args.out_dir is not None:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = resolve_faiss_index_dir(config, project_root=ROOT)

    out_dir.mkdir(parents=True, exist_ok=True)

    texts = [t for t, _ in _DEMO_CHUNKS]
    embedder = build_openai_embeddings(config)
    vectors = embedder.embed_documents(texts)
    if not vectors:
        print("FAIL: пустые эмбеддинги", file=sys.stderr)
        return 1
    dim = len(vectors[0])
    arr = np.asarray(vectors, dtype=np.float32)
    index = faiss.IndexFlatL2(dim)
    index.add(arr)

    vec_path = out_dir / VECTORS_FILENAME
    faiss.write_index(index, str(vec_path))

    chunks_payload = [{"page_content": t, "metadata": dict(m)} for t, m in _DEMO_CHUNKS]
    (out_dir / CHUNKS_FILENAME).write_text(
        json.dumps(chunks_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = {
        "embedding_dim": dim,
        "embedding_model": config.openai_embedding_model,
    }
    (out_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[assistant-flow] FAISS demo index: {out_dir}", flush=True)
    print(f"  vectors={vec_path.name} ntotal={index.ntotal} dim={dim}", flush=True)
    print(f"  {CHUNKS_FILENAME} records={len(chunks_payload)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
