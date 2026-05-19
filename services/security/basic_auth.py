"""HTTP Basic auth parsing (без зависимости от Starlette)."""

from __future__ import annotations

import base64


def parse_basic_auth_header(header: str | None) -> tuple[str, str] | None:
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in raw:
        return None
    email, _, password = raw.partition(":")
    if not email.strip():
        return None
    return email.strip(), password
