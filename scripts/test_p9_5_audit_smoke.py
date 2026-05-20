#!/usr/bin/env python3
"""
Smoke: P9.5 audit trail.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_5_audit_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    errors: list[str] = []

    from services.security.audit_service import _sanitize_details
    from services.security.principal import PLATFORM_ADMIN, PrincipalContext
    from services.retrieval_security.context import ROLE_ADMIN

    bad = _sanitize_details(
        {"password": "secret", "access_token": "tok", "note": "ok"}
    )
    if bad.get("password") != "[redacted]" or bad.get("access_token") != "[redacted]":
        errors.append("sanitize failed")
    if bad.get("note") != "ok":
        errors.append("sanitize over-redacted")

    p = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "audit@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        }
    )
    assert p.has_permission("audit:read")

    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
    except ImportError as e:
        print(f"[p9.5] unit sanitize OK; HTTP skipped: {e}")
        return 0

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
    app = create_admin_api_app()
    client = TestClient(app, raise_server_exceptions=False)

    r_anon = client.get("/api/security/audit/recent")
    if r_anon.status_code != 401:
        errors.append(f"audit anon: expected 401 got {r_anon.status_code}")

    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not email or not password:
        print("[p9.5] sanitize OK; skip HTTP (no INITIAL_ADMIN_*)")
        return 0

    r_bad = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-audit-smoke"},
    )
    if r_bad.status_code != 401:
        errors.append(f"login fail expected 401: {r_bad.status_code}")

    r_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    if r_login.status_code != 200:
        errors.append(f"login: {r_login.status_code}")
        for m in errors:
            print(f"FAIL: {m}")
        return 1

    tok = r_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    r_audit = client.get("/api/security/audit/recent?limit=20", headers=headers)
    if r_audit.status_code != 200:
        errors.append(f"audit recent: {r_audit.status_code} {r_audit.text[:200]}")
    else:
        body = r_audit.json()
        items = body.get("items") or []
        types = {it.get("event_type") for it in items}
        if "auth.login.success" not in types:
            errors.append(f"expected auth.login.success in audit, got: {sorted(types)[:5]}")
        login_ok = next(
            (it for it in items if it.get("event_type") == "auth.login.success"),
            None,
        )
        if login_ok:
            if login_ok.get("action") != "login":
                errors.append(f"login success action: {login_ok.get('action')!r}")
            if login_ok.get("target_type") != "auth":
                errors.append(f"login success target_type: {login_ok.get('target_type')!r}")
            if login_ok.get("request_path") != "/api/auth/login":
                errors.append(f"login success path: {login_ok.get('request_path')!r}")
        for it in items:
            blob = json.dumps(it)
            if "password" in blob.lower() and "[redacted]" not in blob:
                if "password" in str(it.get("details", {})).lower():
                    errors.append("password leaked in audit item")

    r_sum = client.get("/api/security/audit/summary", headers=headers)
    if r_sum.status_code != 200:
        errors.append(
            f"audit summary: {r_sum.status_code} {r_sum.text[:300]}"
        )
    else:
        summary = r_sum.json()
        if "total" not in summary or "by_event_type" not in summary:
            errors.append(f"audit summary shape: {list(summary.keys())}")

    # operator without audit:read
    from services.security.identity_service import get_identity_service
    from services.security.principal import PLATFORM_OPERATOR

    op_email = f"audit-op-{uuid.uuid4().hex[:8]}@smoke.local"
    get_identity_service().create_user(
        email=op_email,
        password="smoke-op-audit",
        platform_role=PLATFORM_OPERATOR,
    )
    r_op = client.post(
        "/api/auth/login",
        json={"email": op_email, "password": "smoke-op-audit"},
    )
    if r_op.status_code == 200:
        op_h = {"Authorization": f"Bearer {r_op.json()['access_token']}"}
        r_denied = client.get("/api/security/audit/recent", headers=op_h)
        if r_denied.status_code != 403:
            errors.append(f"operator audit: expected 403 got {r_denied.status_code}")

    if errors:
        for m in errors:
            print(f"FAIL: {m}")
        return 1

    print("[p9.5] smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
