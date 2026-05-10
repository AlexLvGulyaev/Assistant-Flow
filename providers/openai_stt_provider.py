"""OpenAI-compatible STT provider implementation (P5.4d)."""

from __future__ import annotations

import io
import time
from typing import Any

from openai import OpenAI

from providers.stt_provider import STTProvider, STTResult
from utils.config import AppConfig


class OpenAISTTProvider(STTProvider):
    """Whisper transcription via OpenAI-compatible API."""

    def __init__(self, config: AppConfig) -> None:
        api_key = (config.openai_api_key or "").strip()
        if not api_key:
            raise ValueError("OpenAI STT requires OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key, base_url=config.openai_base_url)
        self._model = config.stt_model
        self._provider = config.stt_provider or "openai"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> STTResult:
        _ = (content_type, metadata)
        if not isinstance(audio_bytes, (bytes, bytearray)) or len(audio_bytes) == 0:
            return STTResult(
                ok=False,
                transcript="",
                provider=self._provider,
                model=self._model,
                error="empty audio payload",
            )
        name = (filename or "voice_input.ogg").strip() or "voice_input.ogg"
        audio_file = io.BytesIO(bytes(audio_bytes))
        audio_file.name = name
        audio_file.seek(0)
        started = time.monotonic()
        try:
            response = self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                response_format="text",
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            transcript = str(response or "").strip()
            if not transcript:
                return STTResult(
                    ok=False,
                    transcript="",
                    provider=self._provider,
                    model=self._model,
                    latency_ms=latency_ms,
                    error="empty transcript",
                )
            return STTResult(
                ok=True,
                transcript=transcript,
                provider=self._provider,
                model=self._model,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return STTResult(
                ok=False,
                transcript="",
                provider=self._provider,
                model=self._model,
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
