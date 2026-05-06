import time
import traceback
import uuid
from typing import Any, Dict

import requests

from utils.config import AppConfig
from utils.request_logger import RequestLogger


class GigaChatService:
    def __init__(self, config: AppConfig, request_logger: RequestLogger) -> None:
        self._config = config
        self._request_logger = request_logger
        self._last_usage: dict[str, int] = {}
        self._last_model: str | None = None

    def _build_auth_header(self) -> str:
        auth_value = self._config.gigachat_auth_key.strip()
        if not auth_value.startswith("Basic "):
            auth_value = f"Basic {auth_value}"
        return auth_value

    @staticmethod
    def _safe_response_text(response: requests.Response) -> str:
        """
        Avoid leaking secrets in logs while preserving troubleshooting value.
        """
        try:
            body = response.json()
            if isinstance(body, dict):
                if "access_token" in body:
                    body["access_token"] = "***masked***"
                if "refresh_token" in body:
                    body["refresh_token"] = "***masked***"
            return str(body)
        except Exception:
            return response.text

    def get_access_token(self) -> str:
        endpoint = "oauth_token"
        start_ts = time.perf_counter()
        status_code = None
        operation = "get_access_token"
        error_text = None
        status = "success"

        try:
            headers = {
                "Authorization": self._build_auth_header(),
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            payload = {"scope": self._config.gigachat_scope}

            response = requests.post(
                self._config.token_url,
                headers=headers,
                data=payload,
                timeout=self._config.timeout_seconds,
                verify=False,  # только для разработки, в production нужен SSL
            )
            status_code = response.status_code
            print(f"[GigaChat][token] status_code={response.status_code}")
            print(f"[GigaChat][token] response_text={self._safe_response_text(response)}")
            response.raise_for_status()

            token = response.json().get("access_token")
            if not token:
                raise RuntimeError("GigaChat token is missing in response")
            return token
        except Exception:
            status = "error"
            error_text = traceback.format_exc()
            traceback.print_exc()
            raise
        finally:
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            self._request_logger.log_request(
                provider="gigachat",
                endpoint=endpoint,
                operation=operation,
                input_type="text",
                model=None,
                duration_ms=duration_ms,
                status=status,
                status_code=status_code,
                error_text=error_text,
            )

    def send_prompt(self, prompt: str) -> str:
        endpoint = "chat_completions"
        start_ts = time.perf_counter()
        status_code = None
        operation = "send_prompt"
        error_text = None
        status = "success"

        try:
            access_token = self.get_access_token()
            headers = {
                "Authorization": f"Bearer {access_token}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/json",
            }
            payload: Dict[str, Any] = {
                "model": self._config.gigachat_model,
                "max_tokens": self._config.gigachat_max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            response = requests.post(
                self._config.prompt_url,
                headers=headers,
                json=payload,
                timeout=self._config.timeout_seconds,
                verify=False,  # только для разработки, в production нужен SSL
            )
            status_code = response.status_code
            print(f"[GigaChat][chat] status_code={response.status_code}")
            print(f"[GigaChat][chat] response_text={self._safe_response_text(response)}")
            response.raise_for_status()

            data = response.json()
            self._last_model = str(data.get("model") or self._config.gigachat_model)
            usage_raw = data.get("usage")
            usage_out: dict[str, int] = {}
            if isinstance(usage_raw, dict):
                mapping = {
                    "prompt_tokens": "input_tokens",
                    "input_tokens": "input_tokens",
                    "completion_tokens": "output_tokens",
                    "output_tokens": "output_tokens",
                    "total_tokens": "total_tokens",
                }
                for src_k, dst_k in mapping.items():
                    raw_v = usage_raw.get(src_k)
                    if raw_v is None:
                        continue
                    try:
                        usage_out[dst_k] = int(raw_v)
                    except (TypeError, ValueError):
                        continue
            self._last_usage = usage_out
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("GigaChat response has no choices")

            message = choices[0].get("message", {})
            content = message.get("content")
            if not content:
                raise RuntimeError("GigaChat response content is empty")
            return content
        except Exception:
            status = "error"
            error_text = traceback.format_exc()
            traceback.print_exc()
            raise
        finally:
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            self._request_logger.log_request(
                provider="gigachat",
                endpoint=endpoint,
                operation=operation,
                input_type="text",
                model=self._config.gigachat_model,
                duration_ms=duration_ms,
                status=status,
                status_code=status_code,
                error_text=error_text,
            )

    def get_last_usage_snapshot(self) -> dict[str, int]:
        return dict(self._last_usage)

    def get_last_model_snapshot(self) -> str | None:
        return self._last_model
