import traceback

from core.orchestrator import PromptOrchestrator
from providers.gigachat_provider import GigaChatProvider
from services.gigachat_service import GigaChatService
from services.image_generation_service import ImageGenerationService
from utils.config import load_config
from utils.request_logger import RequestLogger


def build_orchestrator() -> PromptOrchestrator:
    config = load_config()
    request_logger = RequestLogger(config.logs_db_path)
    service = GigaChatService(config=config, request_logger=request_logger)
    image_generation_service = ImageGenerationService(
        config=config,
        request_logger=request_logger,
    )
    provider = GigaChatProvider(service=service)
    return PromptOrchestrator(
        gigachat_provider=provider,
        request_logger=request_logger,
        model_name=config.gigachat_model,
        image_generation_service=image_generation_service,
    )


def main() -> None:
    orchestrator = build_orchestrator()
    user_prompt = input("Введите запрос для GigaChat: ").strip()
    try:
        answer = orchestrator.process_prompt(user_prompt)
        print("\nОтвет GigaChat:")
        print(answer)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
