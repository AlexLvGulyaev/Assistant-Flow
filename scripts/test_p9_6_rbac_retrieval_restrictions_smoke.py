#!/usr/bin/env python3
"""
P9.6 — RBAC + role-aware retrieval restrictions smoke.

  docker exec portfolio-test-admin-api-1 python scripts/test_p9_6_rbac_retrieval_restrictions_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return cond


def main() -> int:
    os.chdir(ROOT)
    failures = 0

    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
    from services.retrieval_security.principal_bridge import retrieval_security_from_principal
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import (
        VISIBILITY_INTERNAL,
        VISIBILITY_PUBLIC,
        VISIBILITY_RESTRICTED,
        VISIBILITY_UNSPECIFIED,
        effective_visibility,
        filter_documents_by_retrieval_context,
        visibility_to_scope_label,
    )
    from services.security.principal import PrincipalContext
    from services.security.rbac import (
        PERM_AUDIT_READ,
        PERM_RETRIEVAL_ADMIN,
        PLATFORM_ADMIN,
        PLATFORM_AUDITOR,
        PLATFORM_OPERATOR,
        retrieval_role_for_platform,
    )

    mixed = [
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="p",
                metadata={"source": "a.md", "visibility": VISIBILITY_PUBLIC},
            ),
            score=0.1,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="i",
                metadata={"source": "b.md", "visibility": VISIBILITY_INTERNAL},
            ),
            score=0.2,
        ),
        RetrievalSearchResult(
            chunk=RetrievalChunk(
                page_content="r",
                metadata={"source": "c.md", "visibility": VISIBILITY_RESTRICTED},
            ),
            score=0.3,
        ),
    ]

    print("\n=== 1. Role matrix (retrieval chunks) ===")
    guest = build_retrieval_security_context_for_role(ROLE_GUEST)
    emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
    adm = build_retrieval_security_context_for_role(ROLE_ADMIN)

    g = filter_search_results_by_security(list(mixed), guest)
    if not _ok("guest → public only", len(g) == 1):
        failures += 1

    e = filter_search_results_by_security(list(mixed), emp)
    e_vis = {effective_visibility(r.chunk.metadata) for r in e}
    if not _ok("employee → no restricted", VISIBILITY_RESTRICTED not in e_vis, str(sorted(e_vis))):
        failures += 1

    a = filter_search_results_by_security(list(mixed), adm)
    if not _ok("admin → all chunks", len(a) == 3):
        failures += 1

    print("\n=== 2. RBAC permissions ===")
    p_op = PrincipalContext.from_user_row(
        {"id": "00000000-0000-0000-0000-000000000099", "platform_role": PLATFORM_OPERATOR, "email": "op@t"},
        auth_source="bearer",
    )
    p_aud = PrincipalContext.from_user_row(
        {"id": "00000000-0000-0000-0000-000000000098", "platform_role": PLATFORM_AUDITOR, "email": "aud@t"},
        auth_source="bearer",
    )
    if not _ok("operator lacks audit:read", not p_op.has_permission(PERM_AUDIT_READ)):
        failures += 1
    if not _ok("auditor has audit:read", p_aud.has_permission(PERM_AUDIT_READ)):
        failures += 1
    if not _ok("auditor lacks retrieval:admin", not p_aud.has_permission(PERM_RETRIEVAL_ADMIN)):
        failures += 1

    print("\n=== 3. Documents list filter ===")
    docs = [
        {"filename": "pub.md", "document_visibility": "public"},
        {"filename": "int.md", "document_visibility": "internal"},
        {"filename": "sec.md", "document_visibility": "restricted"},
    ]
    op_ctx = retrieval_security_from_principal(p_op)
    op_docs = filter_documents_by_retrieval_context(docs, op_ctx)
    op_names = {d["filename"] for d in op_docs}
    if not _ok("operator docs hide restricted", "sec.md" not in op_names, str(op_names)):
        failures += 1

    print("\n=== 4. visibility_scope label ===")
    if not _ok(
        "restricted → protected scope",
        visibility_to_scope_label(VISIBILITY_RESTRICTED) == "protected",
    ):
        failures += 1

    print("\n=== 5. Audit on filter (DB optional) ===")
    try:
        from services.security.audit_service import get_audit_service

        ctx = build_retrieval_security_context_for_role(ROLE_GUEST)
        ctx = type(ctx)(
            role=ctx.role,
            allowed_sources=ctx.allowed_sources,
            retrieval_scope=ctx.retrieval_scope,
            metadata_filters=ctx.metadata_filters,
            required_tags=ctx.required_tags,
            allowed_visibility=ctx.allowed_visibility,
            audit_email="smoke@guest.local",
            audit_platform_role="guest",
        )
        filter_search_results_by_security(list(mixed), ctx)
        rows = get_audit_service().get_recent(
            limit=5, event_type="retrieval.protected_chunk.denied", since_hours=1
        )
        if not _ok("audit retrieval.protected_chunk.denied", len(rows) >= 1, f"rows={len(rows)}"):
            failures += 1
    except Exception as exc:
        print(f"  ⚠ audit DB skip: {exc}")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
