"""
Сборка Chroma ``where`` до ``collection.query`` (P6.7).

Теги и ``allowed_visibility`` — только в post-filter (``result_filter`` + PG enrich),
как Weaviate/FAISS: legacy Chroma metadata часто без ``visibility``, pre-filter давал
пустой retrieval (P9.6g-postfix).
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

    if not clauses:
        return None

    if len(clauses) == 1:
        where = clauses[0]
    else:
        where = {"$and": clauses}

    return where
