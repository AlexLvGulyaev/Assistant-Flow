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
        # Явный timeout/retries: зависший вызов под _VOICE_AUDIO_PIPELINE_LOCK
        # блокировал бы голос у всех пользователей (P5.4 remainder hardening).
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.openai_base_url,
            timeout=max(1, int(config.audio_timeout_seconds)),
            max_retries=max(0, int(config.audio_max_retries)),
        )
        self._model = config.stt_model
        self._provider = config.stt_provider or "openai"
        self._cost_per_minute_usd = max(0.0, float(config.stt_cost_per_minute_usd))

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
            # Whisper usage не возвращает: оценочная стоимость по длительности
            # аудио (metadata["duration_sec"], fallback — длительность звонка
            # latency по цене $/мин). cost_basis=estimated.
            usage = self._estimate_cost(
                duration_sec=metadata.get("duration_sec") if isinstance(metadata, dict) else None,
                fallback_duration_sec=(latency_ms / 1000.0),
            )
            return STTResult(
                ok=True,
                transcript=transcript,
                provider=self._provider,
                model=self._model,
                latency_ms=latency_ms,
                usage=usage,
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

    def _estimate_cost(
        self, *, duration_sec: Any, fallback_duration_sec: float
    ) -> dict[str, Any]:
        if self._cost_per_minute_usd <= 0:
            return {"cost_basis": "unpriced"}
        try:
            dur = float(duration_sec) if duration_sec is not None else None
        except (TypeError, ValueError):
            dur = None
        if dur is None or dur <= 0:
            dur = max(0.0, float(fallback_duration_sec))
        # Минимальная биллинговая единица whisper — 1 секунда; округляем вверх.
        billed_seconds = max(1.0, float(dur))
        cost = round((billed_seconds / 60.0) * self._cost_per_minute_usd, 6)
        return {
            "cost_usd": cost,
            "cost_basis": "estimated",
            "duration_sec": round(dur, 3),
        }
