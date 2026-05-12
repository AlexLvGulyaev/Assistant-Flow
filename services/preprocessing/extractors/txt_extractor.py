from __future__ import annotations

from services.preprocessing.extractors.base_extractor import BaseExtractor


class TxtExtractor(BaseExtractor):
    """UTF-8 text passthrough (decode with replacement for invalid bytes)."""

    def extract(self, raw: bytes, *, original_filename: str) -> str:
        return raw.decode("utf-8", errors="replace")
