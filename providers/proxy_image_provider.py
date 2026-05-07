import base64
import time
import traceback
from typing import Any, Dict

import requests
from openai import OpenAI

from providers.image_provider import ImageProvider
from services.asset_repository import AssetRepository


class ProxyImageProvider(ImageProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        asset_repository: AssetRepository,
    ) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._asset_repository = asset_repository

    def generate_image(self, prompt: str) -> Dict[str, Any]:
        start_ts = time.perf_counter()
        result: Dict[str, Any] = {
            "provider": "proxy",
            "model": self._model,
            "image_path": None,
            "duration_ms": None,
            "status": "error",
            "error_text": None,
            "provider_url": None,
        }

        try:
            response = self._client.images.generate(model=self._model, prompt=prompt)
            if getattr(response, "data", None) and response.data:
                image_item = response.data[0]
                url_hint = getattr(image_item, "url", None)
                if url_hint:
                    result["provider_url"] = str(url_hint)
            asset_ref = self._save_response_image(response)
            image_path = self._asset_repository.resolve_path(asset_ref)
            result["image_path"] = str(image_path)
            result["asset_ref"] = asset_ref.relative_path
            result["status"] = "success"
            return result
        except Exception:
            result["error_text"] = traceback.format_exc()
            traceback.print_exc()
            return result
        finally:
            result["duration_ms"] = int((time.perf_counter() - start_ts) * 1000)

    def _save_response_image(self, response: Any) -> Any:
        if not getattr(response, "data", None):
            raise RuntimeError("Proxy image response has no data")

        image_item = response.data[0]
        filename = "proxy_generated.png"

        b64_data = getattr(image_item, "b64_json", None)
        if b64_data:
            binary = base64.b64decode(b64_data)
            return self._asset_repository.save_bytes(
                binary,
                namespace="images",
                filename=filename,
                content_type="image/png",
            )

        image_url = getattr(image_item, "url", None)
        if image_url:
            download_response = requests.get(image_url, timeout=30)
            download_response.raise_for_status()
            return self._asset_repository.save_bytes(
                download_response.content,
                namespace="images",
                filename=filename,
                content_type="image/png",
            )

        raise RuntimeError("Proxy image payload has neither b64_json nor url")
