"""
Hybrid context assembly (P6.4 foundation).

Это **context assembly layer**, не отдельный retriever backend.
KB остаётся через RetrievalBackend / существующий RAG retrieve path; memory — через
`ConversationMemoryService` (PostgreSQL dialog history).

Явное разделение источников (без смешивания score / ranking):
- **kb** — чанки из vector retrieval;
- **memory** — последние реплики диалога (не semantic search, не embeddings).

Детерминированный порядок выдачи: **сначала KB, затем memory**.
До появления semantic memory / rerank **нельзя** делать общий ranking KB + memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


HybridSourceType = Literal["kb", "memory"]


@dataclass(frozen=True)
class HybridContextItem:
    """Один элемент собранного контекста (KB chunk или строка dialog memory)."""

    source_type: HybridSourceType
    content: str
    role: str | None = None
    created_at: datetime | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HybridContextResult:
    """Результат сборки: элементы + строка для LLM + флаги budget/усечения."""

    items: tuple[HybridContextItem, ...]
    context_text: str
    hybrid_enabled: bool
    budget_applied: bool
    memory_truncated: bool
    kb_truncated: bool
    total_context_chars: int


@dataclass(frozen=True)
class HybridRetrievalPolicy:
    """
    Жёсткие лимиты hybrid assembly (char-based; conservative defaults).

    Правило: **KB priority > memory** — сначала заполняется KB-блок в пределах
    `max_kb_chars` / `max_kb_chunks`, затем memory только из остатка `max_context_chars`
    и в пределах `max_memory_chars` / `max_memory_messages`. Memory не вытесняет KB.
    """

    max_kb_chunks: int = 5
    max_memory_messages: int = 8
    max_context_chars: int = 12_000
    max_memory_chars: int = 2_500
    max_kb_chars: int = 8_000
