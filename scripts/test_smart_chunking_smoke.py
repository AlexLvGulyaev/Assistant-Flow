#!/usr/bin/env python3
"""
P6.3: smoke SmartChunker (без pytest).

Сценарии: короткий текст; много абзацев; большой текст; один очень длинный абзац.

Запуск из корня:
  python scripts/test_smart_chunking_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _cfg():
    from unittest.mock import MagicMock

    m = MagicMock()
    m.rag_chunk_size = 400
    m.rag_chunk_overlap = 60
    return m


def _run(name: str, text: str) -> tuple[int, list[str]]:
    from services.chunking.base import ChunkingDocument
    from services.chunking.smart_chunker import SmartChunker

    c = SmartChunker.from_app_config(_cfg())
    doc = ChunkingDocument(text=text, metadata={"source": f"smoke:{name}"})
    res = c.chunk_text(doc)
    return len(res), [r.text for r in res]


def main() -> int:
    failed: list[str] = []

    n_short, parts_short = _run("short", "Один короткий абзац.")
    if n_short < 1:
        failed.append("short: ожидался хотя бы один chunk")
    if not all(p.strip() for p in parts_short):
        failed.append("short: пустой chunk")

    # Достаточно длинные абзацы, иначе merge tiny paragraphs даёт один chunk (это ожидаемо).
    big_para = ("Строка абзаца с содержимым. " * 20 + "\n\n") * 12
    n_para, _ = _run("paragraphs", big_para)
    if n_para < 2:
        failed.append("paragraphs: ожидалось разбиение на несколько chunks")

    large = ("Раздел A.\n\n" + "Предложение. " * 200 + "\n\n" + "Раздел B.\n\n" + "Ещё текст.\n\n") * 5
    n_large, parts_large = _run("large", large)
    if n_large < 3:
        failed.append("large: ожидалось несколько chunks")
    for i, p in enumerate(parts_large):
        if len(p) > 9000:
            failed.append(f"large: chunk {i} слишком длинный (giant chunk guard)")

    patho = "X" * 50000
    n_patho, parts_patho = _run("pathological", patho)
    if n_patho < 2:
        failed.append("pathological: длинный абзац должен дать несколько частей")
    if n_patho > 5000:
        failed.append("pathological: слишком много chunks (explosion)")

    for i, p in enumerate(parts_patho):
        if not p.strip():
            failed.append(f"pathological: пустой chunk {i}")

    from services.chunking.base import ChunkingDocument
    from services.chunking.smart_chunker import SmartChunker

    c2 = SmartChunker.from_app_config(_cfg())
    one = c2.chunk_text(ChunkingDocument(text="Hello world.", metadata={"source": "t"}))
    if one:
        md = one[0].metadata
        for k in ("chunk_index", "total_chunks", "chunking_strategy", "approximate_size"):
            if not hasattr(md, k):
                failed.append(f"metadata missing field {k!r}")
    else:
        failed.append("single-line doc: expected one chunk")

    if failed:
        print("FAIL:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(
        f"OK: test_smart_chunking_smoke "
        f"(short={n_short} para={n_para} large={n_large} patho={n_patho})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
