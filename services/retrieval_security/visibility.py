"""
Нормализация visibility metadata чанков (P8.1).

Поддерживаются ключи ``visibility`` и ``document_visibility`` (alias).
"""

from __future__ import annotations

from typing import Any

VISIBILITY_PUBLIC = "public"
VISIBILITY_INTERNAL = "internal"
VISIBILITY_RESTRICTED = "restricted"
VISIBILITY_UNSPECIFIED = "unspecified"
# P9.6 alias: protected ≡ restricted (employee/internal KB scope label)
VISIBILITY_PROTECTED = VISIBILITY_RESTRICTED

# Retrieval scope labels (role → data plane)
SCOPE_PUBLIC = "public"
SCOPE_EMPLOYEE = "employee"
SCOPE_PROTECTED = "protected"
SCOPE_ADMIN = "admin"


def effective_visibility(meta: dict[str, Any]) -> str:
    """
    Единое значение visibility для политик retrieval (public/internal/restricted/unspecified).

    ``visibility_scope`` — scope label (employee/protected/…); не подменяет canonical
    ``visibility`` после PG-enrich (P9.6g-postfix).
    """
    for key in ("visibility", "document_visibility"):
        raw = meta.get(key)
        if raw is None:
            continue
        s = str(raw).strip().lower()
        if s:
            return s
    raw = meta.get("visibility_scope")
    if raw is not None:
        s = str(raw).strip().lower()
        if s in (
            VISIBILITY_PUBLIC,
            VISIBILITY_INTERNAL,
            VISIBILITY_RESTRICTED,
            VISIBILITY_UNSPECIFIED,
        ):
            return s
        if s == SCOPE_PROTECTED:
            return VISIBILITY_RESTRICTED
        if s == SCOPE_PUBLIC:
            return VISIBILITY_PUBLIC
    return VISIBILITY_UNSPECIFIED


def visibility_to_scope_label(visibility: str) -> str:
    """Map chunk visibility → P9.6 scope label (public/employee/protected/admin)."""
    v = (visibility or "").strip().lower()
    if v == VISIBILITY_PUBLIC:
        return SCOPE_PUBLIC
    if v == VISIBILITY_RESTRICTED:
        return SCOPE_PROTECTED
    if v in (VISIBILITY_INTERNAL, VISIBILITY_UNSPECIFIED):
        return SCOPE_EMPLOYEE
    return SCOPE_EMPLOYEE


def filter_documents_by_retrieval_context(
    docs: list[dict[str, Any]],
    ctx,
) -> list[dict[str, Any]]:
    """Admin documents list: hide chunks visibility outside role policy (P9.6)."""
    if ctx is None or ctx.allowed_visibility is None:
        return docs
    kept: list[dict[str, Any]] = []
    for doc in docs:
        vis = str(doc.get("document_visibility") or "unspecified").strip().lower()
        meta = {"visibility": vis, "document_visibility": vis}
        if document_visible_to_context(meta, ctx):
            kept.append(doc)
    return kept


def document_visible_to_context(meta: dict[str, Any], ctx) -> bool:
    """Whether document/chunk metadata is visible under RetrievalSecurityContext."""
    if ctx.allowed_visibility is None:
        return True
    if not ctx.allowed_visibility:
        return False
    return effective_visibility(meta) in ctx.allowed_visibility
