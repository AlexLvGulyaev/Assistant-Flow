"""STT provider contracts and disabled implementation (P5.4c)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class STTResult:
    ok: bool
    transcript: str
    provider: str
    model: str
    latency_ms: int | None = None
    error: str | None = None
    disabled: bool = False
    usage: dict[str, Any] | None = None


class STTProvider(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> STTResult:
        """Transcribe audio bytes into text."""
        raise NotImplementedError


class DisabledSTTProvider(STTProvider):
    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> STTResult:
        _ = (audio_bytes, filename, content_type, metadata)
        return STTResult(
            ok=False,
            transcript="",
            provider="disabled",
            model="disabled",
            error="STT provider is disabled by configuration",
            disabled=True,
        )
