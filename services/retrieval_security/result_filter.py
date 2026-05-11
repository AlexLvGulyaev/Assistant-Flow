"""
Post-retrieval фильтр (вторая линия защиты) + согласование тегов.

Основное ограничение источников — Chroma ``where`` до query; здесь отсекаем
аномалии и поля, не попавшие в where (теги).
"""

from __future__ import annotations

from typing import Any

from services.retrieval.base import RetrievalSearchResult
from services.retrieval_security.context import RetrievalSecurityContext
from services.retrieval_security.telemetry import emit_retrieval_security_event


def _chunk_tags(meta: dict[str, Any]) -> frozenset[str]:
    raw = meta.get("tags")
    if raw is None:
        return frozenset()
    if isinstance(raw, (list, tuple, set)):
        out: set[str] = set()
        for t in raw:
            s = str(t).strip()
            if s:
                out.add(s)
        return frozenset(out)
    s = str(raw).strip()
    return frozenset({s}) if s else frozenset()


def _allowed_by_sources(meta: dict[str, Any], ctx: RetrievalSecurityContext) -> bool:
    if ctx.allowed_sources is None:
        return True
    src = str(meta.get("source") or "").strip()
    return src in ctx.allowed_sources


def _allowed_by_metadata_filters(meta: dict[str, Any], ctx: RetrievalSecurityContext) -> bool:
    for key, expected in ctx.metadata_filters:
        actual = meta.get(key)
        if actual is None:
            return False
        if str(actual).strip() != str(expected).strip():
            return False
    return True


def _allowed_by_required_tags(meta: dict[str, Any], ctx: RetrievalSecurityContext) -> bool:
    if not ctx.required_tags:
        return True
    tags = _chunk_tags(meta)
    return ctx.required_tags.issubset(tags)


def filter_search_results_by_security(
    results: list[RetrievalSearchResult],
    ctx: RetrievalSecurityContext,
) -> list[RetrievalSearchResult]:
    """
    Отбрасывает чанки, не проходящие политику. Порядок ранжирования сохраняется.
    """
    if ctx.is_fully_unrestricted():
        return results

    kept: list[RetrievalSearchResult] = []
    denied_source = 0
    denied_other = 0

    for r in results:
        meta = dict(r.chunk.metadata)
        if not _allowed_by_sources(meta, ctx):
            denied_source += 1
            emit_retrieval_security_event(
                "retrieval_denied_source",
                role=ctx.role,
                retrieval_scope=ctx.retrieval_scope,
                source=str(meta.get("source") or "")[:120],
            )
            continue
        if not _allowed_by_metadata_filters(meta, ctx):
            denied_other += 1
            continue
        if not _allowed_by_required_tags(meta, ctx):
            denied_other += 1
            continue
        kept.append(r)

    dropped = len(results) - len(kept)
    if dropped:
        emit_retrieval_security_event(
            "retrieval_filtered",
            role=ctx.role,
            retrieval_scope=ctx.retrieval_scope,
            dropped_total=dropped,
            denied_source=denied_source,
            denied_other=denied_other,
            kept=len(kept),
        )
    return kept
