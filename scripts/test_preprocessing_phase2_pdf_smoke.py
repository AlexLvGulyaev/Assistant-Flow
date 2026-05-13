#!/usr/bin/env python3
"""
Smoke test: Phase 2 — PDF → preprocessing → .txt → chunking (без отдельного PDF-pipeline).

Проверяет:
- извлечение PyMuPDF и метаданные diagnostics;
- pdf_cleaner: исчезновение типичного шума (страницы, footer, реклама, support, крошки);
- сохранение содержательных терминов;
- SmartChunker.chunk_text на итоговом тексте.

Полный цикл «индексация + retrieval» в CI без векторного бэкенда не воспроизводится здесь;
проверяйте вручную через Admin upload или существующие RAG-smoke при поднятом Chroma/FAISS/Weaviate.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.chunking.base import ChunkingDocument  # noqa: E402
from services.chunking.smart_chunker import SmartChunker  # noqa: E402
from services.preprocessing import PreprocessingService  # noqa: E402
from services.preprocessing.cleaners.pdf_cleaner import clean_pdf_extracted_text  # noqa: E402
from utils.config import load_config  # noqa: E402


def _assert_pdf_cleaner_strips_noise() -> None:
    raw = (
        "Страница 1 из 3\n"
        "Header noise TESTLINE\n"
        "Footer noise TESTLINE\n"
        "РЕКЛАМА\n"
        "Privacy policy\n"
        "·······\n"
        "Customer service\n"
        "Customer service\n"
        "Home > Archive > News\n"
        "Catalog > Products > Item\n"
        "https://t.me/example\n\n"
        "preprocessing pipeline retrieval lifecycle stages SmartChunker chunking\n"
    )
    out = clean_pdf_extracted_text(raw)
    low = out.lower()
    for bad in (
        "страница 1 из 3",
        "header noise",
        "footer noise",
        "реклама",
        "privacy policy",
        "customer service",
        "t.me/example",
        "home > archive",
        "catalog > products",
    ):
        assert bad not in low, bad
    for good in ("preprocessing", "pipeline", "retrieval", "smartchunker", "chunking"):
        assert good in low, good


def _fixture_pdf_bytes() -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open()
    try:
        p = doc.new_page()
        y = 60
        noise_lines = [
            "Страница 1 из 3",
            "Header noise TESTLINE",
            "Footer noise TESTLINE",
            "РЕКЛАМА",
            "Privacy policy",
            "·······",
            "Customer service",
            "Customer service",
            "Customer service",
            "Home > Archive > News",
            "Catalog > Products > Item",
            "https://t.me/example",
        ]
        for ln in noise_lines:
            p.insert_text((48, y), ln, fontsize=9)
            y += 12
        body = (
            "preprocessing pipeline retrieval lifecycle stages "
            "SmartChunker chunking assistant flow"
        )
        p.insert_text((48, y + 8), body, fontsize=10)

        p2 = doc.new_page()
        p2.insert_text((72, 72), "Second page for boundary test.", fontsize=10)
        return doc.tobytes()
    finally:
        doc.close()


def main() -> None:
    _assert_pdf_cleaner_strips_noise()

    try:
        import fitz  # noqa: F401, PLC0415
    except ImportError:
        print("preprocessing phase2 pdf smoke: OK (pdf_cleaner only; PyMuPDF не установлен)")
        return

    pdf = _fixture_pdf_bytes()
    assert pdf.startswith(b"%PDF"), "ожидался валидный PDF"

    svc = PreprocessingService()
    text, diag = svc.run(pdf, original_filename="phase2-smoke.pdf")
    assert diag.extraction_success
    assert diag.original_format == "pdf"
    assert diag.page_count == 2
    assert diag.log_extractor_id == "pdf_pymupdf"
    low = text.lower()

    for bad in (
        "страница 1 из 3",
        "footer noise",
        "реклама",
        "customer service",
        "t.me/example",
        "home > archive > news",
    ):
        assert bad not in low, f"шум должен быть удалён: {bad!r}"

    for good in (
        "preprocessing",
        "pipeline",
        "retrieval",
        "lifecycle",
        "stages",
        "smartchunker",
        "chunking",
        "second page",
    ):
        assert good in low, f"содержательный фрагмент должен остаться: {good!r}"

    assert "\n---\n" in text or "---" in text, "ожидался разделитель страниц"
    assert diag.cleaned_size_bytes == len(text.encode("utf-8"))
    logd = diag.to_log_dict()
    assert logd.get("extractor") == "pdf_pymupdf"
    assert logd.get("page_count") == 2

    cfg = load_config()
    with tempfile.TemporaryDirectory() as tmp:
        txt_path = Path(tmp) / "phase2-smoke.txt"
        txt_path.write_text(text, encoding="utf-8")

        chunker = SmartChunker.from_app_config(cfg)
        chunk_results = chunker.chunk_text(
            ChunkingDocument(
                text=text,
                metadata={"source": "phase2-smoke.txt", "file_path": str(txt_path)},
            )
        )
        assert len(chunk_results) >= 1, "SmartChunker должен дать хотя бы один чанк"
        joined = "\n".join(c.text for c in chunk_results)
        assert "preprocessing" in joined.lower()

    print("preprocessing phase2 pdf smoke: OK")


if __name__ == "__main__":
    main()
