"""
OCR / извлечение текста с изображения через vision-capable OpenAI chat (без tesseract и т.п.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Явный prompt для урока RAG (модуль 5): только текст, без комментариев модели.
OCR_DEFAULT_USER_PROMPT_RU = (
    "Распознай весь текст на изображении. Верни только текст. "
    "Если текста нет, скажи, что текст не обнаружен."
)

_OCR_MARKERS = (
    "ocr",
    "оцр",
    "распознай",
    "распознать",
    "прочитай",
    "прочитать",
    "текст на изображении",
    "текст с картинки",
    "текст с изображения",
    "считай текст",
    "извлеки текст",
    "read the text",
    "extract text",
    "read this image",
)


def caption_requests_ocr(caption: str) -> bool:
    """True, если подпись к фото явно просит OCR/чтение текста."""
    s = (caption or "").strip().lower()
    if not s:
        return False
    return any(m in s for m in _OCR_MARKERS)


def build_ocr_user_instruction(*, caption: str | None, mode_is_ocr: bool) -> str:
    """Текстовая часть vision-запроса: дефолтный OCR-prompt + опционально подпись пользователя."""
    cap = (caption or "").strip()
    if mode_is_ocr and not cap:
        return OCR_DEFAULT_USER_PROMPT_RU
    if mode_is_ocr and cap:
        return f"{OCR_DEFAULT_USER_PROMPT_RU}\n\nДополнительно от пользователя: {cap}"
    if cap:
        return cap
    return OCR_DEFAULT_USER_PROMPT_RU


if TYPE_CHECKING:
    from providers.openai_chat_provider import OpenAIChatProvider


class VisionOcrService:
    """Тонкая обёртка над OpenAI vision; сохранение входного файла — на стороне caller (Telegram → AssetRepository)."""

    def __init__(self, chat: "OpenAIChatProvider") -> None:
        self._chat = chat

    def extract_text(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        user_instruction: str,
    ) -> str:
        return self._chat.extract_text_from_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_instruction=user_instruction,
            temperature=0.1,
            max_tokens=4096,
        )
