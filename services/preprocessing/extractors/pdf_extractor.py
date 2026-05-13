from __future__ import annotations

import re

from services.preprocessing.extractors.base_extractor import BaseExtractor


def _normalize_whitespace_per_page(page_text: str) -> str:
    """Только пробелы/пустые строки внутри страницы; шумовые шаблоны — в ``pdf_cleaner``."""
    raw_lines = page_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for raw_line in raw_lines:
        collapsed = re.sub(r"[ \t]{2,}", " ", raw_line).rstrip()
        out.append(collapsed)
    merged: list[str] = []
    empty_run = 0
    for ln in out:
        if not ln.strip():
            empty_run += 1
            if empty_run <= 2:
                merged.append("")
        else:
            empty_run = 0
            merged.append(ln)
    while merged and not merged[0].strip():
        merged.pop(0)
    while merged and not merged[-1].strip():
        merged.pop()
    return "\n".join(merged)


class PdfExtractor(BaseExtractor):
    """
    Извлечение текста из PDF через PyMuPDF (fitz).

    Постранично; между страницами вставляется разделитель ``\\n\\n---\\n\\n``,
    чтобы downstream clean/normalize не склеивали контент в монолит без границ.
    """

    _PAGE_SEPARATOR = "\n\n---\n\n"
    last_page_count: int = 0

    def extract(self, raw: bytes, *, original_filename: str) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PyMuPDF (fitz) не установлен: добавьте пакет PyMuPDF в окружение."
            ) from exc

        if not raw:
            raise ValueError("empty PDF payload")

        doc = fitz.open(stream=raw, filetype="pdf")
        try:
            n = int(doc.page_count)
            self.last_page_count = n
            if n <= 0:
                return ""
            parts: list[str] = []
            for i in range(n):
                page = doc.load_page(i)
                raw_page = page.get_text("text") or ""
                cleaned = _normalize_whitespace_per_page(raw_page)
                parts.append(cleaned)
            return self._PAGE_SEPARATOR.join(parts)
        finally:
            doc.close()
