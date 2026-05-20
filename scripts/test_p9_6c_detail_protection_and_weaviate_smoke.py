#!/usr/bin/env python3
"""
P9.6c — detail protection + Weaviate reindex visibility consistency smoke.

  docker exec portfolio-test-admin-api-1 python scripts/test_p9_6c_detail_protection_and_weaviate_smoke.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return cond


def _visibility_distribution() -> dict[str, int]:
    from repositories.connection import get_connection
    from psycopg.rows import dict_row

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COALESCE(
                    NULLIF(TRIM(metadata->>'document_visibility'), ''),
                    NULLIF(TRIM(metadata->>'visibility'), ''),
                    'NULL'
                ) AS vis, COUNT(*)::int AS cnt
                FROM document_chunks GROUP BY 1 ORDER BY cnt DESC
                """
            )
            rows = cur.fetchall()
        conn.commit()
    return {str(r["vis"]): int(r["cnt"]) for r in rows}


def main() -> int:
    os.chdir(ROOT)
    failures = 0

    print("\n=== 1. Restricted detail protection (HTTP) ===")
    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
    except ImportError as exc:
        print(f"  skip HTTP: {exc}")
        return 1

    os.environ.setdefault("AF_AUTH_MIDDLEWARE_MODE", "required")
    client = TestClient(create_admin_api_app(), raise_server_exceptions=False)

    admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    admin_pass = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not admin_email or not admin_pass:
        print("  skip: INITIAL_ADMIN_* not set")
        return 1

    def login(email: str, password: str) -> str:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        return r.json().get("access_token", "") if r.status_code == 200 else ""

    admin_t = login(admin_email, admin_pass)
    op_t = login("sc-op-502e81f1@smoke.local", "sc-op-pass")
    aud_t = login("sc-aud-9c57c512@smoke.local", "sc-aud-pass")

    r_admin_list = client.get(
        "/api/documents?limit=400", headers={"Authorization": f"Bearer {admin_t}"}
    )
    restricted_id = None
    for it in r_admin_list.json().get("items") or []:
        if it.get("document_visibility") == "restricted":
            restricted_id = it.get("document_id")
            break

    if not restricted_id:
        print("  ⚠ no restricted doc — upload skipped in this env")
    else:
        r_ad = client.get(
            f"/api/documents/{restricted_id}/detail",
            headers={"Authorization": f"Bearer {admin_t}"},
        )
        if not _ok("admin restricted detail → 200", r_ad.status_code == 200):
            failures += 1
        r_op = client.get(
            f"/api/documents/{restricted_id}/detail",
            headers={"Authorization": f"Bearer {op_t}"},
        )
        if not _ok("operator restricted detail → 404", r_op.status_code == 404, str(r_op.status_code)):
            failures += 1
        r_aud = client.get(
            f"/api/documents/{restricted_id}/detail",
            headers={"Authorization": f"Bearer {aud_t}"},
        )
        if not _ok("auditor restricted detail → 404", r_aud.status_code == 404, str(r_aud.status_code)):
            failures += 1

    print("\n=== 2. Weaviate reindex visibility stability ===")
    from repositories.connection import get_connection
    from repositories.document_repository import DocumentRepository
    from services.admin_service import AdminService

    before = _visibility_distribution()
    print(f"  before: {before}")

    repo = DocumentRepository()
    svc = AdminService()
    target_id: uuid.UUID | None = None
    with get_connection() as conn:
        rows = repo.list_documents_with_version_summary(conn)
        conn.commit()
    for row in rows:
        fn = str(row.get("filename") or "")
        if fn == "p9_6b_restricted_handbook.txt":
            continue
        if str(row.get("document_visibility") or "") == "internal":
            target_id = row["document_id"]
            if not isinstance(target_id, uuid.UUID):
                target_id = uuid.UUID(str(target_id))
            break

    if target_id is None:
        print("  ⚠ no internal doc for reindex test")
    else:
        out = svc.reindex_document_file(target_id, reindex_log_kind="admin")
        if not _ok("single-doc reindex ok", bool(out.get("success")), str(out.get("error"))):
            failures += 1
        after = _visibility_distribution()
        print(f"  after:  {after}")
        if not _ok("internal count stable", before.get("internal", 0) == after.get("internal", 0)):
            failures += 1
        if not _ok(
            "restricted count stable",
            before.get("restricted", 0) == after.get("restricted", 0),
        ):
            failures += 1
        null_before = before.get("NULL", 0)
        null_after = after.get("NULL", 0)
        if not _ok("no visibility NULL growth", null_after <= null_before, f"{null_before}→{null_after}"):
            failures += 1

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
