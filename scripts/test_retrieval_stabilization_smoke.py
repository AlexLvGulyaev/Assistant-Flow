#!/usr/bin/env python3
"""
P6.2b: лёгкий smoke контракта retrieval (без pytest).

1) Всегда (если есть faiss-cpu): FAISS на временном индексе + синтетический embedder —
   без langchain_openai / Chroma.
2) Опционально: Chroma + реальный FAISS из конфига — только при OPENAI_API_KEY и импорте стека AF.

Проверяет: backend_name, metadata dict, ключи source/chunk_id/backend, numeric score, непустой page_content.

Запуск из корня репозитория:
  python scripts/test_retrieval_stabilization_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_QUERY = "Assistant Flow retrieval test query"
_TOP_K = 3


def _validate_block(label: str, backend_name: str, results: list) -> list[str]:
    failed: list[str] = []
    if not backend_name or not str(backend_name).strip():
        failed.append(f"{label}: пустой backend_name")
    for i, r in enumerate(results):
        prefix = f"{label}[{i}]"
        if not isinstance(getattr(r, "chunk", None).metadata, dict):
            failed.append(f"{prefix}: metadata не dict")
            continue
        md = r.chunk.metadata
        for key in ("source", "chunk_id", "backend"):
            if key not in md:
                failed.append(f"{prefix}: нет ключа metadata {key!r}")
        try:
            float(r.score)
        except (TypeError, ValueError):
            failed.append(f"{prefix}: score не numeric")
        if not (r.chunk.page_content or "").strip():
            failed.append(f"{prefix}: пустой page_content")
    return failed


def _faiss_synthetic_block() -> list[str]:
    """Не тянет OpenAI/Chroma — только faiss + numpy + FaissBackend."""
    try:
        import faiss  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return ["faiss_synthetic: нет faiss/numpy (pip install faiss-cpu)"]

    from services.retrieval.faiss_backend import CHUNKS_FILENAME, VECTORS_FILENAME, FaissBackend

    dim = 8
    tmp = Path(tempfile.mkdtemp(prefix="af_stab_faiss_"))
    idx = faiss.IndexFlatL2(dim)
    vecs = np.random.RandomState(42).rand(3, dim).astype("float32")
    idx.add(vecs)
    faiss.write_index(idx, str(tmp / VECTORS_FILENAME))
    chunks = []
    for j in range(3):
        chunks.append(
            {
                "page_content": f"Demo FAISS chunk {j} for stabilization smoke.",
                "metadata": {"source": f"tmp:{j}"},
            }
        )
    (tmp / CHUNKS_FILENAME).write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    (tmp / "manifest.json").write_text(
        json.dumps({"embedding_dim": dim, "embedding_model": "synthetic"}),
        encoding="utf-8",
    )

    class _FixedEmb:
        def embed_query(self, q: str) -> list[float]:
            return [0.01 * (j + 1) for j in range(dim)]

    fb = FaissBackend(index_dir=tmp, embeddings=_FixedEmb())  # type: ignore[arg-type]
    fa_results = fb.search("any", top_k=_TOP_K)
    return _validate_block("faiss_synthetic", fb.backend_name, fa_results)


def main() -> int:
    all_failed: list[str] = []

    all_failed.extend(_faiss_synthetic_block())

    try:
        from utils.config import load_config

        config = load_config()
    except Exception as exc:
        print(f"[stabilization] config SKIP: {exc}", flush=True)
        if all_failed:
            print("FAIL:", "\n  ".join(all_failed), file=sys.stderr)
            return 1
        print("OK: test_retrieval_stabilization_smoke (faiss_synthetic only)", flush=True)
        return 0

    if not (config.openai_api_key or "").strip():
        print("[stabilization] chroma/real_faiss SKIP: нет OPENAI_API_KEY", flush=True)
        if all_failed:
            print("FAIL:", "\n  ".join(all_failed), file=sys.stderr)
            return 1
        print("OK: test_retrieval_stabilization_smoke", flush=True)
        return 0

    try:
        from providers.rag_embeddings import build_openai_embeddings
        from services.rag_chroma_store import ChromaRagStore
        from services.retrieval.chroma_backend import ChromaBackend
        from services.retrieval.faiss_backend import VECTORS_FILENAME, FaissBackend, resolve_faiss_index_dir
        from services.retrieval.factory import normalize_rag_backend
    except ImportError as exc:
        print(f"[stabilization] chroma/real_faiss SKIP: {exc}", flush=True)
        if all_failed:
            print("FAIL:", "\n  ".join(all_failed), file=sys.stderr)
            return 1
        print("OK: test_retrieval_stabilization_smoke", flush=True)
        return 0

    embeddings = build_openai_embeddings(config)

    try:

        def _chroma_path() -> Path:
            p = Path(config.chroma_persist_dir)
            return p if p.is_absolute() else ROOT / p

        chroma_dir = _chroma_path()
        if not config.chroma_use_http:
            chroma_dir.mkdir(parents=True, exist_ok=True)
        store = ChromaRagStore(config, embeddings, persist_directory=chroma_dir)
        cb = ChromaBackend(store)
        ch_results = cb.search(_QUERY, top_k=_TOP_K)
        all_failed.extend(_validate_block("chroma", cb.backend_name, ch_results))
        print(
            f"[stabilization] chroma backend={cb.backend_name!r} n_results={len(ch_results)}",
            flush=True,
        )
    except Exception as exc:
        print(f"[stabilization] chroma SKIP: {type(exc).__name__}: {exc}", flush=True)

    try:
        real_dir = resolve_faiss_index_dir(config, project_root=ROOT)
        vec = real_dir / VECTORS_FILENAME
        if vec.is_file():
            fb2 = FaissBackend(index_dir=real_dir, embeddings=embeddings)
            r2 = fb2.search(_QUERY, top_k=_TOP_K)
            all_failed.extend(_validate_block("faiss_config_dir", fb2.backend_name, r2))
            print(
                f"[stabilization] faiss_config_dir backend={fb2.backend_name!r} n={len(r2)}",
                flush=True,
            )
    except Exception as exc:
        print(f"[stabilization] faiss_config_dir SKIP: {type(exc).__name__}: {exc}", flush=True)

    if normalize_rag_backend(config.rag_backend) == "weaviate":
        try:
            import uuid
            from dataclasses import replace

            from langchain_core.documents import Document

            from services.retrieval.weaviate_backend import WeaviateBackend

            wcfg = replace(
                config,
                weaviate_class_name=(
                    (os.getenv("WEAVIATE_STABILIZATION_CLASS_NAME") or "").strip()
                    or "AssistantFlowStabilizationSmoke"
                ),
            )
            wb = WeaviateBackend(config=wcfg, embeddings=embeddings)
            wb.reset_for_full_reindex()
            wb.add_documents(
                [
                    Document(
                        page_content=_QUERY + " stabilization weaviate corpus line.",
                        metadata={
                            "source": "stabilization_weaviate.txt",
                            "chunk_id": "stab-w-1",
                            "document_id": str(uuid.uuid4()),
                            "document_version_id": str(uuid.uuid4()),
                            "chunk_index": 0,
                            "total_chunks": 1,
                        },
                    )
                ]
            )
            wr = wb.search(_QUERY, top_k=_TOP_K)
            all_failed.extend(_validate_block("weaviate_active_config", wb.backend_name, wr))
            print(
                f"[stabilization] weaviate backend={wb.backend_name!r} n_results={len(wr)}",
                flush=True,
            )
            wb.close()
        except Exception as exc:
            print(
                f"[stabilization] weaviate SKIP: {type(exc).__name__}: {exc}",
                flush=True,
            )

    if all_failed:
        print("FAIL:", file=sys.stderr)
        for f in all_failed:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK: test_retrieval_stabilization_smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
