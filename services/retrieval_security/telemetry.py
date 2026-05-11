"""
Телеметрия retrieval security (P6.7): только stdout-строки, без PII в payload.
"""

from __future__ import annotations

from typing import Any


def emit_retrieval_security_event(event: str, **fields: Any) -> None:
    """Единый префикс для grep / downstream парсеров; значения — только агрегаты/идентификаторы."""
    safe = {k: v for k, v in fields.items() if v is not None}
    tail = " ".join(f"{k}={safe[k]}" for k in sorted(safe))
    print(
        f"[assistant-flow] retrieval_security: событие={event} {tail}".rstrip(),
        flush=True,
    )
