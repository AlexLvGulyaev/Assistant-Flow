from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from services.preprocessing.cleaners.html_cleaner import clean_html_extracted_text
from services.preprocessing.cleaners.text_cleaner import clean_extracted_text
from services.preprocessing.extractors.html_extractor import HtmlExtractor
from services.preprocessing.extractors.txt_extractor import TxtExtractor
from services.preprocessing.normalizers.text_normalizer import normalize_text


Format = Literal["txt", "html"]


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
    error: str | None = None

    def to_log_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": "ok" if self.extraction_success else "error",
            "extraction_success": self.extraction_success,
            "original_format": self.original_format,
            "original_bytes": int(self.original_bytes),
            "cleaned_char_len": int(self.cleaned_char_len),
            "extracted_char_len": int(self.extracted_char_len),
            "removed_line_count": int(self.removed_line_count),
        }
        if self.preview_raw:
            out["preview_raw"] = self.preview_raw
        if self.preview_cleaned:
            out["preview_cleaned"] = self.preview_cleaned
        if self.error:
            out["error"] = self.error
        return out


class PreprocessingService:
    """Phase-1 preprocessing: txt passthrough, html via BeautifulSoup + cleaners."""

    _PREVIEW = 480

    def run(self, raw: bytes, *, original_filename: str) -> tuple[str, PreprocessingDiagnostics]:
        if not isinstance(raw, (bytes, bytearray)) or len(raw) == 0:
            raise ValueError("empty payload")
        safe = Path(original_filename).name
        ext = Path(safe).suffix.lower()
        if ext == ".txt":
            fmt: Format = "txt"
            extracted = TxtExtractor().extract(raw, original_filename=safe)
            after_struct = clean_extracted_text(extracted)
        elif ext in (".html", ".htm"):
            fmt = "html"
            extracted = HtmlExtractor().extract(raw, original_filename=safe)
            after_struct = clean_html_extracted_text(extracted)
        else:
            raise ValueError(f"unsupported extension for preprocessing: {ext!r}")

        cleaned_mid = after_struct
        final = normalize_text(cleaned_mid)

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
            error=None,
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
            error=err,
        )


def run_preprocessing(raw: bytes, *, original_filename: str) -> tuple[str, PreprocessingDiagnostics]:
    """Functional entrypoint (thin wrapper)."""
    return PreprocessingService().run(raw, original_filename=original_filename)
