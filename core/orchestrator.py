import time
import uuid
from pathlib import Path
from typing import Any

from providers.gigachat_provider import GigaChatProvider
from services.image_generation_service import ImageGenerationService
from services.runtime_lifecycle_service import RuntimeLifecycleService, truncate_for_lifecycle_log
from utils.request_logger import RequestLogger


def build_output_image_records(
    path_str: str | None,
    *,
    provider_url: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Метаданные сгенерированного файла для processing_logs.details (без binary).
    """
    if not path_str or not str(path_str).strip():
        return []
    raw = str(path_str).strip()
    p = Path(raw)
    rec: dict[str, Any] = {
        "path": raw,
        "filename": p.name,
        "provider_url": (provider_url or "") or "",
        "provider": (provider or "") or "",
        "model": (model or "") or "",
        "size": None,
    }
    try:
        if p.is_file():
            rec["size"] = int(p.stat().st_size)
    except OSError:
        rec["size"] = None
    return [rec]


class PromptOrchestrator:
    """
    Central place for business orchestration:
    - validates high-level input rules
    - delegates generation to provider layer
    """

    def __init__(
        self,
        gigachat_provider: GigaChatProvider,
        request_logger: RequestLogger | None = None,
        model_name: str | None = None,
        image_generation_service: ImageGenerationService | None = None,
    ) -> None:
        self._gigachat_provider = gigachat_provider
        self._request_logger = request_logger
        self._model_name = model_name
        self._image_generation_service = image_generation_service
        self._last_image_generation_result: dict[str, Any] | None = None

    def _log_pipeline_stage(
        self,
        operation: str,
        status: str,
        provider: str = "gigachat",
    ) -> None:
        if not self._request_logger:
            return
        self._request_logger.log_request(
            provider=provider,
            endpoint="orchestrator",
            operation=operation,
            input_type="text",
            model=self._model_name,
            status=status,
        )

    def _get_image_generation_service(self) -> ImageGenerationService:
        if self._image_generation_service is not None:
            return self._image_generation_service
        raise RuntimeError("ImageGenerationService is required for image generation")

    def get_last_text_usage_snapshot(self) -> dict[str, int]:
        """Last usage reported by the text provider, if available."""
        return self._gigachat_provider.get_last_usage_snapshot()

    def get_last_text_model_snapshot(self) -> str | None:
        """Last model reported by the text provider, if available."""
        return self._gigachat_provider.get_last_model_snapshot()

    def get_last_image_generation_snapshot(self) -> dict[str, Any]:
        """Metadata from the last image provider call in this process (for logging after process_text)."""
        return dict(self._last_image_generation_result or {})

    def process_text(
        self,
        input_text: str,
        *,
        execution_id: str | None = None,
        intake_event_id: uuid.UUID | None = None,
        lifecycle: RuntimeLifecycleService | None = None,
    ) -> str:
        exec_id = execution_id or str(uuid.uuid4())
        normalized_input = (input_text or "").strip()
        if not normalized_input:
            raise ValueError("Input prompt is empty")

        route = self.route_request(normalized_input)
        if lifecycle is not None:
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="route_selected",
                status="success",
                details={"route": route},
            )

        try:
            t_enh_start = time.monotonic()
            enhanced_prompt = self.enhance_prompt(normalized_input)
            t_enh_ms = int((time.monotonic() - t_enh_start) * 1000)
            if lifecycle is not None and route == "image_generation":
                u_enh = self.get_last_text_usage_snapshot()
                m_enh = self.get_last_text_model_snapshot()
                det_enh: dict[str, Any] = {
                    "route": route,
                    "mode": "image",
                    "enhanced_prompt": truncate_for_lifecycle_log(enhanced_prompt, 4000),
                    "enhancement_latency_ms": t_enh_ms,
                    "provider": "gigachat",
                    "model": m_enh or self._model_name,
                }
                for k in ("input_tokens", "output_tokens", "total_tokens"):
                    if k in u_enh:
                        det_enh[k] = int(u_enh[k])
                lifecycle.log_processing_event(
                    execution_id=exec_id,
                    intake_event_id=intake_event_id,
                    stage="image_text_enhancement_done",
                    status="success",
                    details=det_enh,
                )

            if route == "image_generation":
                result = self._run_image_generation_pipeline(
                    exec_id,
                    intake_event_id,
                    enhanced_prompt,
                    lifecycle,
                )
            else:
                result = self.prepare_response(route=route, enhanced_prompt=enhanced_prompt)
        except Exception as exc:
            if lifecycle is not None:
                lifecycle.log_processing_event(
                    execution_id=exec_id,
                    intake_event_id=intake_event_id,
                    stage="processing_error",
                    status="error",
                    details={"route": route},
                    error_text=str(exc),
                )
                lifecycle.log_error_from_exception(
                    execution_id=exec_id,
                    intake_event_id=intake_event_id,
                    component="PromptOrchestrator",
                    operation="process_text",
                    exc=exc,
                )
            raise

        # image_generation: processing_done is logged in Telegram after a successful send_photo
        if lifecycle is not None and route != "image_generation":
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="processing_done",
                status="success",
                details={"route": route},
            )
        return result

    def _run_image_generation_pipeline(
        self,
        exec_id: str,
        intake_event_id: uuid.UUID | None,
        enhanced_prompt: str,
        lifecycle: RuntimeLifecycleService | None,
    ) -> str:
        """Генерация изображения с полным observability в processing_logs (без изменения контракта возврата)."""
        self._last_image_generation_result = None
        if lifecycle is not None:
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="image_generation_started",
                status="started",
                details={"route": "image_generation", "mode": "image"},
            )

        t_ref_start = time.monotonic()
        image_prompt = self.build_image_prompt(enhanced_prompt)
        t_ref_ms = int((time.monotonic() - t_ref_start) * 1000)
        if lifecycle is not None:
            u_ref = self.get_last_text_usage_snapshot()
            m_ref = self.get_last_text_model_snapshot()
            det_ref: dict[str, Any] = {
                "route": "image_generation",
                "mode": "image",
                "image_prompt": truncate_for_lifecycle_log(image_prompt, 4000),
                "rewritten_prompt": truncate_for_lifecycle_log(image_prompt, 4000),
                "refinement_latency_ms": t_ref_ms,
                "provider": "gigachat",
                "model": m_ref or self._model_name,
            }
            for k in ("input_tokens", "output_tokens", "total_tokens"):
                if k in u_ref:
                    det_ref[k] = int(u_ref[k])
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="image_prompt_refinement_done",
                status="success",
                details=det_ref,
            )

        image_service = self._get_image_generation_service()
        image_result = image_service.generate_image(
            prompt=image_prompt,
            provider_name="proxy",
        )
        self._log_pipeline_stage(
            operation="image_generation",
            status=image_result.get("status", "error"),
            provider=image_result.get("provider", "proxy"),
        )

        path_raw = image_result.get("image_path")
        provider_url = image_result.get("provider_url") or image_result.get("image_url")
        img_model = image_result.get("model") or ""
        img_provider = image_result.get("provider") or "proxy"
        output_records = build_output_image_records(
            str(path_raw) if path_raw else None,
            provider_url=str(provider_url) if provider_url else None,
            provider=str(img_provider),
            model=str(img_model),
        )

        det_prov: dict[str, Any] = {
            "route": "image_generation",
            "provider": img_provider,
            "model": img_model,
            "duration_ms": image_result.get("duration_ms"),
            "status": image_result.get("status"),
            "image_path": path_raw,
            "output_images": output_records,
        }
        for k in (
            "asset_ref",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "image_tokens",
            "cost_usd",
            "usage",
        ):
            if k in image_result and image_result.get(k) is not None:
                det_prov[k] = image_result.get(k)
        if lifecycle is not None:
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="image_provider_done",
                status="success"
                if str(image_result.get("status") or "").lower() == "success"
                else "error",
                details=det_prov,
                error_text=image_result.get("error_text")
                if str(image_result.get("status") or "").lower() != "success"
                else None,
            )

        if str(image_result.get("status") or "").lower() != "success":
            err = image_result.get("error_text") or "Image generation failed"
            raise RuntimeError(err)
        if not path_raw:
            raise RuntimeError("Image generation returned empty image_path")

        self._last_image_generation_result = {
            "provider": image_result.get("provider"),
            "model": image_result.get("model"),
            "provider_url": image_result.get("provider_url") or image_result.get("image_url"),
            "duration_ms": image_result.get("duration_ms"),
            **{
                k: image_result.get(k)
                for k in (
                    "asset_ref",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "image_tokens",
                    "cost_usd",
                    "usage",
                )
                if k in image_result and image_result.get(k) is not None
            },
        }

        if lifecycle is not None:
            lifecycle.log_processing_event(
                execution_id=exec_id,
                intake_event_id=intake_event_id,
                stage="image_assets_persisted",
                status="success",
                details={
                    "route": "image_generation",
                    "generated_files": output_records,
                    "output_images": output_records,
                },
            )

        return str(path_raw)

    def enhance_prompt(self, text: str) -> str:
        operation = "prompt_enhancement"
        try:
            system_instruction = (
                "Ты объясняешь простым и понятным языком для широкой аудитории. "
                "При этом, если тема содержит формулы, научные термины или числовые зависимости, "
                "обязательно добавляй точный научный вариант без упрощений. "
                "Формат ответа: сначала простое объяснение, затем отдельный блок "
                "\"Точная формула:\" с корректной записью формулы/термина/зависимости."
            )
            composed_prompt = (
                f"{system_instruction}\n\n"
                f"Запрос пользователя:\n{text}"
            )
            enhanced_prompt = self._gigachat_provider.generate_response(composed_prompt)
            self._log_pipeline_stage(operation=operation, status="success")
            return enhanced_prompt
        except Exception:
            self._log_pipeline_stage(operation=operation, status="error")
            raise

    def clean_prompt(self, text: str) -> str:
        banned_phrases = (
            "не удалось",
            "я не могу",
            "вот описание",
            "представь себе",
        )

        # Remove empty/whitespace-only lines and collapse extra paragraphs.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        normalized_text = " ".join(lines)
        lowered_text = normalized_text.lower()

        # Remove unwanted meta-phrases in a case-insensitive way.
        cleaned_text = normalized_text
        for phrase in banned_phrases:
            phrase_lower = phrase.lower()
            while phrase_lower in lowered_text:
                idx = lowered_text.find(phrase_lower)
                cleaned_text = (cleaned_text[:idx] + cleaned_text[idx + len(phrase) :]).strip()
                lowered_text = cleaned_text.lower()

        # Keep only 1-2 short sentences for image prompt quality.
        sentence_candidates = [
            sentence.strip()
            for sentence in cleaned_text.replace("!", ".").replace("?", ".").split(".")
            if sentence.strip()
        ]
        if not sentence_candidates:
            return text.strip()

        return ". ".join(sentence_candidates[:2]).strip() + "."

    def build_image_prompt(self, text: str) -> str:
        operation = "image_prompt_building"
        try:
            system_instruction = (
                "Ты преобразуешь пользовательский запрос в краткий и точный промпт для генерации изображения.\n\n"
                "Правила:\n"
                "- Убирай художественные и абстрактные фразы\n"
                "- Оставляй только визуальные объекты\n"
                "- Добавляй:\n"
                "  - стиль (fantasy, realistic, cinematic)\n"
                "  - освещение (sunset, soft light)\n"
                "  - композицию (wide shot, detailed)\n"
                "- Убирай лишние детали и повторения\n"
                "- Максимум 2–3 предложения\n"
                "- Ответ — только текст промпта без объяснений\n"
                "- Итоговый prompt всегда на английском языке\n"
                "- Сохраняй все ключевые визуальные объекты из запроса\n"
                "- Если встречается слово \"вол\", трактуй как ox/bull, not wolf\n"
                "- Не заменяй редких животных на более привычных\n\n"
                "Few-shot пример:\n"
                "Вход:\n"
                "\"Нарисуй сказочный золотой город под голубым небом. "
                "В городе есть прозрачные ворота, яркая звезда, сад с цветами и три фантастических "
                "существа: огненно-рыжий лев, мощный вол/бык и золотой орёл.\"\n\n"
                "Ожидаемый image prompt:\n"
                "\"Fantasy golden city under a blue sky, transparent gates, a bright star above the city, "
                "lush garden with flowers, three mythical animals: fiery golden lion, powerful ox or bull, "
                "not a wolf, and golden eagle, cinematic fantasy illustration, detailed composition, warm "
                "magical lighting.\""
            )
            composed_prompt = (
                f"{system_instruction}\n\n"
                f"Запрос для преобразования:\n{text}"
            )
            image_prompt = self._gigachat_provider.generate_response(composed_prompt)
            self._log_pipeline_stage(operation=operation, status="success")
            return image_prompt.strip()
        except Exception:
            self._log_pipeline_stage(operation=operation, status="error")
            raise

    def route_request(self, text: str) -> str:
        lowered_text = text.lower()
        image_keywords = (
            "нарисуй",
            "изобрази",
            "сгенерируй изображение",
            "draw",
            "generate image",
            "create image",
            "image",
            "picture",
        )
        if any(keyword in lowered_text for keyword in image_keywords):
            return "image_generation"
        return "text_response"

    def prepare_response(self, route: str, enhanced_prompt: str) -> str:
        operation = "prepare_response"
        try:
            if route == "image_generation":
                raise RuntimeError(
                    "image_generation must use process_text() / _run_image_generation_pipeline()"
                )
            result = enhanced_prompt
            self._log_pipeline_stage(operation=operation, status="success")
            return result
        except Exception:
            self._log_pipeline_stage(operation=operation, status="error")
            raise

    def process_prompt(self, prompt: str, **kwargs: Any) -> str:
        # Backward-compatible alias for existing call sites.
        return self.process_text(prompt, **kwargs)
