"""
Сборка Chroma ``where`` до ``collection.query`` (P6.7).

Теги и сложные предикаты — в post-filter (``result_filter``), чтобы не зависеть
от версии операторов Chroma.
"""

from __future__ import annotations

from typing import Any

from services.retrieval_security.context import RetrievalSecurityContext


def build_chroma_where(ctx: RetrievalSecurityContext) -> dict[str, Any] | None:
    """
    Возвращает ``where`` для Chroma или None, если ограничений на уровне БД нет.

    Пустой ``allowed_sources`` (frozenset()) **не** порождает ``$in: []`` — Chroma
    падает с ValueError; такой случай обрабатывается post-filter (ноль результатов)
    без передачи ``where`` по источнику.
    """
    clauses: list[dict[str, Any]] = []

    if ctx.allowed_sources is not None and len(ctx.allowed_sources) > 0:
        src_list = sorted(ctx.allowed_sources)
        clauses.append({"source": {"$in": src_list}})

    for key, val in sorted(ctx.metadata_filters, key=lambda x: x[0]):
        k = str(key).strip()
        if not k:
            continue
        if isinstance(val, list):
            if len(val) == 0:
                continue
            clauses.append({k: {"$in": list(val)}})
            continue
        clauses.append({k: val})

    if ctx.allowed_visibility is not None and len(ctx.allowed_visibility) > 0:
        vis_list = sorted(ctx.allowed_visibility)
        if len(vis_list) == 1:
            clauses.append({"visibility": vis_list[0]})
        else:
            clauses.append({"visibility": {"$in": vis_list}})

    if not clauses:
        return None

    if len(clauses) == 1:
        where = clauses[0]
    else:
        where = {"$and": clauses}

    return where
