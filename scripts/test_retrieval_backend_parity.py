#!/usr/bin/env python3
"""
Smoke / inspection: один запрос к Chroma и к FAISS (если доступны).

Не бенчмарк. Сравнение top-k, scores (L2 distance), превью чанков.

Запуск из корня:
  python scripts/test_retrieval_backend_parity.py "ваш запрос"

Требования:
- OPENAI_API_KEY (через load_config / .env);
- Chroma по конфигу (HTTP или локальный путь);
- FAISS: собранный индекс в FAISS_INDEX_DIR (см. scripts/build_faiss_demo_index.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TOP_K = 5
_PREVIEW = 180


def _resolve_path(config_value: str) -> Path:
    p = Path(config_value)
    return p if p.is_absolute() else ROOT / p


def _print_block(title: str, backend: str, results: list) -> None:
    print(f"\n=== {title} (backend={backend}) ===", flush=True)
    if not results:
        print("  (нет результатов)", flush=True)
        return
    for i, r in enumerate(results, 1):
        prev = (r.chunk.page_content or "").replace("\n", " ")
        if len(prev) > _PREVIEW:
            prev = prev[: _PREVIEW - 1] + "…"
        src = r.chunk.metadata.get("source", "?")
        print(f"  [{i}] score(L2)={r.score:.6f} source={src!r}", flush=True)
        print(f"      {prev}", flush=True)


def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or "Что такое Assistant Flow и RAG?"

    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore
    from services.retrieval.chroma_backend import ChromaBackend
    from services.retrieval.faiss_backend import FaissBackend, resolve_faiss_index_dir
    from utils.config import load_config

    config = load_config()
    if not (config.openai_api_key or "").strip():
        print("FAIL: нужен OPENAI_API_KEY (см. .env)", file=sys.stderr)
        return 1

    embeddings = build_openai_embeddings(config)
    chroma_ok = False

    # --- Chroma ---
    try:
        chroma_dir = _resolve_path(config.chroma_persist_dir)
        if not config.chroma_use_http:
            chroma_dir.mkdir(parents=True, exist_ok=True)
        store = ChromaRagStore(
            config,
            embeddings,
            persist_directory=chroma_dir,
        )
        chroma_b = ChromaBackend(store)
        ch_res = chroma_b.search(query, top_k=_TOP_K)
        h = chroma_b.healthcheck()
        print(
            f"[parity] chroma health ok={h.ok} count={h.collection_count}",
            flush=True,
        )
        _print_block("Chroma", chroma_b.backend_name, ch_res)
        chroma_ok = True
    except Exception as exc:
        print(f"[parity] Chroma: SKIP ({type(exc).__name__}: {exc})", flush=True)

    # --- FAISS (основной контур для smoke parity в P6.2a) ---
    idx_dir = resolve_faiss_index_dir(config, project_root=ROOT)
    try:
        fb = FaissBackend(index_dir=idx_dir, embeddings=embeddings)
        fh = fb.healthcheck()
        print(
            f"[parity] faiss health ok={fh.ok} count={fh.collection_count} "
            f"index_dir={fb.index_dir}",
            flush=True,
        )
        if not fh.ok:
            print(f"[parity] FAISS: health detail={fh.detail}", flush=True)
            return 1
        fa_res = fb.search(query, top_k=_TOP_K)
        _print_block("FAISS", fb.backend_name, fa_res)
    except Exception as exc:
        print(f"[parity] FAISS: FAIL ({type(exc).__name__}: {exc})", flush=True)
        return 1

    if not chroma_ok:
        print("\n[parity] примечание: Chroma пропущен; FAISS-контур проверен.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
