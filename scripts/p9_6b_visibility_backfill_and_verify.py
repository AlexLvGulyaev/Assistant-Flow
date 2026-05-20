#!/usr/bin/env python3
"""
P9.6b — visibility backfill (legacy corpus) + bounded per-document reindex + runtime verification.

Запуск (portfolio-test):

  docker exec portfolio-test-admin-api-1 python scripts/p9_6b_visibility_backfill_and_verify.py --all
  docker exec portfolio-test-admin-api-1 python scripts/p9_6b_visibility_backfill_and_verify.py --backfill
  docker exec portfolio-test-admin-api-1 python scripts/p9_6b_visibility_backfill_and_verify.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESTRICTED_FILENAME = "p9_6b_restricted_handbook.txt"
RESTRICTED_MARKER = "P9.6B_RESTRICTED_VERIFICATION_DOC"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return cond


def _visibility_distribution(conn) -> dict[str, int]:
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                COALESCE(
                    NULLIF(TRIM(metadata->>'document_visibility'), ''),
                    NULLIF(TRIM(metadata->>'visibility'), ''),
                    'NULL'
                ) AS vis,
                COUNT(*)::int AS cnt
            FROM document_chunks
            GROUP BY 1
            ORDER BY cnt DESC
            """
        )
        return {str(r["vis"]): int(r["cnt"]) for r in cur.fetchall()}


def backfill_postgres(*, dry_run: bool = False) -> dict[str, Any]:
    from repositories.connection import get_connection

    sql_preview = """
        SELECT COUNT(*)::int AS n
        FROM document_chunks
        WHERE (
            metadata->>'visibility' IS NULL OR TRIM(metadata->>'visibility') = ''
        )
        AND (
            metadata->>'document_visibility' IS NULL OR TRIM(metadata->>'document_visibility') = ''
        )
    """
    sql_update = """
        UPDATE document_chunks
        SET metadata = metadata
            || jsonb_build_object(
                'visibility', 'internal',
                'document_visibility', 'internal'
            )
            || CASE
                WHEN metadata->>'visibility_scope' IS NULL
                  OR TRIM(metadata->>'visibility_scope') = ''
                THEN jsonb_build_object('visibility_scope', 'employee')
                ELSE '{}'::jsonb
            END
        WHERE (
            metadata->>'visibility' IS NULL OR TRIM(metadata->>'visibility') = ''
        )
        AND (
            metadata->>'document_visibility' IS NULL OR TRIM(metadata->>'document_visibility') = ''
        )
    """
    with get_connection() as conn:
        before = _visibility_distribution(conn)
        with conn.cursor() as cur:
            cur.execute(sql_preview)
            to_update = int(cur.fetchone()[0])
        if dry_run:
            conn.rollback()
            return {"dry_run": True, "would_update": to_update, "before": before}
        with conn.cursor() as cur:
            cur.execute(sql_update)
            updated = cur.rowcount
        conn.commit()
        after = _visibility_distribution(conn)
    return {"updated": updated, "before": before, "after": after}


def reindex_all_documents() -> dict[str, Any]:
    from repositories.connection import get_connection
    from repositories.document_repository import DocumentRepository
    from services.admin_service import AdminService

    svc = AdminService()
    repo = DocumentRepository()
    results: list[dict[str, Any]] = []
    with get_connection() as conn:
        rows = repo.list_documents_with_version_summary(conn)
        conn.commit()
    doc_ids = [r["document_id"] for r in rows if r.get("document_id")]
    ok = 0
    fail = 0
    for doc_id in doc_ids:
        uid = doc_id if isinstance(doc_id, uuid.UUID) else uuid.UUID(str(doc_id))
        out = svc.reindex_document_file(uid, reindex_log_kind="admin")
        entry = {
            "document_id": str(uid),
            "success": bool(out.get("success")),
            "chunks": out.get("chunks"),
            "error": out.get("error"),
        }
        results.append(entry)
        if entry["success"]:
            ok += 1
        else:
            fail += 1
            print(f"  ⚠ reindex {uid}: {entry['error']}")
    return {"total": len(doc_ids), "ok": ok, "fail": fail, "results": results}


def upload_restricted_verification_doc() -> dict[str, Any]:
    from services.admin_service import AdminService

    svc = AdminService()
    body = (
        f"{RESTRICTED_MARKER}\n\n"
        "Внутренний employee handbook (restricted verification document).\n"
        "Содержит конфиденциальные HR policy notes для P9.6b runtime checks.\n"
    ).encode("utf-8")
    result = svc.upload_txt_and_index(
        RESTRICTED_FILENAME,
        body,
        document_visibility="restricted",
    )
    return result


def _login_token(client, email: str, password: str) -> str | None:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


def verify_runtime(*, skip_detail: bool = False) -> int:
    failures = 0
    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
    except ImportError as exc:
        print(f"verify skipped: {exc}")
        return 1

    os.environ.setdefault("AF_AUTH_MIDDLEWARE_MODE", "required")
    app = create_admin_api_app()
    client = TestClient(app, raise_server_exceptions=False)

    admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    admin_pass = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not admin_email or not admin_pass:
        print("verify: INITIAL_ADMIN_* not set")
        return 1

    admin_t = _login_token(client, admin_email, admin_pass)
    op_t = _login_token(client, "sc-op-502e81f1@smoke.local", "sc-op-pass")
    aud_t = _login_token(client, "sc-aud-9c57c512@smoke.local", "sc-aud-pass")
    if not all([admin_t, op_t, aud_t]):
        print("verify: login failed for one of roles")
        return 1

    def doc_counts(token: str) -> tuple[int, set[str]]:
        r = client.get("/api/documents?limit=400", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            return -1, set()
        items = r.json().get("items") or []
        vis = {str(x.get("document_visibility") or "?") for x in items}
        return len(items), vis

    print("\n=== Runtime verification: documents list ===")
    admin_n, admin_vis = doc_counts(admin_t)
    op_n, op_vis = doc_counts(op_t)
    aud_n, aud_vis = doc_counts(aud_t)
    if not _ok("admin documents >= operator", admin_n >= op_n, f"admin={admin_n} op={op_n}"):
        failures += 1
    if not _ok("operator sees internal corpus", op_n > 0, f"count={op_n} vis={sorted(op_vis)}"):
        failures += 1
    if not _ok(
        "admin sees restricted visibility",
        "restricted" in admin_vis,
        f"vis={sorted(admin_vis)}",
    ):
        failures += 1
    if not _ok(
        "operator hides restricted",
        "restricted" not in op_vis and op_n < admin_n,
        f"op={op_n} admin={admin_n} op_vis={sorted(op_vis)}",
    ):
        failures += 1
    if not _ok(
        "auditor hides restricted",
        "restricted" not in aud_vis and aud_n == op_n,
        f"aud={aud_n} vis={sorted(aud_vis)}",
    ):
        failures += 1

    print("\n=== Retrieval filter (unit with live PG sample) ===")
    from repositories.connection import get_connection
    from psycopg.rows import dict_row
    from services.retrieval.base import RetrievalChunk, RetrievalSearchResult
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role
    from services.retrieval_security.result_filter import filter_search_results_by_security
    from services.retrieval_security.visibility import VISIBILITY_INTERNAL, VISIBILITY_RESTRICTED

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT metadata
                FROM document_chunks
                WHERE metadata->>'document_visibility' = 'restricted'
                LIMIT 1
                """
            )
            row = cur.fetchone()
        conn.commit()
    if row:
        restricted_meta = dict(row["metadata"])
        mixed = [
            RetrievalSearchResult(
                chunk=RetrievalChunk(page_content="i", metadata={"visibility": VISIBILITY_INTERNAL}),
                score=0.1,
            ),
            RetrievalSearchResult(
                chunk=RetrievalChunk(page_content="r", metadata=restricted_meta),
                score=0.2,
            ),
        ]
        emp = build_retrieval_security_context_for_role(ROLE_EMPLOYEE)
        adm = build_retrieval_security_context_for_role(ROLE_ADMIN)
        emp_out = filter_search_results_by_security(list(mixed), emp)
        adm_out = filter_search_results_by_security(list(mixed), adm)
        if not _ok("employee filter drops restricted chunk", len(emp_out) == 1):
            failures += 1
        if not _ok("admin keeps restricted chunk", len(adm_out) == 2):
            failures += 1
    else:
        print("  ⚠ no restricted chunk in PG for filter test")

    print("\n=== Audit retrieval deny ===")
    from services.security.audit_service import get_audit_service

    rows = get_audit_service().get_recent(
        limit=5, event_type="retrieval.protected_chunk.denied", since_hours=24
    )
    if not _ok("retrieval.protected_chunk.denied in audit", len(rows) >= 1, f"rows={len(rows)}"):
        failures += 1

    if not skip_detail:
        print("\n=== Document detail (confirmed defect check) ===")
        r_admin = client.get("/api/documents?limit=400", headers={"Authorization": f"Bearer {admin_t}"})
        restricted_id = None
        for it in r_admin.json().get("items") or []:
            if it.get("document_visibility") == "restricted":
                restricted_id = it.get("document_id")
                break
        if restricted_id:
            r_op_detail = client.get(
                f"/api/documents/{restricted_id}/detail",
                headers={"Authorization": f"Bearer {op_t}"},
            )
        if not _ok(
            "operator restricted detail → 404 (P9.6c)",
            r_op_detail.status_code == 404,
            f"HTTP {r_op_detail.status_code}",
        ):
            failures += 1
        else:
            print("  ⚠ restricted doc id not found for detail check")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failed)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="P9.6b visibility backfill + verify")
    parser.add_argument("--backfill", action="store_true", help="SQL backfill only")
    parser.add_argument("--reindex", action="store_true", help="Per-document reindex")
    parser.add_argument("--upload-restricted", action="store_true", help="Upload restricted test doc")
    parser.add_argument("--verify-only", action="store_true", help="Runtime verification only")
    parser.add_argument("--all", action="store_true", help="backfill + reindex + upload + verify")
    parser.add_argument("--dry-run", action="store_true", help="Backfill dry-run")
    args = parser.parse_args()

    if not any(
        [args.backfill, args.reindex, args.upload_restricted, args.verify_only, args.all]
    ):
        args.all = True

    os.chdir(ROOT)
    failures = 0

    if args.all or args.backfill:
        print("\n=== A. PostgreSQL visibility backfill ===")
        out = backfill_postgres(dry_run=args.dry_run)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if args.dry_run:
            return 0

    if args.all or args.reindex:
        print("\n=== B. Bounded per-document reindex (vector sync) ===")
        rep = reindex_all_documents()
        print(
            f"  reindexed {rep['ok']}/{rep['total']} ok, failures={rep['fail']}"
        )
        if rep["fail"]:
            failures += 1
        # Weaviate single-file path rebuilds full corpus; non-target files lose stamped
        # visibility in PG during _index_one_file. Re-apply SQL backfill (idempotent).
        print("\n=== B2. Post-reindex PG backfill (Weaviate side-effect mitigation) ===")
        post = backfill_postgres(dry_run=False)
        print(json.dumps(post, ensure_ascii=False, indent=2))

    if args.all or args.upload_restricted:
        print("\n=== C. Restricted verification document ===")
        up = upload_restricted_verification_doc()
        print(json.dumps({k: up.get(k) for k in ("success", "filename", "document_visibility", "error")}, ensure_ascii=False))
        if not up.get("success"):
            failures += 1

    if args.all or args.verify_only:
        failures += verify_runtime()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
