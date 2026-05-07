from typing import Dict

from providers.image_provider import ImageProvider
from providers.openai_image_provider import OpenAIImageProvider
from providers.proxy_image_provider import ProxyImageProvider
from utils.config import AppConfig
from utils.request_logger import RequestLogger


class ImageGenerationService:
    def __init__(self, config: AppConfig, request_logger: RequestLogger) -> None:
        self._config = config
        self._request_logger = request_logger
        self._providers: Dict[str, ImageProvider] = {
            "openai": OpenAIImageProvider(
                api_key=config.openai_api_key,
                model=config.openai_image_model,
            ),
            "proxy": ProxyImageProvider(
                api_key=config.proxy_api_key,
                base_url=config.proxy_openai_base_url
                or "https://api.proxyapi.ru/openai/v1",
                model=config.proxy_image_model,
            ),
        }

    def generate_image(self, prompt: str, provider_name: str | None = None) -> dict:
        normalized_provider = (
            (provider_name or self._config.image_provider or "proxy").strip().lower()
        )
        if normalized_provider not in self._providers:
            raise ValueError(f"Unsupported image provider: {provider_name}")

        if normalized_provider == "proxy":
            print("image provider: proxy", flush=True)

        provider = self._providers[normalized_provider]
        result = provider.generate_image(prompt)
        model_name = (
            self._config.openai_image_model
            if normalized_provider == "openai"
            else self._config.proxy_image_model
        )
        self._request_logger.log_request(
            provider=result.get("provider"),
            endpoint="images.generate",
            operation="image_generation",
            input_type="text",
            model=model_name,
            duration_ms=result.get("duration_ms"),
            status=result.get("status"),
            error_text=result.get("error_text"),
        )
        result["model"] = model_name
        return result
