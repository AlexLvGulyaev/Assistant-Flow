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
        # Явный timeout/retries: зависший вызов под _VOICE_AUDIO_PIPELINE_LOCK
        # блокировал бы голос у всех пользователей (P5.4 remainder hardening).
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.openai_base_url,
            timeout=max(1, int(config.audio_timeout_seconds)),
            max_retries=max(0, int(config.audio_max_retries)),
        )
        self._model = config.tts_model
        self._voice = config.tts_voice
        self._fmt = config.tts_output_format
        self._provider = config.tts_provider or "openai"
        self._cost_per_1m_chars_usd = max(0.0, float(config.tts_cost_per_1m_chars_usd))

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
                usage=self._estimate_cost(chars=len(payload)),
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

    def _estimate_cost(self, *, chars: int) -> dict[str, Any]:
        # TTS usage API не возвращает: оценочная стоимость по числу символов
        # входного текста (cost_basis=estimated).
        if self._cost_per_1m_chars_usd <= 0:
            return {"cost_basis": "unpriced"}
        n = max(0, int(chars))
        cost = round(n * self._cost_per_1m_chars_usd / 1_000_000, 6)
        return {"cost_usd": cost, "cost_basis": "estimated", "chars": n}
