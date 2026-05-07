"""TTS provider contracts and disabled implementation (P5.4c)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TTSResult:
    ok: bool
    provider: str
    model: str
    audio_bytes: bytes | None
    content_type: str | None
    latency_ms: int | None = None
    error: str | None = None
    disabled: bool = False
    usage: dict[str, Any] | None = None


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TTSResult:
        """Synthesize text to audio bytes."""
        raise NotImplementedError


class DisabledTTSProvider(TTSProvider):
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TTSResult:
        _ = (text, voice, metadata)
        return TTSResult(
            ok=False,
            provider="disabled",
            model="disabled",
            audio_bytes=None,
            content_type=None,
            error="TTS provider is disabled by configuration",
            disabled=True,
        )
