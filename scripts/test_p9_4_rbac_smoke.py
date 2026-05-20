#!/usr/bin/env python3
"""
Smoke: P9.4 real RBAC — permissions, route enforcement, retrieval bridge.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_4_rbac_smoke.py
"""

from __future__ import annotations

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

    from services.security.rbac import (
        PERM_AUDIT_READ,
        PERM_DOCUMENTS_REINDEX,
        PERM_DOCUMENTS_WRITE,
        PERM_LOGS_FORENSIC,
        PERM_LOGS_READ,
        PERM_RETRIEVAL_ADMIN,
        PERM_SETTINGS_WRITE,
        PERM_USERS_WRITE,
        expand_permissions_for_response,
        resolve_permissions,
        retrieval_role_for_platform,
    )
    from services.security.principal import (
        PLATFORM_ADMIN,
        PLATFORM_AUDITOR,
        PLATFORM_EMPLOYEE,
        PLATFORM_OPERATOR,
        PLATFORM_SUPERADMIN,
        PrincipalContext,
    )
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST
    from services.retrieval_security.principal_bridge import retrieval_security_from_principal

    admin_perms = resolve_permissions(PLATFORM_ADMIN)
    assert PERM_DOCUMENTS_WRITE in admin_perms
    assert PERM_DOCUMENTS_REINDEX in admin_perms
    assert PERM_RETRIEVAL_ADMIN in admin_perms
    assert PERM_SETTINGS_WRITE in admin_perms

    op_perms = resolve_permissions(PLATFORM_OPERATOR)
    assert PERM_DOCUMENTS_WRITE in op_perms
    assert PERM_LOGS_READ in op_perms
    assert PERM_RETRIEVAL_ADMIN not in op_perms
    assert PERM_SETTINGS_WRITE not in op_perms

    aud_perms = resolve_permissions(PLATFORM_AUDITOR)
    assert PERM_LOGS_FORENSIC in aud_perms
    assert PERM_DOCUMENTS_WRITE not in aud_perms

    assert len(resolve_permissions(PLATFORM_EMPLOYEE)) == 0

    sa = resolve_permissions(PLATFORM_SUPERADMIN)
    assert PERM_USERS_WRITE in sa
    assert PERM_SETTINGS_WRITE in sa
    assert PERM_DOCUMENTS_REINDEX in sa
    expanded_sa = expand_permissions_for_response(
        frozenset({"*"})
    )
    assert PERM_USERS_WRITE in expanded_sa

    p_admin = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "rbac-admin@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        }
    )
    assert p_admin.has_permission(PERM_DOCUMENTS_WRITE)
    assert p_admin.has_any_permission(PERM_LOGS_READ, PERM_AUDIT_READ)
    ctx = retrieval_security_from_principal(p_admin)
    assert ctx is not None and ctx.is_fully_unrestricted()

    assert retrieval_role_for_platform(PLATFORM_ADMIN) == ROLE_ADMIN
    assert retrieval_role_for_platform("end_user") == ROLE_GUEST
    assert retrieval_role_for_platform(PLATFORM_OPERATOR) == ROLE_EMPLOYEE

    p_op = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "rbac-op@test.local",
            "platform_role": PLATFORM_OPERATOR,
            "status": "active",
        }
    )
    assert p_op.retrieval_role == ROLE_EMPLOYEE
    assert not p_op.has_permission(PERM_RETRIEVAL_ADMIN)

    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
        from services.security.identity_service import get_identity_service
    except ImportError as e:
        print(f"[p9.4] unit checks OK; HTTP skipped: {e}")
        return 0

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
    app = create_admin_api_app()
    client = TestClient(app, raise_server_exceptions=False)

    r_anon = client.get("/api/logs/recent?limit=1")
    if r_anon.status_code != 401:
        errors.append(f"anon logs: expected 401 got {r_anon.status_code}")

    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if email and password:
        r_login = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        if r_login.status_code != 200:
            errors.append(f"admin login: {r_login.status_code}")
        else:
            tok = r_login.json().get("access_token")
            headers = {"Authorization": f"Bearer {tok}"}
            me = client.get("/api/auth/me", headers=headers).json()
            if not me.get("authenticated"):
                errors.append("me not authenticated")
            perms = me.get("permissions") or []
            if PERM_DOCUMENTS_WRITE not in perms:
                errors.append(f"admin me permissions: {perms[:12]}")
            r_logs = client.get("/api/logs/recent?limit=1", headers=headers)
            if r_logs.status_code not in (200, 404):
                errors.append(f"admin logs: {r_logs.status_code}")

    op_email = f"rbac-operator-{uuid.uuid4().hex[:8]}@smoke.local"
    op_pass = "smoke-op-pass-9"
    try:
        get_identity_service().create_user(
            email=op_email,
            password=op_pass,
            platform_role=PLATFORM_OPERATOR,
        )
        r_op_login = client.post(
            "/api/auth/login",
            json={"email": op_email, "password": op_pass},
        )
        if r_op_login.status_code != 200:
            errors.append(f"operator login: {r_op_login.status_code}")
        else:
            op_headers = {
                "Authorization": f"Bearer {r_op_login.json()['access_token']}"
            }
            r_op_logs = client.get("/api/logs/recent?limit=1", headers=op_headers)
            if r_op_logs.status_code not in (200, 404):
                errors.append(f"operator logs: {r_op_logs.status_code}")
            r_op_tune = client.put(
                "/api/retrieval/tuning",
                headers=op_headers,
                json={"rag_top_k": 3},
            )
            if r_op_tune.status_code != 403:
                errors.append(
                    f"operator tuning: expected 403 got {r_op_tune.status_code}"
                )
    except Exception as exc:
        errors.append(f"operator fixture: {exc}")

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}")
        return 1

    print("[p9.4] smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
