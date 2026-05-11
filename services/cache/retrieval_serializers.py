"""Сериализация RetrievalSearchResult ↔ JSON для SQLite cache."""

from __future__ import annotations

from typing import Any

from services.retrieval.base import RetrievalChunk, RetrievalSearchResult


def serialize_search_results(results: list[RetrievalSearchResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        out.append(
            {
                "page_content": r.chunk.page_content,
                "metadata": dict(r.chunk.metadata),
                "score": float(r.score),
            }
        )
    return out


def deserialize_search_results(raw: Any) -> list[RetrievalSearchResult]:
    if not isinstance(raw, list):
        return []
    out: list[RetrievalSearchResult] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        page = str(row.get("page_content") or "")
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        try:
            sc = float(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(
            RetrievalSearchResult(
                chunk=RetrievalChunk(page_content=page, metadata=dict(meta)),
                score=sc,
            )
        )
    return out
