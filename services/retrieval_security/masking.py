"""
Минимальное маскирование PII без NLP/детекторов (P6.7 foundation).

Только regex-хелперы для типичных паттернов; вызывающий решает, когда применять.
"""

from __future__ import annotations

import re
from typing import Callable

from services.retrieval_security.telemetry import emit_retrieval_security_event

_PHONE_LIKE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,6}(?!\d)"
)
_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)
_LONG_DIGITS = re.compile(r"\d{8,}")


def mask_phone(text: str, *, placeholder: str = "[PHONE]") -> str:
    return _PHONE_LIKE.sub(placeholder, text or "")


def mask_email(text: str, *, placeholder: str = "[EMAIL]") -> str:
    return _EMAIL.sub(placeholder, text or "")


def mask_long_digit_runs(text: str, *, placeholder: str = "[PII]", min_len: int = 8) -> str:
    """Последовательности цифр длиной >= min_len (простая эвристика под номера/ID)."""
    if min_len < 4:
        min_len = 4

    def repl(m: re.Match[str]) -> str:
        if len(m.group(0)) >= min_len:
            return placeholder
        return m.group(0)

    return _LONG_DIGITS.sub(repl, text or "")


def mask_common_pii(
    text: str,
    *,
    phone: bool = True,
    email: bool = True,
    long_digits: bool = True,
    on_mask: Callable[[str], None] | None = None,
) -> str:
    """Цепочка масок; ``on_mask`` вызывается с типом при первом изменении."""
    out = text or ""
    if phone:
        nxt = mask_phone(out)
        if nxt != out and on_mask:
            on_mask("phone")
        out = nxt
    if email:
        nxt = mask_email(out)
        if nxt != out and on_mask:
            on_mask("email")
        out = nxt
    if long_digits:
        nxt = mask_long_digit_runs(out)
        if nxt != out and on_mask:
            on_mask("long_digits")
        out = nxt
    return out


def mask_common_pii_with_telemetry(text: str) -> str:
    """Обёртка с одним событием ``masking_applied`` при любой маске."""

    applied: list[str] = []

    def on_mask(kind: str) -> None:
        if kind not in applied:
            applied.append(kind)

    out = mask_common_pii(text, on_mask=on_mask)
    if applied:
        emit_retrieval_security_event(
            "masking_applied",
            kinds=",".join(applied),
            replacements=len(applied),
        )
    return out
