import base64
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

import requests
from openai import OpenAI

from providers.image_provider import ImageProvider


class OpenAIImageProvider(ImageProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key)
        self._output_dir = Path("outputs")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_image(self, prompt: str) -> Dict[str, Any]:
        start_ts = time.perf_counter()
        result: Dict[str, Any] = {
            "provider": "openai",
            "image_path": None,
            "duration_ms": None,
            "status": "error",
            "error_text": None,
        }

        try:
            response = self._client.images.generate(model=self._model, prompt=prompt)
            image_path = self._save_response_image(response)
            result["image_path"] = str(image_path)
            result["status"] = "success"
            return result
        except Exception:
            result["error_text"] = traceback.format_exc()
            traceback.print_exc()
            return result
        finally:
            result["duration_ms"] = int((time.perf_counter() - start_ts) * 1000)

    def _save_response_image(self, response: Any) -> Path:
        if not getattr(response, "data", None):
            raise RuntimeError("OpenAI image response has no data")

        image_item = response.data[0]
        filename = self._output_dir / f"openai_{uuid.uuid4().hex}.png"

        b64_data = getattr(image_item, "b64_json", None)
        if b64_data:
            binary = base64.b64decode(b64_data)
            filename.write_bytes(binary)
            return filename

        image_url = getattr(image_item, "url", None)
        if image_url:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            filename.write_bytes(response.content)
            return filename

        raise RuntimeError("OpenAI image payload has neither b64_json nor url")
