"""OpenAI-compatible TTS provider implementation (P5.4e)."""

from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from providers.tts_provider import TTSProvider, TTSResult
from utils.config import AppConfig


class OpenAITTSProvider(TTSProvider):
    """Text-to-speech via OpenAI-compatible API."""

    def __init__(self, config: AppConfig) -> None:
        api_key = (config.openai_api_key or "").strip()
        if not api_key:
            raise ValueError("OpenAI TTS requires OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key, base_url=config.openai_base_url)
        self._model = config.tts_model
        self._voice = config.tts_voice
        self._fmt = config.tts_output_format
        self._provider = config.tts_provider or "openai"

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TTSResult:
        _ = metadata
        payload = (text or "").strip()
        if not payload:
            return TTSResult(
                ok=False,
                provider=self._provider,
                model=self._model,
                audio_bytes=None,
                content_type=None,
                error="empty input text",
            )
        started = time.monotonic()
        v = (voice or self._voice or "alloy").strip() or "alloy"
        try:
            response = self._client.audio.speech.create(
                model=self._model,
                voice=v,
                input=payload,
                response_format=self._fmt,
            )
            data = response.read()
            latency_ms = int((time.monotonic() - started) * 1000)
            if not data:
                return TTSResult(
                    ok=False,
                    provider=self._provider,
                    model=self._model,
                    audio_bytes=None,
                    content_type=None,
                    latency_ms=latency_ms,
                    error="empty tts audio",
                )
            mime = {
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "opus": "audio/opus",
                "aac": "audio/aac",
                "flac": "audio/flac",
                "pcm": "audio/L16",
            }.get(self._fmt.lower(), "application/octet-stream")
            return TTSResult(
                ok=True,
                provider=self._provider,
                model=self._model,
                audio_bytes=data,
                content_type=mime,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return TTSResult(
                ok=False,
                provider=self._provider,
                model=self._model,
                audio_bytes=None,
                content_type=None,
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
