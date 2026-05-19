"""
Нормализация visibility metadata чанков (P8.1).

Поддерживаются ключи ``visibility`` и ``document_visibility`` (alias).
"""

from __future__ import annotations

from typing import Any

VISIBILITY_PUBLIC = "public"
VISIBILITY_INTERNAL = "internal"
VISIBILITY_RESTRICTED = "restricted"
VISIBILITY_UNSPECIFIED = "unspecified"


def effective_visibility(meta: dict[str, Any]) -> str:
    """Единое значение visibility для политик retrieval."""
    for key in ("document_visibility", "visibility"):
        raw = meta.get(key)
        if raw is None:
            continue
        s = str(raw).strip().lower()
        if s:
            return s
    return VISIBILITY_UNSPECIFIED
