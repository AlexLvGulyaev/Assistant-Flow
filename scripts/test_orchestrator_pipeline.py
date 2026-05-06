import sys
import traceback
from pathlib import Path


# Add project root to import path for standalone script execution.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import PromptOrchestrator
from providers.gigachat_provider import GigaChatProvider
from services.gigachat_service import GigaChatService
from services.image_generation_service import ImageGenerationService
from utils.config import load_config
from utils.request_logger import RequestLogger


def run_test(orchestrator: PromptOrchestrator, title: str, prompt: str) -> None:
    print(f"[TEST] {title}")
    print(f"[INPUT] {prompt}")
    try:
        result = orchestrator.process_text(prompt)
        print(f"[RESULT] {result}")
    except Exception:
        print(f"[ERROR] Test failed: {title}")
        traceback.print_exc()
    finally:
        print("-" * 80)


def main() -> None:
    config = load_config()
    request_logger = RequestLogger(config.logs_db_path)

    gigachat_service = GigaChatService(config=config, request_logger=request_logger)
    gigachat_provider = GigaChatProvider(service=gigachat_service)
    image_generation_service = ImageGenerationService(
        config=config,
        request_logger=request_logger,
    )

    orchestrator = PromptOrchestrator(
        gigachat_provider=gigachat_provider,
        request_logger=request_logger,
        model_name=config.gigachat_model,
        image_generation_service=image_generation_service,
    )

    run_test(
        orchestrator=orchestrator,
        title="Text request without image generation",
        prompt="Объясни простыми словами, как работает фотосинтез",
    )
    run_test(
        orchestrator=orchestrator,
        title="Image generation request",
        prompt="Нарисуй футуристический город на закате",
    )


if __name__ == "__main__":
    main()
