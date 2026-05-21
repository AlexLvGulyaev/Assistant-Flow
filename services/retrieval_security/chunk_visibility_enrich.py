"""
Resolve missing chunk visibility before post-retrieval security filter (P9.6g).

Weaviate (and legacy vectors) may omit ``visibility`` in stored/returned metadata;
without enrichment restricted chunks appear as ``unspecified`` and pass employee policy.
"""

from __future__ import annotations

import uuid
from typing import Any

from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
from services.retrieval_security.context import RetrievalSecurityContext
from services.retrieval_security.visibility import (
    VISIBILITY_UNSPECIFIED,
    effective_visibility,
    visibility_to_scope_label,
)


def enrich_search_results_visibility_metadata(
    results: list[RetrievalSearchResult],
    ctx: RetrievalSecurityContext,
) -> list[RetrievalSearchResult]:
    """
    Return results with visibility stamped from PostgreSQL when vector metadata lacks it.
    """
    if ctx.is_fully_unrestricted() or ctx.allowed_visibility is None:
        return results

    need_ids: list[uuid.UUID] = []
    seen: set[str] = set()
    for r in results:
        meta = r.chunk.metadata
        if effective_visibility(meta) != VISIBILITY_UNSPECIFIED:
            continue
        raw_id = str(meta.get("document_id") or "").strip()
        if not raw_id or raw_id in seen:
            continue
        try:
            need_ids.append(uuid.UUID(raw_id))
            seen.add(raw_id)
        except ValueError:
            continue

    if not need_ids:
        return results

    vis_map = _load_visibility_by_document_ids(need_ids)
    if not vis_map:
        return results

    enriched: list[RetrievalSearchResult] = []
    for r in results:
        meta = dict(r.chunk.metadata)
        if effective_visibility(meta) == VISIBILITY_UNSPECIFIED:
            doc_id = str(meta.get("document_id") or "").strip()
            vis = vis_map.get(doc_id)
            if vis:
                meta["visibility"] = vis
                meta["document_visibility"] = vis
                meta["visibility_scope"] = visibility_to_scope_label(vis)
        enriched.append(
            RetrievalSearchResult(
                chunk=RetrievalChunk(page_content=r.chunk.page_content, metadata=meta),
                score=r.score,
            )
        )
    return enriched


def _load_visibility_by_document_ids(document_ids: list[uuid.UUID]) -> dict[str, str]:
    db_url = ""
    try:
        from utils.config import load_config

        db_url = (load_config().database_url or "").strip()
    except Exception:
        return {}
    if not db_url:
        return {}
    try:
        from repositories.connection import get_connection
        from repositories.document_repository import DocumentRepository

        with get_connection() as conn:
            repo = DocumentRepository()
            vis_map = repo.get_visibility_for_document_ids(conn, document_ids)
            conn.commit()
        return vis_map
    except Exception:
        return {}
