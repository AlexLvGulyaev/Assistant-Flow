import uuid
from typing import Any

from providers.gigachat_provider import GigaChatProvider
from services.image_generation_service import ImageGenerationService
from services.runtime_lifecycle_service import RuntimeLifecycleService
from utils.request_logger import RequestLogger


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
            enhanced_prompt = self.enhance_prompt(normalized_input)
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
                provider_name = "proxy"
                image_prompt = self.build_image_prompt(enhanced_prompt)
                image_service = self._get_image_generation_service()
                image_result = image_service.generate_image(
                    prompt=image_prompt,
                    provider_name=provider_name,
                )
                self._log_pipeline_stage(
                    operation="image_generation",
                    status=image_result.get("status", "error"),
                    provider=image_result.get("provider", provider_name),
                )
                if image_result.get("status") != "success":
                    error_text = image_result.get("error_text") or "Image generation failed"
                    raise RuntimeError(error_text)
                result = image_result.get("image_path")
                if not result:
                    raise RuntimeError("Image generation returned empty image_path")
            else:
                result = enhanced_prompt
            self._log_pipeline_stage(operation=operation, status="success")
            return result
        except Exception:
            self._log_pipeline_stage(operation=operation, status="error")
            raise

    def process_prompt(self, prompt: str, **kwargs: Any) -> str:
        # Backward-compatible alias for existing call sites.
        return self.process_text(prompt, **kwargs)
