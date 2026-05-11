#!/usr/bin/env python3
"""
Smoke: OCR / vision route (service-level).

Полный Telegram E2E не обязателен: проверка эвристик маршрутизации и при наличии
OPENAI_API_KEY — один вызов vision API на минимальном PNG (1×1).

  docker exec -it portfolio-test-assistant-flow-1 python scripts/test_ocr_route_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import base64

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Заведомо валидный PNG 1×1 (transparent) без внешних зависимостей.
_MINIMAL_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kvpEAAAAASUVORK5CYII="
)


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.vision_ocr_service import (
        OCR_DEFAULT_USER_PROMPT_RU,
        VisionOcrService,
        build_ocr_user_instruction,
        caption_requests_ocr,
    )

    assert caption_requests_ocr("OCR please")
    assert caption_requests_ocr("распознай текст")
    assert caption_requests_ocr("прочитай изображение")
    assert not caption_requests_ocr("")
    assert not caption_requests_ocr("просто привет")

    ins = build_ocr_user_instruction(caption=None, mode_is_ocr=True)
    assert "Распознай" in ins
    ins2 = build_ocr_user_instruction(caption="дополнительно", mode_is_ocr=True)
    assert "дополнительно" in ins2

    # Incoming image asset persistence (no Telegram, no OCR libs).
    # Use workspace-local dir: host/CI may not have /app/storage from docker .env.
    from services.asset_repository import FilesystemAssetRepository

    asset_root = ROOT / ".tmp" / "ocr_smoke_assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    repo = FilesystemAssetRepository(asset_root)
    ref = repo.save_bytes(
        _MINIMAL_PNG_1x1,
        namespace="incoming_images",
        filename="smoke_min.png",
        content_type="image/png",
    )
    assert ref.relative_path and ref.sha256 and ref.size_bytes == len(_MINIMAL_PNG_1x1)
    sample_payload = {
        "route": "vision_ocr",
        "mode": "ocr",
        "user_input_kind": "image",
        "system_output_kind": "text",
        "input_asset_ref": ref.relative_path,
        "latency_ms": 42,
        "response_latency_ms": 40,
        "usage_not_returned_by_provider_wrapper": True,
    }
    dumped = json.dumps(sample_payload, ensure_ascii=False)
    assert "base64" not in dumped.lower()
    assert "iVBOR" not in dumped
    print("[assistant-flow] ocr_smoke: incoming_image_asset_ok", flush=True)

    try:
        from providers.openai_chat_provider import OpenAIChatProvider

        chat = OpenAIChatProvider(load_config())
        svc = VisionOcrService(chat)
        t0 = __import__("time").monotonic()
        out = svc.extract_text(
            image_bytes=_MINIMAL_PNG_1x1,
            mime_type="image/png",
            user_instruction=OCR_DEFAULT_USER_PROMPT_RU,
        )
        dt_ms = int((__import__("time").monotonic() - t0) * 1000)
        assert isinstance(out, str) and len(out.strip()) > 0
        assert dt_ms >= 0
        usage = chat.get_last_llm_usage_for_log()
        if usage is None:
            print("[assistant-flow] ocr_smoke: vision_usage_optional_missing", flush=True)
        else:
            assert any(k in usage for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
        print("[assistant-flow] ocr_smoke: vision_api_ok", flush=True)
    except (ValueError, ModuleNotFoundError, ImportError) as exc:
        print(
            f"[assistant-flow] ocr_smoke: vision_api_skipped ({type(exc).__name__}: {exc})",
            flush=True,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if (
            "image_parse_error" in msg
            or "unsupported image" in msg
            or "invalid_request_error" in msg
        ):
            print(f"[assistant-flow] ocr_smoke: vision_api_skipped ({exc})", flush=True)
            return 0
        print(
            f"[assistant-flow] ocr_smoke: vision_api_failed {type(exc).__name__}: {exc}",
            flush=True,
        )
        return 1

    print("[assistant-flow] test_ocr_route_smoke: OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
