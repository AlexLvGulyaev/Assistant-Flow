#!/usr/bin/env python3
"""
Smoke: ChromaBackend и FaissBackend — разные классы, разные backend_name, один запрос.

Цель — исключить «тихую» подмену backend (один объект на два режима) и показать top scores
+ идентификаторы чанков. Совпадение distance до 3–4 знака при одинаковых embeddings и L2 —
ожидаемо (см. engineering log), но классы и пути хранилища должны различаться.

Запуск из корня репозитория:
  python scripts/test_retrieval_backend_identity_smoke.py "ваш запрос"

Требования: OPENAI_API_KEY, Chroma по конфигу, собранный FAISS_INDEX_DIR.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TOP_K = 5


def _chunk_row_id(meta: dict) -> str:
    for k in ("chunk_id", "id", "chroma_id"):
        v = meta.get(k)
        if v:
            return str(v)
    return "—"


def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or "Assistant Flow RAG retrieval"
    from providers.rag_embeddings import build_openai_embeddings
    from services.rag_chroma_store import ChromaRagStore
    from services.retrieval.chroma_backend import ChromaBackend
    from services.retrieval.faiss_backend import FaissBackend, resolve_faiss_index_dir
    from utils.config import load_config

    cfg = load_config()
    if not (cfg.openai_api_key or "").strip():
        print("FAIL: нужен OPENAI_API_KEY", file=sys.stderr)
        return 1

    emb = build_openai_embeddings(cfg)
    chroma_dir = Path(cfg.chroma_persist_dir)
    if not cfg.chroma_use_http:
        chroma_dir = chroma_dir if chroma_dir.is_absolute() else ROOT / chroma_dir
        chroma_dir.mkdir(parents=True, exist_ok=True)

    store = ChromaRagStore(cfg, emb, persist_directory=chroma_dir)
    cb = ChromaBackend(store)
    idx = resolve_faiss_index_dir(cfg, project_root=ROOT)
    fb = FaissBackend(index_dir=idx, embeddings=emb, app_config=cfg, allow_empty=False)

    assert type(cb) is not type(fb), "FAIL: один и тот же класс backend"
    assert id(cb) != id(fb), "FAIL: один и тот же объект"
    assert cb.backend_name == "chroma", f"FAIL: chroma name={cb.backend_name!r}"
    assert fb.backend_name == "faiss", f"FAIL: faiss name={fb.backend_name!r}"

    print(
        f"[identity] ChromaBackend={type(cb).__name__} id={id(cb):#x} "
        f"FaissBackend={type(fb).__name__} id={id(fb):#x}",
        flush=True,
    )
    print(f"[identity] faiss_index_dir={fb.index_dir}", flush=True)

    cr = cb.search(query, top_k=_TOP_K)
    fr = fb.search(query, top_k=_TOP_K)
    print(f"[identity] chroma rows={len(cr)} faiss rows={len(fr)}", flush=True)

    def dump(title: str, rows: list) -> None:
        print(f"\n=== {title} ===", flush=True)
        for i, r in enumerate(rows, 1):
            m = dict(r.chunk.metadata or {})
            src = str(m.get("source", "?"))
            rid = _chunk_row_id(m)
            print(
                f"  [{i}] score={float(r.score):.6f} source={src!r} row_id={rid!r} "
                f"meta.backend={m.get('retrieval_backend', m.get('backend', '—'))!r}",
                flush=True,
            )

    dump("Chroma", cr, "chroma")
    dump("FAISS", fr, "faiss")

    if cr and fr:
        same_scores = all(
            abs(float(cr[i].score) - float(fr[i].score)) < 1e-3
            for i in range(min(len(cr), len(fr), 3))
        )
        if same_scores:
            print(
                "\n[identity] примечание: top scores близки — типично при одинаковой "
                "модели эмбеддингов и L2-метрике на том же корпусе чанков (см. лог аудита).",
                flush=True,
            )

    print("\n[identity] OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
