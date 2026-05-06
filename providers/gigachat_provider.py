from services.gigachat_service import GigaChatService


class GigaChatProvider:
    def __init__(self, service: GigaChatService) -> None:
        self._service = service

    def generate_response(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty")
        return self._service.send_prompt(prompt.strip())

    def get_last_usage_snapshot(self) -> dict[str, int]:
        return self._service.get_last_usage_snapshot()

    def get_last_model_snapshot(self) -> str | None:
        return self._service.get_last_model_snapshot()
