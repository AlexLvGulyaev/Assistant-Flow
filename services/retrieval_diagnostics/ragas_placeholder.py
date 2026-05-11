"""
Placeholder для будущей интеграции RAGAS на уровне retrieval-diagnostics.

По умолчанию выключено; отсутствие пакета ragas не является ошибкой (P6.8).
"""

from __future__ import annotations

from typing import Any


def try_retrieval_ragas_row(
    *,
    query: str,
    contexts: list[str],
    enable: bool = False,
) -> dict[str, Any] | None:
    """
    Заготовка: при ``enable`` и установленном ragas можно вернуть строку для RAGAS.

    Сейчас всегда ``None`` — не тянем тяжёлые зависимости в обязательный путь.
    """
    del query, contexts
    if not enable:
        return None
    try:
        import ragas  # noqa: F401, PLC0415
    except ImportError:
        return None
    return None
