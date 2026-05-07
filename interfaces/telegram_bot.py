import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import telebot

from core.orchestrator import PromptOrchestrator, build_output_image_records
from providers.gigachat_provider import GigaChatProvider
from providers.openai_stt_provider import OpenAISTTProvider
from providers.openai_tts_provider import OpenAITTSProvider
from providers.openai_chat_provider import OpenAIChatProvider
from providers.rag_embeddings import build_openai_embeddings
from providers.stt_provider import DisabledSTTProvider, STTProvider
from providers.tts_provider import DisabledTTSProvider, TTSProvider
from services.audio_pipeline_service import (
    AudioPipelineService,
    AudioSynthesisResult,
    AudioTranscriptionResult,
)
from services.gigachat_service import GigaChatService
from services.image_generation_service import ImageGenerationService
from services.asset_repository_factory import create_asset_repository
from services.rag_chroma_store import ChromaRagStore, count_chroma_chunks
from services.rag_query_service import RagQueryService
from services.rag_types import RagQueryResult
from services.runtime_lifecycle_service import RuntimeLifecycleService
from utils.config import AppConfig, load_config
from utils.request_logger import RequestLogger
from utils.telegram_formatter import format_for_telegram
from utils.telegram_user_state import InMemoryTelegramUserStore, Mode

_KNOWN_COMMAND_PREFIXES = frozenset(
    {"/start", "/help", "/mode", "/stats", "/reset"}
)


def _is_unknown_slash_command(message: telebot.types.Message) -> bool:
    if message.content_type != "text" or not message.text or not message.text.startswith("/"):
        return False
    cmd = message.text.split(maxsplit=1)[0].split("@", 1)[0].lower()
    return cmd not in _KNOWN_COMMAND_PREFIXES


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_project_path(config: AppConfig, relative_or_abs: str) -> Path:
    p = Path(relative_or_abs)
    return p if p.is_absolute() else _project_root() / p


def send_long_message(bot: telebot.TeleBot, chat_id: int, text: str, max_len: int = 3500) -> None:
    remaining = (text or "").strip()
    if not remaining:
        bot.send_message(chat_id, "Пустой ответ от сервиса.")
        return

    while remaining:
        if len(remaining) <= max_len:
            bot.send_message(chat_id, remaining)
            break

        chunk = remaining[:max_len]
        split_pos = chunk.rfind("\n\n")
        if split_pos == -1:
            split_pos = chunk.rfind("\n")
        if split_pos == -1:
            split_pos = max_len

        part = remaining[:split_pos].strip()
        if not part:
            part = remaining[:max_len].strip()
            split_pos = max_len

        bot.send_message(chat_id, part)
        remaining = remaining[split_pos:].strip()


def build_orchestrator() -> PromptOrchestrator:
    config = load_config()
    request_logger = RequestLogger(config.logs_db_path)
    gigachat_service = GigaChatService(config=config, request_logger=request_logger)
    gigachat_provider = GigaChatProvider(service=gigachat_service)
    image_generation_service = ImageGenerationService(
        config=config,
        request_logger=request_logger,
    )
    return PromptOrchestrator(
        gigachat_provider=gigachat_provider,
        request_logger=request_logger,
        model_name=config.gigachat_model,
        image_generation_service=image_generation_service,
    )


def build_rag_query_service(config: AppConfig) -> RagQueryService:
    chroma_dir = _resolve_project_path(config, config.chroma_persist_dir)
    embeddings = build_openai_embeddings(config)
    store = ChromaRagStore(
        config,
        embeddings,
        persist_directory=chroma_dir,
    )
    chat = OpenAIChatProvider(config)
    return RagQueryService(store, chat, config)


def _log_system_degraded(
    lifecycle: RuntimeLifecycleService,
    *,
    component: str,
    reason: str,
    message: str | None = None,
) -> None:
    """Best-effort processing_logs row when startup is degraded (requires PostgreSQL)."""
    lifecycle.log_processing_event(
        execution_id=f"system-{uuid.uuid4()}",
        intake_event_id=None,
        stage="system_degraded",
        status="error",
        details={"component": component, "reason": reason},
        error_text=(message or "")[:4000] or None,
    )


def _try_build_rag_query_service(
    config: AppConfig,
    *,
    lifecycle: RuntimeLifecycleService,
    log_to_db: bool,
) -> tuple[RagQueryService | None, str | None]:
    """
    Build RAG service without crashing the process. On failure optionally logs system_degraded.
    """
    try:
        svc = build_rag_query_service(config)
        print("[assistant-flow] RAG service ready", flush=True)
        return svc, None
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        print(f"[assistant-flow] startup degraded: rag unavailable ({msg})", flush=True)
        low = msg.lower()
        if config.chroma_use_http and any(
            x in low
            for x in (
                "connection",
                "refused",
                "timeout",
                "chroma",
                "unreachable",
                "failed to connect",
                "errno",
            )
        ):
            print("[assistant-flow] startup degraded: chroma unavailable", flush=True)
        if log_to_db:
            if any(
                x in low
                for x in (
                    "chroma",
                    "chromadb",
                    "connection",
                    "refused",
                    "unreachable",
                    "timeout",
                    "failed to connect",
                )
            ):
                comp = "chroma"
            else:
                comp = "rag"
            _log_system_degraded(
                lifecycle,
                component=comp,
                reason="init_failed",
                message=msg,
            )
        return None, msg


def _format_rag_telegram_reply(result: RagQueryResult) -> str:
    # User-facing Telegram response must stay clean (no technical diagnostics).
    return (result.answer or "").strip()


def _safe_answer_text_for_log(text: str, max_len: int = 3000) -> str:
    """
    Keep answer text compact for processing_logs.
    - maximum length: ``max_len`` (+ "..." suffix if trimmed)
    - basic secret-pattern redaction
    """
    t = (text or "").strip()
    if not t:
        return ""
    lower = t.lower()
    if "sk-" in lower or "api_key" in lower or "openai_api_key" in lower:
        return "[answer redacted: possible secret pattern]"
    if len(t) <= max_len:
        return t
    return t[:max_len] + "..."


def _safe_query_preview_for_log(text: str, max_len: int = 200) -> str:
    """Compact safe preview for user prompt in processing_logs."""
    t = " ".join((text or "").strip().split())
    if not t:
        return ""
    lower = t.lower()
    if "sk-" in lower or "api_key" in lower or "openai_api_key" in lower:
        return "[preview redacted: possible secret pattern]"
    if len(t) <= max_len:
        return t
    return t[:max_len] + "..."


def _guess_audio_filename(file_path: str | None, content_type: str | None) -> str:
    p = str(file_path or "").strip()
    if p:
        name = Path(p).name
        if "." in name:
            return name
    c = (content_type or "").lower()
    if "ogg" in c or "opus" in c:
        return "voice_input.ogg"
    if "mpeg" in c or "mp3" in c:
        return "voice_input.mp3"
    if "wav" in c:
        return "voice_input.wav"
    if "m4a" in c or "mp4" in c:
        return "voice_input.m4a"
    return "voice_input.bin"


def build_stt_provider(config: AppConfig) -> tuple[STTProvider, str | None]:
    if not config.audio_enabled:
        return DisabledSTTProvider(), "audio pipeline is disabled by AUDIO_ENABLED=false"
    raw = (config.stt_provider or "").strip().lower()
    if raw in ("", "disabled", "none", "off"):
        return DisabledSTTProvider(), None
    if raw in ("openai", "openai_direct"):
        try:
            return OpenAISTTProvider(config), None
        except Exception as exc:
            return DisabledSTTProvider(), f"stt provider init failed: {type(exc).__name__}: {exc}"
    return DisabledSTTProvider(), f"unsupported stt provider: {raw}"


def build_tts_provider(config: AppConfig) -> tuple[TTSProvider, str | None]:
    if not config.audio_enabled:
        return DisabledTTSProvider(), "audio pipeline is disabled by AUDIO_ENABLED=false"
    raw = (config.tts_provider or "").strip().lower()
    if raw in ("", "disabled", "none", "off"):
        return DisabledTTSProvider(), None
    if raw in ("openai", "openai_direct"):
        try:
            return OpenAITTSProvider(config), None
        except Exception as exc:
            return DisabledTTSProvider(), f"tts provider init failed: {type(exc).__name__}: {exc}"
    return DisabledTTSProvider(), f"unsupported tts provider: {raw}"


def create_bot() -> telebot.TeleBot:
    config = load_config()
    if not config.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    bot = telebot.TeleBot(config.telegram_bot_token)
    orchestrator = build_orchestrator()
    asset_repository = create_asset_repository(config)
    audio_pipeline = AudioPipelineService(
        config=config,
        asset_repository=asset_repository,
    )
    stt_provider, stt_provider_init_error = build_stt_provider(config)
    tts_provider, tts_provider_init_error = build_tts_provider(config)
    if stt_provider_init_error:
        print(f"[assistant-flow] startup degraded: {stt_provider_init_error}", flush=True)
    if tts_provider_init_error:
        print(f"[assistant-flow] startup degraded: {tts_provider_init_error}", flush=True)
    _chroma_path = _resolve_project_path(config, config.chroma_persist_dir)
    if config.chroma_use_http:
        print(
            "[assistant-flow] RAG (Chroma HTTP)",
            f"{config.chroma_host}:{config.chroma_port}",
            f"(local path hint: {_chroma_path})",
            flush=True,
        )
    else:
        print(
            "[assistant-flow] RAG (Chroma local persist)",
            _chroma_path,
            flush=True,
        )
    user_store = InMemoryTelegramUserStore()
    lifecycle = RuntimeLifecycleService()
    if stt_provider_init_error:
        _log_system_degraded(
            lifecycle=lifecycle,
            component="stt",
            reason="provider_init_failed",
            message=stt_provider_init_error,
        )
    if tts_provider_init_error:
        _log_system_degraded(
            lifecycle=lifecycle,
            component="tts",
            reason="provider_init_failed",
            message=tts_provider_init_error,
        )

    rag_holder: dict[str, Any] = {"service": None, "last_error": None}

    def try_init_rag(*, log_to_db: bool) -> RagQueryService | None:
        svc, err = _try_build_rag_query_service(
            config, lifecycle=lifecycle, log_to_db=log_to_db
        )
        rag_holder["service"] = svc
        rag_holder["last_error"] = err
        return svc

    try_init_rag(log_to_db=True)

    chroma_display = _resolve_project_path(config, config.chroma_persist_dir)
    docs_display = _resolve_project_path(config, config.rag_documents_dir)

    @bot.message_handler(commands=["start"])
    def handle_start(message: telebot.types.Message) -> None:
        try:
            bot.send_message(
                message.chat.id,
                "Я карьерный мультимодальный ассистент.\n"
                "Могу:\n"
                "- отвечать на вопросы (режим текста, GigaChat)\n"
                "- отвечать по базе знаний (режим RAG, нужен проиндексированный Chroma)\n"
                "- генерировать изображения по запросу (в текстовом режиме)\n\n"
                "Команды: /help, /mode, /stats, /reset",
            )
        except Exception:
            traceback.print_exc()
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(commands=["help"])
    def handle_help(message: telebot.types.Message) -> None:
        try:
            bot.send_message(
                message.chat.id,
                "Режимы:\n"
                "/mode text — обычный диалог и генерация картинок по ключевым словам\n"
                "/mode rag — вопросы по документам в Chroma (индекс через CLI)\n\n"
                "/stats — статистика индекса RAG\n"
                "/reset — сброс в текстовый режим и очистка истории RAG\n\n"
                "Примеры (текст):\n"
                "• Объясни простыми словами, как работает фотосинтез\n"
                "• Нарисуй футуристический город на закате\n\n"
                "В режиме RAG задавайте вопросы по уже проиндексированной базе.",
            )
        except Exception:
            traceback.print_exc()
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(commands=["mode"])
    def handle_mode(message: telebot.types.Message) -> None:
        try:
            uid = message.from_user.id
            parts = (message.text or "").split(maxsplit=1)
            if len(parts) < 2:
                current = user_store.get_mode(uid)
                bot.send_message(
                    message.chat.id,
                    f"Текущий режим: {current}\n\n"
                    "Доступно:\n"
                    "/mode text — обычный режим (GigaChat + картинки)\n"
                    "/mode rag — ответы по RAG / Chroma\n\n"
                    "TODO: сохранение режима в PostgreSQL (chat_sessions).",
                )
                return
            arg = parts[1].strip().lower()
            if arg not in ("text", "rag"):
                bot.send_message(
                    message.chat.id,
                    "Неизвестный режим. Используйте: /mode text или /mode rag",
                )
                return
            user_store.set_mode(uid, arg)
            labels = {
                "text": "Текстовый режим: GigaChat и генерация изображений.",
                "rag": "Режим RAG: ответы по проиндексированной базе (см. /stats).",
            }
            bot.send_message(message.chat.id, f"Режим: {arg}\n{labels[arg]}")
        except Exception:
            traceback.print_exc()
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(commands=["stats"])
    def handle_stats(message: telebot.types.Message) -> None:
        try:
            n = count_chroma_chunks(config, persist_path=chroma_display)
            if config.chroma_use_http:
                backend_line = (
                    f"Chroma backend: HTTP {config.chroma_host}:{config.chroma_port}\n"
                    f"(локальный каталог в .env — только подсказка: {chroma_display})\n"
                )
            else:
                backend_line = f"Каталог Chroma (persist):\n{chroma_display}\n"
            text = (
                "Статистика RAG (read-only):\n\n"
                f"Чанков в Chroma: {n}\n"
                f"{backend_line}"
                f"Каталог документов (источник для индексации):\n{docs_display}\n\n"
                "Индексация: docs/RAG_SMOKE_TEST.md, scripts/rag_smoke_test.py"
            )
            bot.send_message(message.chat.id, text)
        except BaseException as exc:
            print("[assistant-flow] /stats failed", flush=True)
            print(type(exc), exc, flush=True)
            traceback.print_exc()
            try:
                bot.send_message(
                    message.chat.id,
                    "Не удалось получить статистику базы знаний. Подробности выведены в консоль.",
                )
            except BaseException as send_exc:
                print(
                    "[assistant-flow] /stats: could not send fallback message to user",
                    flush=True,
                )
                print(type(send_exc), send_exc, flush=True)
                traceback.print_exc()

    @bot.message_handler(commands=["reset"])
    def handle_reset(message: telebot.types.Message) -> None:
        try:
            user_store.reset(message.from_user.id)
            bot.send_message(
                message.chat.id,
                "Сброшено: режим text, история RAG очищена.\n"
                "(TODO: синхронизация с PostgreSQL chat_sessions.)",
            )
        except Exception:
            traceback.print_exc()
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=_is_unknown_slash_command)
    def handle_unknown_command(message: telebot.types.Message) -> None:
        try:
            bot.send_message(message.chat.id, "Неизвестная команда. См. /help")
        except Exception:
            traceback.print_exc()

    @bot.message_handler(content_types=["voice"])
    def handle_voice(message: telebot.types.Message) -> None:
        execution_id = str(uuid.uuid4())
        intake_id: uuid.UUID | None = None
        try:
            voice = message.voice
            if voice is None or not getattr(voice, "file_id", None):
                bot.send_message(message.chat.id, "Голосовое сообщение не распознано.")
                return

            mime_type = str(getattr(voice, "mime_type", "") or "audio/ogg").strip()
            duration_sec = int(getattr(voice, "duration", 0) or 0)
            declared_size = int(getattr(voice, "file_size", 0) or 0)
            intake_id = lifecycle.create_intake_event(
                execution_id=execution_id,
                telegram_chat_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                text_preview="[voice]",
                original_char_length=0,
            )
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="intake_received",
                status="success" if intake_id else "error",
                details={
                    "mode": "voice",
                    "route": "voice",
                    "input_type": "voice",
                    "duration_sec": duration_sec,
                    "mime_type": mime_type,
                    "size_bytes": declared_size,
                },
                error_text=None if intake_id else "intake_events insert failed",
            )

            if declared_size > max(1, int(config.audio_max_bytes)):
                err = f"audio too large: {declared_size} > {config.audio_max_bytes}"
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="voice_processing_error",
                    status="error",
                    details={
                        "mode": "voice",
                        "route": "voice",
                        "input_type": "voice",
                        "size_bytes": declared_size,
                        "audio_max_bytes": int(config.audio_max_bytes),
                    },
                    error_text=err,
                )
                bot.send_message(
                    message.chat.id,
                    "Голосовое сообщение слишком большое. Попробуйте файл меньшего размера.",
                )
                return

            file_info = bot.get_file(voice.file_id)
            raw_bytes = bot.download_file(file_info.file_path)
            size_bytes = len(raw_bytes)
            if size_bytes > max(1, int(config.audio_max_bytes)):
                err = f"audio too large after download: {size_bytes} > {config.audio_max_bytes}"
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="voice_processing_error",
                    status="error",
                    details={
                        "mode": "voice",
                        "route": "voice",
                        "input_type": "voice",
                        "size_bytes": size_bytes,
                        "audio_max_bytes": int(config.audio_max_bytes),
                    },
                    error_text=err,
                )
                bot.send_message(
                    message.chat.id,
                    "Голосовое сообщение слишком большое. Попробуйте файл меньшего размера.",
                )
                return

            filename = _guess_audio_filename(file_info.file_path, mime_type)
            input_asset = audio_pipeline.save_input_audio(
                raw_bytes,
                filename=filename,
                content_type=mime_type,
            )
            input_path = audio_pipeline.resolve_audio_asset_path(asset_ref=input_asset.asset_ref)
            stt_start_ts = time.monotonic()
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="stt_started",
                status="started",
                details={
                    "mode": "voice",
                    "route": "voice",
                    "input_type": "voice",
                    "filename": input_asset.filename,
                    "mime_type": input_asset.content_type,
                    "duration_sec": duration_sec,
                    "size_bytes": input_asset.size_bytes,
                    "asset_ref": input_asset.asset_ref,
                    "audio_path": str(input_path) if input_path else None,
                    "provider": config.stt_provider,
                    "model": config.stt_model,
                },
            )

            stt_result = stt_provider.transcribe(
                raw_bytes,
                filename=input_asset.filename,
                content_type=input_asset.content_type,
                metadata={
                    "execution_id": execution_id,
                    "telegram_chat_id": message.chat.id,
                    "telegram_user_id": message.from_user.id,
                },
            )
            stt_latency_ms = stt_result.latency_ms
            if stt_latency_ms is None:
                stt_latency_ms = int((time.monotonic() - stt_start_ts) * 1000)
            stt_norm = AudioTranscriptionResult(
                ok=stt_result.ok,
                transcript=stt_result.transcript,
                provider=stt_result.provider,
                model=stt_result.model,
                latency_ms=stt_latency_ms,
                error=stt_result.error,
                disabled=stt_result.disabled,
                input_tokens=(
                    int(stt_result.usage.get("input_tokens"))
                    if isinstance(stt_result.usage, dict)
                    and stt_result.usage.get("input_tokens") is not None
                    else None
                ),
                output_tokens=(
                    int(stt_result.usage.get("output_tokens"))
                    if isinstance(stt_result.usage, dict)
                    and stt_result.usage.get("output_tokens") is not None
                    else None
                ),
                total_tokens=(
                    int(stt_result.usage.get("total_tokens"))
                    if isinstance(stt_result.usage, dict)
                    and stt_result.usage.get("total_tokens") is not None
                    else None
                ),
                cost_usd=(
                    float(stt_result.usage.get("cost_usd"))
                    if isinstance(stt_result.usage, dict)
                    and stt_result.usage.get("cost_usd") is not None
                    else None
                ),
            )
            stt_details = audio_pipeline.build_audio_event_details(
                input_asset=input_asset,
                transcription=stt_norm,
                metadata={
                    "mode": "voice",
                    "route": "voice",
                    "input_type": "voice",
                    "filename": input_asset.filename,
                    "mime_type": input_asset.content_type,
                    "duration_sec": duration_sec,
                    "size_bytes": input_asset.size_bytes,
                    "audio_path": str(input_path) if input_path else None,
                },
            )
            stt_details["transcript"] = stt_norm.transcript
            stt_details["asset_ref"] = input_asset.asset_ref
            stt_details["audio_path"] = str(input_path) if input_path else None
            stt_details["provider"] = stt_norm.provider
            stt_details["model"] = stt_norm.model
            stt_details["latency_ms"] = stt_norm.latency_ms
            stt_details["size_bytes"] = input_asset.size_bytes
            stt_details["mime_type"] = input_asset.content_type
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="stt_completed",
                status="success" if stt_norm.ok else "error",
                details=stt_details,
                error_text=(stt_norm.error or None),
            )

            if not stt_norm.ok:
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="voice_processing_error",
                    status="error",
                    details=stt_details,
                    error_text=stt_norm.error,
                )
                if stt_norm.disabled:
                    bot.send_message(
                        message.chat.id,
                        "Распознавание голоса временно отключено.",
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        "Не удалось распознать голосовое сообщение. Попробуйте позже.",
                    )
                return

            transcript = (stt_norm.transcript or "").strip()
            if not transcript:
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="voice_processing_error",
                    status="error",
                    details=stt_details,
                    error_text="empty transcript",
                )
                bot.send_message(
                    message.chat.id,
                    "Не удалось распознать голосовое сообщение. Попробуйте позже.",
                )
                return

            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="route_selected",
                status="success",
                details={
                    "mode": "voice",
                    "route": "voice",
                    "query_preview": _safe_query_preview_for_log(transcript, max_len=200),
                    "transcript": transcript,
                    "asset_ref": input_asset.asset_ref,
                    "audio_path": str(input_path) if input_path else None,
                },
            )

            is_image_request = orchestrator.route_request(transcript) == "image_generation"
            if is_image_request:
                bot.send_message(
                    message.chat.id,
                    "Распознал голос. Генерирую изображение по запросу… ⏳",
                )
            start_ts = time.monotonic()
            result = orchestrator.process_text(
                transcript,
                execution_id=execution_id,
                intake_event_id=intake_id,
                lifecycle=lifecycle,
            )
            usage = orchestrator.get_last_text_usage_snapshot()
            model_snapshot = orchestrator.get_last_text_model_snapshot()
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            result_text = str(result)
            is_image_path = (
                "outputs" in result_text.lower()
                or "/storage/" in result_text.lower()
                or result_text.lower().endswith(".png")
                or result_text.lower().endswith(".jpg")
                or result_text.lower().endswith(".jpeg")
            )

            voice_base_details: dict[str, Any] = {
                "mode": "voice",
                "route": "voice",
                "input_type": "voice",
                "transcript": transcript,
                "query_preview": _safe_query_preview_for_log(transcript, max_len=200),
                "asset_ref": input_asset.asset_ref,
                "audio_path": str(input_path) if input_path else None,
                "filename": input_asset.filename,
                "mime_type": input_asset.content_type,
                "size_bytes": input_asset.size_bytes,
                "provider": stt_norm.provider,
                "model": stt_norm.model,
                "latency_ms": stt_norm.latency_ms,
            }

            if is_image_path:
                try:
                    img_snap = orchestrator.get_last_image_generation_snapshot()
                    asset_ref = str(img_snap.get("asset_ref") or "").strip()
                    resolved_path: Path | None = None
                    if asset_ref:
                        try:
                            p_candidate = asset_repository.resolve_path(asset_ref)
                            if p_candidate.is_file():
                                resolved_path = p_candidate
                        except Exception:
                            resolved_path = None
                    if resolved_path is None:
                        p_legacy = Path(result_text)
                        if p_legacy.is_file():
                            resolved_path = p_legacy
                    if resolved_path is None:
                        raise FileNotFoundError(
                            "image file is missing for both asset_ref and image_path"
                        )
                    with resolved_path.open("rb") as image_file:
                        bot.send_photo(message.chat.id, image_file)
                    details_done: dict[str, Any] = {
                        **voice_base_details,
                        "route": "image_generation",
                        "generation_completed": True,
                        "output_images": build_output_image_records(
                            str(resolved_path),
                            provider_url=str(img_snap.get("provider_url") or "") or None,
                            provider=str(img_snap.get("provider") or "") or None,
                            model=str(img_snap.get("model") or "") or None,
                        ),
                        "latency_ms": latency_ms,
                    }
                    for key in ("input_tokens", "output_tokens", "total_tokens"):
                        if key in usage:
                            details_done[key] = usage[key]
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="processing_done",
                        status="success",
                        details=details_done,
                    )
                except Exception as send_exc:
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="voice_processing_error",
                        status="error",
                        details=voice_base_details,
                        error_text=str(send_exc),
                    )
                    bot.send_message(
                        message.chat.id,
                        "Не удалось обработать голосовой запрос. Попробуйте позже.",
                    )
                    return
            else:
                formatted_result = format_for_telegram(result_text)
                send_long_message(bot, message.chat.id, formatted_result)
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="text_answer_done",
                    status="success",
                    details={
                        **voice_base_details,
                        "route": "text_response",
                        "answer_text": _safe_answer_text_for_log(
                            formatted_result, max_len=3000
                        ),
                        "answer_preview": _safe_answer_text_for_log(
                            formatted_result, max_len=300
                        ),
                        "provider": "gigachat",
                        "model": model_snapshot or config.gigachat_model,
                        **(
                            {"input_tokens": usage["input_tokens"]}
                            if "input_tokens" in usage
                            else {}
                        ),
                        **(
                            {"output_tokens": usage["output_tokens"]}
                            if "output_tokens" in usage
                            else {}
                        ),
                        **(
                            {"total_tokens": usage["total_tokens"]}
                            if "total_tokens" in usage
                            else {}
                        ),
                        "latency_ms": latency_ms,
                    },
                )
                tts_stage_base: dict[str, Any] = {
                    **voice_base_details,
                    "generated_text": _safe_answer_text_for_log(
                        formatted_result, max_len=3000
                    ),
                    "provider": config.tts_provider,
                    "model": config.tts_model,
                    "voice": config.tts_voice,
                    "format": config.tts_output_format,
                }
                if isinstance(tts_provider, DisabledTTSProvider):
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="tts_skipped",
                        status="skipped",
                        details={**tts_stage_base, "reason": "provider_disabled"},
                    )
                elif len(formatted_result) > max(1, int(config.tts_max_chars)):
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="tts_skipped",
                        status="skipped",
                        details={
                            **tts_stage_base,
                            "reason": "text_too_long",
                            "text_chars": len(formatted_result),
                            "tts_max_chars": int(config.tts_max_chars),
                        },
                    )
                else:
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="tts_started",
                        status="started",
                        details=tts_stage_base,
                    )
                    tts_result = tts_provider.synthesize(
                        formatted_result,
                        voice=config.tts_voice,
                        metadata={
                            "execution_id": execution_id,
                            "telegram_chat_id": message.chat.id,
                            "telegram_user_id": message.from_user.id,
                        },
                    )
                    if (
                        tts_result.ok
                        and isinstance(tts_result.audio_bytes, (bytes, bytearray))
                        and len(tts_result.audio_bytes) > 0
                    ):
                        out_filename = f"tts_response.{config.tts_output_format}"
                        out_asset = audio_pipeline.save_output_audio(
                            bytes(tts_result.audio_bytes),
                            filename=out_filename,
                            content_type=tts_result.content_type or "audio/mpeg",
                        )
                        out_path = audio_pipeline.resolve_audio_asset_path(
                            asset_ref=out_asset.asset_ref
                        )
                        tts_norm = AudioSynthesisResult(
                            ok=True,
                            provider=tts_result.provider,
                            model=tts_result.model,
                            generated_text=formatted_result,
                            audio_bytes=tts_result.audio_bytes,
                            content_type=tts_result.content_type,
                            latency_ms=tts_result.latency_ms,
                        )
                        tts_details = audio_pipeline.build_audio_event_details(
                            input_asset=input_asset,
                            output_asset=out_asset,
                            synthesis=tts_norm,
                            metadata={
                                **voice_base_details,
                                "output_type": "voice",
                                "voice": config.tts_voice,
                                "format": config.tts_output_format,
                                "generated_text": _safe_answer_text_for_log(
                                    formatted_result, max_len=3000
                                ),
                                "mime_type": out_asset.content_type,
                                "filename": out_asset.filename,
                                "size_bytes": out_asset.size_bytes,
                                "provider": tts_result.provider,
                                "model": tts_result.model,
                            },
                        )
                        tts_details["output_asset_ref"] = out_asset.asset_ref
                        tts_details["output_audio_path"] = (
                            str(out_path) if out_path else None
                        )
                        tts_details["latency_ms"] = tts_result.latency_ms
                        try:
                            if out_path is None:
                                raise FileNotFoundError("tts output asset path missing")
                            with out_path.open("rb") as vf:
                                bot.send_voice(message.chat.id, vf)
                            lifecycle.log_processing_event(
                                execution_id=execution_id,
                                intake_event_id=intake_id,
                                stage="tts_completed",
                                status="success",
                                details=tts_details,
                            )
                        except Exception as send_exc:
                            lifecycle.log_processing_event(
                                execution_id=execution_id,
                                intake_event_id=intake_id,
                                stage="tts_error",
                                status="error",
                                details=tts_details,
                                error_text=str(send_exc),
                            )
                    else:
                        lifecycle.log_processing_event(
                            execution_id=execution_id,
                            intake_event_id=intake_id,
                            stage="tts_error",
                            status="error",
                            details={
                                **tts_stage_base,
                                "provider": tts_result.provider,
                                "model": tts_result.model,
                                "latency_ms": tts_result.latency_ms,
                                "error": tts_result.error,
                            },
                            error_text=tts_result.error,
                        )

            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="voice_processing_done",
                status="success",
                details={
                    **voice_base_details,
                    "downstream_route": "image_generation" if is_image_request else "text_response",
                },
            )
        except Exception as exc:
            traceback.print_exc()
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="voice_processing_error",
                status="error",
                details={"mode": "voice", "route": "voice"},
                error_text=str(exc),
            )
            bot.send_message(
                message.chat.id,
                "Не удалось обработать голосовое сообщение. Попробуйте позже.",
            )

    @bot.message_handler(
        func=lambda msg: msg.content_type == "text"
        and (not msg.text or not msg.text.startswith("/"))
    )
    def handle_text(message: telebot.types.Message) -> None:
        is_image_request = False
        try:
            text = (message.text or "").strip()
            if not text:
                bot.send_message(message.chat.id, "Введите текстовый запрос.")
                return

            uid = message.from_user.id
            mode: Mode = user_store.get_mode(uid)

            if mode == "rag":
                execution_id = str(uuid.uuid4())
                intake_id: uuid.UUID | None = None
                try:
                    print("[assistant-flow] rag handler started", flush=True)
                    rag_service = rag_holder["service"] or try_init_rag(log_to_db=False)
                    if rag_service is None:
                        intake_id = lifecycle.create_intake_event(
                            execution_id=execution_id,
                            telegram_chat_id=message.chat.id,
                            telegram_user_id=message.from_user.id,
                            text_preview=text,
                            original_char_length=len(text),
                        )
                        lifecycle.log_processing_event(
                            execution_id=execution_id,
                            intake_event_id=intake_id,
                            stage="intake_received",
                            status="success" if intake_id else "error",
                            details={"mode": "rag"},
                            error_text=None
                            if intake_id
                            else "intake_events insert failed",
                        )
                        lifecycle.log_processing_event(
                            execution_id=execution_id,
                            intake_event_id=intake_id,
                            stage="rag_unavailable",
                            status="error",
                            details={
                                "route": "rag",
                                "reason": "chroma_unavailable",
                            },
                            error_text=(rag_holder["last_error"] or "rag init failed")[
                                :4000
                            ],
                        )
                        bot.send_message(
                            message.chat.id,
                            "База знаний временно недоступна. Попробуйте позже.",
                        )
                        return

                    bot.send_message(message.chat.id, "Ищу в базе знаний… ⏳")
                    intake_id = lifecycle.create_intake_event(
                        execution_id=execution_id,
                        telegram_chat_id=message.chat.id,
                        telegram_user_id=message.from_user.id,
                        text_preview=text,
                        original_char_length=len(text),
                    )
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="intake_received",
                        status="success" if intake_id else "error",
                        details={"mode": "rag"},
                        error_text=None
                        if intake_id
                        else "intake_events insert failed",
                    )
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="route_selected",
                        status="success",
                        details={"route": "rag"},
                    )
                    history = user_store.rag_history_snapshot(uid)
                    print(
                        "[assistant-flow] rag before rag_service.answer",
                        flush=True,
                    )
                    result = rag_service.answer(
                        text, conversation_history=history
                    )
                    print(
                        "[assistant-flow] rag after rag_service.answer",
                        flush=True,
                    )
                    rag_diag = result.diagnostics
                    rag_details: dict[str, object] = {"route": "rag"}
                    if rag_diag is not None:
                        rag_details.update(rag_diag.to_log_details())
                    rag_status = (
                        "error"
                        if rag_details.get("fallback_reason") == "llm_error"
                        else "success"
                    )
                    reply = _format_rag_telegram_reply(result)
                    telegram_reply = format_for_telegram(reply)
                    rag_details["answer_text"] = _safe_answer_text_for_log(telegram_reply)
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="rag_answer_done",
                        status=rag_status,
                        details=rag_details,
                    )
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="processing_done",
                        status="success",
                        details={"route": "rag"},
                    )
                    user_store.append_rag_turn(uid, text, result.answer)
                    print("[assistant-flow] rag before send_message", flush=True)
                    send_long_message(
                        bot, message.chat.id, telegram_reply
                    )
                    print("[assistant-flow] rag after send_message", flush=True)
                except BaseException as exc:
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="processing_error",
                        status="error",
                        details={"route": "rag"},
                        error_text=str(exc),
                    )
                    lifecycle.log_error_from_exception(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        component="RagPipeline",
                        operation="answer",
                        exc=exc,
                    )
                    print("[assistant-flow] rag handler failed", flush=True)
                    print(type(exc), exc, flush=True)
                    traceback.print_exc()
                    el = str(exc).lower()
                    if any(
                        x in el
                        for x in (
                            "chroma",
                            "connection",
                            "refused",
                            "timeout",
                            "unreachable",
                            "errno",
                        )
                    ):
                        rag_holder["service"] = None
                    try:
                        bot.send_message(
                            message.chat.id,
                            "Не удалось выполнить поиск по базе знаний. Подробности выведены в консоль.",
                        )
                    except BaseException as send_exc:
                        print(
                            "[assistant-flow] rag: could not send error message",
                            flush=True,
                        )
                        print(type(send_exc), send_exc, flush=True)
                        traceback.print_exc()
                return

            is_image_request = orchestrator.route_request(text) == "image_generation"
            execution_id = str(uuid.uuid4())
            intake_id = lifecycle.create_intake_event(
                execution_id=execution_id,
                telegram_chat_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                text_preview=text,
                original_char_length=len(text),
            )
            intake_details: dict = {
                "mode": "image" if is_image_request else "text",
                "query_preview": _safe_query_preview_for_log(text, max_len=200),
                "user_text": _safe_answer_text_for_log(text, max_len=3000),
            }
            if is_image_request:
                intake_details["route"] = "image_generation"
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_id,
                stage="intake_received",
                status="success" if intake_id else "error",
                details=intake_details,
                error_text=None if intake_id else "intake_events insert failed",
            )
            if is_image_request:
                bot.send_message(
                    message.chat.id,
                    "Генерирую изображение, это может занять до 1 минуты ⏳",
                )

            start_ts = time.monotonic()
            result = orchestrator.process_text(
                text,
                execution_id=execution_id,
                intake_event_id=intake_id,
                lifecycle=lifecycle,
            )
            usage = orchestrator.get_last_text_usage_snapshot()
            model_snapshot = orchestrator.get_last_text_model_snapshot()
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            result_text = str(result)
            is_image_path = (
                "outputs" in result_text.lower()
                or "/storage/" in result_text.lower()
                or result_text.lower().endswith(".png")
                or result_text.lower().endswith(".jpg")
                or result_text.lower().endswith(".jpeg")
            )
            if is_image_path:
                try:
                    img_snap = orchestrator.get_last_image_generation_snapshot()
                    asset_ref = str(img_snap.get("asset_ref") or "").strip()
                    resolved_path: Path | None = None
                    if asset_ref:
                        try:
                            p_candidate = asset_repository.resolve_path(asset_ref)
                            if p_candidate.is_file():
                                resolved_path = p_candidate
                        except Exception:
                            resolved_path = None
                    if resolved_path is None:
                        p_legacy = Path(result_text)
                        if p_legacy.is_file():
                            resolved_path = p_legacy
                    if resolved_path is None:
                        raise FileNotFoundError(
                            "image file is missing for both asset_ref and image_path"
                        )
                    with resolved_path.open("rb") as image_file:
                        bot.send_photo(message.chat.id, image_file)
                    usage_done = orchestrator.get_last_text_usage_snapshot()
                    model_done = orchestrator.get_last_text_model_snapshot()
                    prov_url = img_snap.get("provider_url") or img_snap.get("image_url")
                    im_model = str(img_snap.get("model") or "").strip()
                    details_done: dict = {
                        "route": "image_generation",
                        "generation_completed": True,
                        "output_images": build_output_image_records(
                            str(resolved_path),
                            provider_url=str(prov_url) if prov_url else None,
                            provider=str(img_snap.get("provider") or "") or None,
                            model=im_model or None,
                        ),
                        "latency_ms": latency_ms,
                        "provider": str(img_snap.get("provider") or "").strip() or "proxy",
                    }
                    if im_model:
                        details_done["model"] = im_model
                    for k in (
                        "asset_ref",
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "image_tokens",
                        "cost_usd",
                        "usage",
                    ):
                        if k in img_snap and img_snap.get(k) is not None:
                            details_done[k] = img_snap[k]
                    if "input_tokens" in usage_done:
                        details_done["input_tokens"] = usage_done["input_tokens"]
                    if "output_tokens" in usage_done:
                        details_done["output_tokens"] = usage_done["output_tokens"]
                    if "total_tokens" in usage_done:
                        details_done["total_tokens"] = usage_done["total_tokens"]
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="processing_done",
                        status="success",
                        details=details_done,
                    )
                except Exception as send_exc:
                    traceback.print_exc()
                    lifecycle.log_processing_event(
                        execution_id=execution_id,
                        intake_event_id=intake_id,
                        stage="processing_error",
                        status="error",
                        details={"route": "image_generation"},
                        error_text=str(send_exc),
                    )
                    bot.send_message(
                        message.chat.id,
                        "Не удалось сгенерировать изображение. Попробуйте позже.",
                    )
            elif is_image_request:
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="processing_error",
                    status="error",
                    details={"route": "image_generation"},
                    error_text="Ответ не является путём к файлу изображения",
                )
                bot.send_message(
                    message.chat.id,
                    "Не удалось сгенерировать изображение. Попробуйте позже.",
                )
            else:
                formatted_result = format_for_telegram(result_text)
                send_long_message(bot, message.chat.id, formatted_result)
                lifecycle.log_processing_event(
                    execution_id=execution_id,
                    intake_event_id=intake_id,
                    stage="text_answer_done",
                    status="success",
                    details={
                        "route": "text_response",
                        "answer_text": _safe_answer_text_for_log(
                            formatted_result, max_len=3000
                        ),
                        "answer_preview": _safe_answer_text_for_log(
                            formatted_result, max_len=300
                        ),
                        "query_preview": _safe_query_preview_for_log(text, max_len=200),
                        "provider": "gigachat",
                        "model": model_snapshot or config.gigachat_model,
                        **(
                            {"input_tokens": usage["input_tokens"]}
                            if "input_tokens" in usage
                            else {}
                        ),
                        **(
                            {"output_tokens": usage["output_tokens"]}
                            if "output_tokens" in usage
                            else {}
                        ),
                        **(
                            {"total_tokens": usage["total_tokens"]}
                            if "total_tokens" in usage
                            else {}
                        ),
                        "latency_ms": latency_ms,
                    },
                )
        except Exception:
            traceback.print_exc()
            if user_store.get_mode(message.from_user.id) == "rag":
                try:
                    bot.send_message(
                        message.chat.id,
                        "Не удалось выполнить поиск по базе знаний. Подробности выведены в консоль.",
                    )
                except BaseException:
                    traceback.print_exc()
            elif is_image_request:
                bot.send_message(
                    message.chat.id,
                    "Не удалось сгенерировать изображение. Попробуйте позже.",
                )
            else:
                bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    return bot


def run_polling() -> None:
    try:
        bot = create_bot()
    except Exception:
        print(
            "Telegram bot failed during startup (create_bot).",
            file=sys.stderr,
        )
        traceback.print_exc()
        raise

    token_env = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    print(f"TELEGRAM_BOT_TOKEN is set: {bool(token_env)}", flush=True)
    print(f"token length: {len(bot.token)}", flush=True)
    print("bot object created", flush=True)
    print("Telegram bot started", flush=True)
    print("starting infinity_polling...", flush=True)

    try:
        bot.infinity_polling(
            skip_pending=True,
            timeout=60,
            long_polling_timeout=60,
        )
        print("WARNING: infinity_polling returned unexpectedly", flush=True)
    except BaseException as exc:
        print(type(exc), exc, flush=True)
        traceback.print_exc()
        raise
