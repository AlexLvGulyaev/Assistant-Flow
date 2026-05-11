"""
Контракт conversational memory (P6.3 foundation).

Conversational memory — **отдельный subsystem** (не helper внутри orchestrator):
отдельный lifecycle через `ConversationMemoryService`, budget discipline, observability.
KB retrieval (`services/retrieval/`, RAG) **не** смешивается с этим read/write path.

Явное разделение:
- **dialog history** — персистентные user/assistant реплики в PostgreSQL (этот слой);
- **semantic memory** — будущие извлекаемые записи памяти (отдельный retrieval namespace), здесь НЕ реализовано;
- **KB retrieval context** — RAG-чанки и промежуточный контекст; в dialog history **не** сохраняются.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConversationMemoryRecord:
    """Одна запись dialog history (не semantic memory vector)."""

    message_id: str
    session_id: str
    user_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_id: str | None = None


@dataclass(frozen=True)
class ConversationMemoryQuery:
    """Параметры выборки (расширяемо без ломания API)."""

    session_id: str
    limit: int = 50


@dataclass(frozen=True)
class MemoryBudgetPolicy:
    """
    Ограничения выдачи recent messages (character approximation; token-aware — отложено).

    Conservative defaults: защита от context explosion до hybrid/memory retrieval.
    Read path: детерминированный trim по `max_message_chars`, затем жёстный cap по
    `total_memory_chars_budget` (без silent exceed суммарной выдачи).
    """

    max_recent_messages: int = 50
    max_message_chars: int = 8000
    total_memory_chars_budget: int = 32000


@runtime_checkable
class ConversationMemoryServiceProtocol(Protocol):
    def get_recent_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        ...

    def get_session_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        ...
