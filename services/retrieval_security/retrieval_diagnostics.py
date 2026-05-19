"""
Агрегаты visibility для RAG diagnostics (P8.2). Без PII — только счётчики меток.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

from services.retrieval_security.visibility import effective_visibility


def visibility_distribution(
    pairs: Sequence[tuple[Any, float]],
) -> dict[str, int]:
    """Распределение visibility по списку чанков retrieval."""
    c: Counter[str] = Counter()
    for doc, _ in pairs:
        meta = dict(getattr(doc, "metadata", None) or {})
        c[effective_visibility(meta)] += 1
    if not c:
        return {}
    return dict(sorted(c.items()))


def build_retrieval_security_summary(
    *,
    security_role: str | None,
    retrieval_scope: str | None,
    retrieved_count: int,
    filtered_count: int,
    visibility_before: dict[str, int],
    visibility_after_relevance: dict[str, int],
    security_filtered_count: int | None = None,
) -> dict[str, object]:
    """Краткая сводка для ``processing_logs.details`` (без тел чанков)."""
    out: dict[str, object] = {
        "security_role": security_role,
        "retrieval_scope": retrieval_scope,
        "retrieved_count": int(retrieved_count),
        "filtered_count": int(filtered_count),
    }
    if visibility_before:
        out["visibility_distribution_retrieved"] = visibility_before
    if visibility_after_relevance:
        out["visibility_distribution_kept"] = visibility_after_relevance
    if security_filtered_count is not None and security_filtered_count > 0:
        out["security_filtered_count"] = int(security_filtered_count)
    return out
