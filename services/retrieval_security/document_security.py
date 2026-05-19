"""
Security metadata для ingestion / indexing (P8.2).

Без миграций SQL: visibility хранится в chunk metadata (PostgreSQL JSONB + vector backends).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.documents import Document

from services.retrieval_security.visibility import (
    VISIBILITY_INTERNAL,
    VISIBILITY_PUBLIC,
    VISIBILITY_RESTRICTED,
    VISIBILITY_UNSPECIFIED,
    effective_visibility,
)

# Новые загрузки: не public по умолчанию (guest не увидит без явного выбора).
DEFAULT_NEW_DOCUMENT_VISIBILITY = VISIBILITY_INTERNAL

_KNOWN_VISIBILITY = frozenset(
    {
        VISIBILITY_PUBLIC,
        VISIBILITY_INTERNAL,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
    }
)


def normalize_upload_visibility(raw: str | None) -> str:
    """
    Нормализует значение из Admin API / UI.

    Пустое / неизвестное → ``internal`` (secure default для новых документов).
    """
    s = (raw or "").strip().lower()
    if s in (VISIBILITY_PUBLIC, VISIBILITY_INTERNAL, VISIBILITY_RESTRICTED):
        return s
    return DEFAULT_NEW_DOCUMENT_VISIBILITY


def stamp_chunks_visibility(
    chunks: list[Any],
    visibility: str,
) -> list[Any]:
    """Проставляет ``visibility`` и ``document_visibility`` на каждый чанк до vector upsert."""
    from langchain_core.documents import Document

    vis = normalize_upload_visibility(visibility)
    out: list[Any] = []
    for d in chunks:
        meta = dict(d.metadata or {})
        meta["visibility"] = vis
        meta["document_visibility"] = vis
        out.append(Document(page_content=d.page_content, metadata=meta))
    return out


def visibility_label_from_metadata(meta: dict[str, Any]) -> str:
    """Метка для diagnostics / UI (без текста чанка)."""
    return effective_visibility(meta)
