from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """Extract readable text from raw bytes (encoding-safe)."""

    @abstractmethod
    def extract(self, raw: bytes, *, original_filename: str) -> str:
        raise NotImplementedError
