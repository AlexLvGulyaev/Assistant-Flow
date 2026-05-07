"""Audio pipeline foundation with AssetRepository integration (P5.4c)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.asset_repository import AssetRef, AssetRepository
from services.asset_repository_factory import create_asset_repository
from utils.config import AppConfig, load_config


@dataclass(frozen=True)
class AudioAsset:
    """Stored audio asset descriptor."""

    kind: str  # input | output
    namespace: str
    asset_ref: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class AudioTranscriptionResult:
    """Normalized STT result shape for future provider integrations."""

    ok: bool
    transcript: str
    provider: str
    model: str
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    disabled: bool = False


@dataclass(frozen=True)
class AudioSynthesisResult:
    """Normalized TTS result shape for future provider integrations."""

    ok: bool
    provider: str
    model: str
    generated_text: str
    audio_bytes: bytes | None = None
    content_type: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    disabled: bool = False


class AudioPipelineService:
    """Asset-first audio utility service (no runtime side effects)."""

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        self._config = config or load_config()
        self._repo = asset_repository or create_asset_repository(self._config)

    @property
    def input_namespace(self) -> str:
        return f"{self._config.audio_storage_namespace}/input"

    @property
    def output_namespace(self) -> str:
        return f"{self._config.audio_storage_namespace}/output"

    def save_input_audio(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AudioAsset:
        ref = self._repo.save_bytes(
            data,
            namespace=self.input_namespace,
            filename=filename or "audio_input.bin",
            content_type=content_type or "application/octet-stream",
        )
        return self._to_audio_asset(ref, kind="input")

    def save_output_audio(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AudioAsset:
        ref = self._repo.save_bytes(
            data,
            namespace=self.output_namespace,
            filename=filename or "audio_output.bin",
            content_type=content_type or "application/octet-stream",
        )
        return self._to_audio_asset(ref, kind="output")

    def build_audio_event_details(
        self,
        *,
        input_asset: AudioAsset | None = None,
        output_asset: AudioAsset | None = None,
        transcription: AudioTranscriptionResult | None = None,
        synthesis: AudioSynthesisResult | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details: dict[str, Any] = self.normalize_audio_metadata(metadata)
        if input_asset is not None:
            details["input_audio"] = self._asset_dict(input_asset)
        if output_asset is not None:
            details["output_audio"] = self._asset_dict(output_asset)
        if transcription is not None:
            details["stt"] = {
                "ok": transcription.ok,
                "disabled": transcription.disabled,
                "provider": transcription.provider,
                "model": transcription.model,
                "transcript": transcription.transcript,
                "latency_ms": transcription.latency_ms,
                "input_tokens": transcription.input_tokens,
                "output_tokens": transcription.output_tokens,
                "total_tokens": transcription.total_tokens,
                "cost_usd": transcription.cost_usd,
                "error": transcription.error,
            }
        if synthesis is not None:
            details["tts"] = {
                "ok": synthesis.ok,
                "disabled": synthesis.disabled,
                "provider": synthesis.provider,
                "model": synthesis.model,
                "generated_text": synthesis.generated_text,
                "content_type": synthesis.content_type,
                "latency_ms": synthesis.latency_ms,
                "input_tokens": synthesis.input_tokens,
                "output_tokens": synthesis.output_tokens,
                "total_tokens": synthesis.total_tokens,
                "cost_usd": synthesis.cost_usd,
                "error": synthesis.error,
            }
        return details

    def normalize_audio_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        src = metadata or {}
        out: dict[str, Any] = {}
        if not isinstance(src, dict):
            return out
        allowed = (
            "filename",
            "duration_sec",
            "mime_type",
            "sample_rate",
            "channels",
            "size_bytes",
            "provider",
            "model",
            "created_at",
            "mode",
            "route",
            "input_type",
            "output_type",
        )
        for key in allowed:
            val = src.get(key)
            if val is not None:
                out[key] = val
        return out

    def resolve_audio_asset_path(
        self,
        *,
        asset_ref: str | None = None,
        raw_path: str | None = None,
    ) -> Path | None:
        if asset_ref and str(asset_ref).strip():
            try:
                p = self._repo.resolve_path(str(asset_ref).strip())
                if p.is_file():
                    return p
            except Exception:
                pass
        if raw_path and str(raw_path).strip():
            try:
                p = Path(str(raw_path).strip())
                if p.is_file():
                    return p
            except Exception:
                pass
        return None

    def _to_audio_asset(self, ref: AssetRef, *, kind: str) -> AudioAsset:
        return AudioAsset(
            kind=kind,
            namespace=ref.namespace,
            asset_ref=ref.relative_path,
            filename=ref.filename,
            content_type=ref.content_type,
            size_bytes=ref.size_bytes,
            sha256=ref.sha256,
        )

    @staticmethod
    def _asset_dict(asset: AudioAsset) -> dict[str, Any]:
        return {
            "kind": asset.kind,
            "namespace": asset.namespace,
            "asset_ref": asset.asset_ref,
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
        }
