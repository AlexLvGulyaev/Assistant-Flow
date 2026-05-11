"""
Контракт chunking-слоя (P6.3): отдельный engineering subsystem для retrieval-quality.

Текущая семантика размеров — **character-oriented approximation** (см. PROJECT_STATE §30).
Будущее: token-aware chunking без поломки этого контракта на границах эволюции.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ChunkingDocument:
    """Вход: полный текст одного логического документа (страница PDF, файл .md и т.д.) + базовые metadata."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkMetadata:
    """
    Минимальный набор полей chunk для downstream (Chroma, retrieval contract).

    Поля не удаляют существующие ключи из базового metadata при merge — только дополняют.
    """

    source: str
    chunk_index: int
    total_chunks: int
    chunking_strategy: str
    approximate_size: int
    document_id: str | None = None
    version_id: str | None = None

    def merged_into(self, base: dict[str, Any]) -> dict[str, Any]:
        """Объединение с базовым metadata документа (backward-compatible)."""
        out: dict[str, Any] = dict(base)
        out["source"] = self.source or out.get("source") or "unknown"
        out["chunk_index"] = self.chunk_index
        out["total_chunks"] = self.total_chunks
        out["chunking_strategy"] = self.chunking_strategy
        out["approximate_size"] = self.approximate_size
        if self.document_id is not None:
            out.setdefault("document_id", self.document_id)
        if self.version_id is not None:
            out.setdefault("version_id", self.version_id)
        return out


@dataclass(frozen=True)
class ChunkingResult:
    """Один chunk: текст + нормализованные metadata."""

    text: str
    metadata: ChunkMetadata

    def to_langchain_metadata(self, base: dict[str, Any]) -> dict[str, Any]:
        return self.metadata.merged_into(dict(base))


@runtime_checkable
class Chunker(Protocol):
    """Детерминированный chunker без LLM (foundation)."""

    def chunk_text(self, document: ChunkingDocument) -> list[ChunkingResult]:
        """Разбивает текст документа на chunks с metadata."""
        ...


@dataclass(frozen=True)
class ChunkingTelemetry:
    """Компактная телеметрия одного вызова chunking (без содержимого)."""

    strategy: str
    chunks_created: int
    avg_chunk_size: int
    max_chunk_size: int
