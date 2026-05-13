from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from services.preprocessing.cleaners.html_cleaner import clean_html_extracted_text
from services.preprocessing.cleaners.pdf_cleaner import clean_pdf_extracted_text
from services.preprocessing.cleaners.text_cleaner import clean_extracted_text
from services.preprocessing.extractors.html_extractor import HtmlExtractor
from services.preprocessing.extractors.pdf_extractor import PdfExtractor
from services.preprocessing.extractors.txt_extractor import TxtExtractor
from services.preprocessing.normalizers.text_normalizer import normalize_text


Format = Literal["txt", "html", "pdf"]


@dataclass(frozen=True)
class PreprocessingDiagnostics:
    extraction_success: bool
    original_format: Format
    original_bytes: int
    cleaned_char_len: int
    extracted_char_len: int
    removed_line_count: int
    preview_raw: str | None
    preview_cleaned: str | None
    cleaned_size_bytes: int
    error: str | None = None
    page_count: int | None = None
    log_extractor_id: str | None = None

    def to_log_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": "ok" if self.extraction_success else "error",
            "extraction_success": self.extraction_success,
            "original_format": self.original_format,
            "original_bytes": int(self.original_bytes),
            "cleaned_char_len": int(self.cleaned_char_len),
            "extracted_char_len": int(self.extracted_char_len),
            "extracted_characters": int(self.extracted_char_len),
            "removed_line_count": int(self.removed_line_count),
            "cleaned_size_bytes": int(self.cleaned_size_bytes),
        }
        if self.log_extractor_id:
            out["extractor"] = self.log_extractor_id
        if self.page_count is not None:
            out["page_count"] = int(self.page_count)
        if self.preview_raw:
            out["preview_raw"] = self.preview_raw
        if self.preview_cleaned:
            out["preview_cleaned"] = self.preview_cleaned
        if self.error:
            out["error"] = self.error
        return out


class PreprocessingService:
    """Preprocessing: txt, html, pdf (PyMuPDF) → cleaners → нормализация UTF-8."""

    _PREVIEW = 480

    def run(self, raw: bytes, *, original_filename: str) -> tuple[str, PreprocessingDiagnostics]:
        if not isinstance(raw, (bytes, bytearray)) or len(raw) == 0:
            raise ValueError("empty payload")
        safe = Path(original_filename).name
        ext = Path(safe).suffix.lower()
        page_count: int | None = None
        log_extractor_id: str | None = None

        if ext == ".txt":
            fmt: Format = "txt"
            extracted = TxtExtractor().extract(raw, original_filename=safe)
            after_struct = clean_extracted_text(extracted)
        elif ext in (".html", ".htm"):
            fmt = "html"
            extracted = HtmlExtractor().extract(raw, original_filename=safe)
            after_struct = clean_html_extracted_text(extracted)
        elif ext == ".pdf":
            fmt = "pdf"
            pdf_ex = PdfExtractor()
            extracted = pdf_ex.extract(raw, original_filename=safe)
            log_extractor_id = "pdf_pymupdf"
            page_count = pdf_ex.last_page_count
            extracted = clean_pdf_extracted_text(extracted)
            after_struct = clean_extracted_text(extracted)
        else:
            raise ValueError(f"unsupported extension for preprocessing: {ext!r}")

        cleaned_mid = after_struct
        final = normalize_text(cleaned_mid)
        cleaned_b = len(final.encode("utf-8"))

        raw_lines = extracted.count("\n") + (1 if extracted and not extracted.endswith("\n") else 0)
        fin_lines = final.count("\n") + (1 if final and not final.endswith("\n") else 0)
        removed_lines = max(0, raw_lines - fin_lines)

        prev = self._PREVIEW
        diag = PreprocessingDiagnostics(
            extraction_success=True,
            original_format=fmt,
            original_bytes=len(raw),
            cleaned_char_len=len(final),
            extracted_char_len=len(extracted),
            removed_line_count=removed_lines,
            preview_raw=(extracted[:prev] + ("…" if len(extracted) > prev else "")) or None,
            preview_cleaned=(final[:prev] + ("…" if len(final) > prev else "")) or None,
            cleaned_size_bytes=cleaned_b,
            error=None,
            page_count=page_count,
            log_extractor_id=log_extractor_id,
        )
        return final, diag

    @staticmethod
    def failure_diag(
        *,
        original_filename: str,
        original_bytes: int,
        err: str,
        fmt: Format = "txt",
    ) -> PreprocessingDiagnostics:
        return PreprocessingDiagnostics(
            extraction_success=False,
            original_format=fmt,
            original_bytes=original_bytes,
            cleaned_char_len=0,
            extracted_char_len=0,
            removed_line_count=0,
            preview_raw=None,
            preview_cleaned=None,
            cleaned_size_bytes=0,
            error=err,
            page_count=None,
            log_extractor_id=("pdf_pymupdf" if Path(original_filename).suffix.lower() == ".pdf" else None),
        )


def run_preprocessing(raw: bytes, *, original_filename: str) -> tuple[str, PreprocessingDiagnostics]:
    """Functional entrypoint (thin wrapper)."""
    return PreprocessingService().run(raw, original_filename=original_filename)
