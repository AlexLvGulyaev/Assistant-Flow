import traceback
from pathlib import Path

from services.image_generation_service import ImageGenerationService
from utils.config import load_config
from utils.request_logger import RequestLogger


def main() -> None:
    # Stable smoke prompt for repeatable manual verification.
    test_prompt = "A photorealistic mountain lake at sunrise, cinematic lighting"
    providers_to_test = ["openai", "proxy"]

    config = load_config()
    request_logger = RequestLogger(config.logs_db_path)
    image_service = ImageGenerationService(config=config, request_logger=request_logger)

    print("=== Image Providers Smoke Test ===")
    print(f"Prompt: {test_prompt}")
    print("")

    Path("outputs").mkdir(parents=True, exist_ok=True)

    for provider_name in providers_to_test:
        print(f"[START] provider={provider_name}")
        try:
            result = image_service.generate_image(
                prompt=test_prompt,
                provider_name=provider_name,
            )
            print(f"[RESULT] provider={provider_name}: {result}")
        except Exception:
            print(f"[ERROR] provider={provider_name} raised unexpected exception")
            traceback.print_exc()
        finally:
            print("-" * 80)


if __name__ == "__main__":
    main()
