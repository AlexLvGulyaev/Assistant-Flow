#!/usr/bin/env python3
"""
P9.5b — smoke security scenarios (narrative report).

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_5b_security_scenarios.py
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


def _section(title: str) -> None:
    print(f"\n{'=' * 56}")
    print(title)
    print("=" * 56)


def _step(name: str, ok: bool, detail: str) -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}")
    for line in detail.strip().splitlines():
        print(f"      {line}")
    return ok


def main() -> int:
    os.chdir(ROOT)
    failures = 0

    from services.security.rbac import (
        PERM_AUDIT_READ,
        PERM_DOCUMENTS_WRITE,
        PERM_RETRIEVAL_ADMIN,
        retrieval_role_for_platform,
    )
    from services.security.principal import (
        PLATFORM_ADMIN,
        PLATFORM_AUDITOR,
        PLATFORM_EMPLOYEE,
        PLATFORM_END_USER,
        PLATFORM_OPERATOR,
        PrincipalContext,
    )
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST
    from services.retrieval_security.principal_bridge import retrieval_security_from_principal
    from services.retrieval_security.policy_resolver import build_retrieval_security_context_for_role

    _section("1. Retrieval role bridge (unit)")
    for platform, expected in [
        (PLATFORM_ADMIN, ROLE_ADMIN),
        (PLATFORM_OPERATOR, ROLE_EMPLOYEE),
        (PLATFORM_END_USER, ROLE_GUEST),
    ]:
        got = retrieval_role_for_platform(platform)
        if not _step(
            f"platform {platform} → retrieval {expected}",
            got == expected,
            f"получено: {got}",
        ):
            failures += 1

    guest_ctx = build_retrieval_security_context_for_role(ROLE_GUEST)
    if not _step(
        "guest visibility = public only",
        guest_ctx.allowed_visibility == frozenset({"public"}),
        f"allowed: {sorted(guest_ctx.allowed_visibility or [])}",
    ):
        failures += 1

    _section("2. RBAC principals (unit)")
    p_admin = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "sc-admin@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        }
    )
    p_op = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "sc-operator@test.local",
            "platform_role": PLATFORM_OPERATOR,
            "status": "active",
        }
    )
    p_aud = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "sc-auditor@test.local",
            "platform_role": PLATFORM_AUDITOR,
            "status": "active",
        }
    )
    p_emp = PrincipalContext.from_user_row(
        {
            "id": str(uuid.uuid4()),
            "email": "sc-employee@test.local",
            "platform_role": PLATFORM_EMPLOYEE,
            "status": "active",
        }
    )

    if not _step(
        "admin: documents + audit",
        p_admin.has_permission(PERM_DOCUMENTS_WRITE) and p_admin.has_permission(PERM_AUDIT_READ),
        "operator-level privileged actions разрешены",
    ):
        failures += 1
    if not _step(
        "operator: нет retrieval:admin",
        not p_op.has_permission(PERM_RETRIEVAL_ADMIN),
        f"retrieval_role={p_op.retrieval_role}",
    ):
        failures += 1
    if not _step(
        "auditor: audit:read, без documents:write",
        p_aud.has_permission(PERM_AUDIT_READ) and not p_aud.has_permission(PERM_DOCUMENTS_WRITE),
        "read-only security observability",
    ):
        failures += 1
    if not _step(
        "employee: нет platform permissions",
        len(p_emp.permissions) == 0,
        "guest/end_user — только retrieval bridge",
    ):
        failures += 1

    rs_admin = retrieval_security_from_principal(p_admin)
    if not _step(
        "admin retrieval bridge unrestricted",
        rs_admin is not None and rs_admin.is_fully_unrestricted(),
        "P8 permissive context",
    ):
        failures += 1

    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
        from services.security.identity_service import get_identity_service
    except ImportError as exc:
        print(f"\n[p9.5b] HTTP skipped: {exc}")
        print(f"\nИтог: unit-only, failures={failures}")
        return 1 if failures else 0

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
    app = create_admin_api_app()
    client = TestClient(app, raise_server_exceptions=False)
    id_svc = get_identity_service()

    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not email or not password:
        print("\n[p9.5b] skip HTTP: no INITIAL_ADMIN_*")
        return 1 if failures else 0

    _section("3. Auth scenarios (HTTP)")

    r_fail = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-p9-5b-scenario"},
    )
    if not _step(
        "failed login → 401",
        r_fail.status_code == 401,
        "ожидался отказ без выдачи токена",
    ):
        failures += 1

    r_login = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    if r_login.status_code != 200:
        _step("successful login", False, f"status {r_login.status_code}")
        return 1
    tok = r_login.json()["access_token"]
    admin_h = {"Authorization": f"Bearer {tok}"}
    if not _step(
        "successful login → 200 + token",
        bool(tok),
        "сессия выдана; audit auth.login.success ожидается в recent",
    ):
        failures += 1

    r_bad = client.get("/api/security/audit/recent?limit=5")
    if not _step(
        "invalid token / anon → audit 401",
        r_bad.status_code == 401,
        "security.access.denied в audit при попытках к защищённым API",
    ):
        failures += 1

    r_invalid = client.get(
        "/api/security/audit/recent?limit=5",
        headers={"Authorization": "Bearer invalid-token-p9-5b"},
    )
    if not _step(
        "invalid bearer → 401",
        r_invalid.status_code == 401,
        "токен не принят middleware",
    ):
        failures += 1

    _section("4. RBAC + audit visibility (HTTP)")

    op_email = f"sc-op-{uuid.uuid4().hex[:8]}@smoke.local"
    aud_email = f"sc-aud-{uuid.uuid4().hex[:8]}@smoke.local"
    id_svc.create_user(
        email=op_email, password="sc-op-pass", platform_role=PLATFORM_OPERATOR
    )
    id_svc.create_user(
        email=aud_email, password="sc-aud-pass", platform_role=PLATFORM_AUDITOR
    )

    r_op = client.post(
        "/api/auth/login", json={"email": op_email, "password": "sc-op-pass"}
    )
    r_aud = client.post(
        "/api/auth/login", json={"email": aud_email, "password": "sc-aud-pass"}
    )
    op_h = {"Authorization": f"Bearer {r_op.json()['access_token']}"}
    aud_h = {"Authorization": f"Bearer {r_aud.json()['access_token']}"}

    r_op_tune = client.put(
        "/api/retrieval/tuning", headers=op_h, json={"rag_top_k": 4}
    )
    if not _step(
        "operator: retrieval settings denied → 403",
        r_op_tune.status_code == 403,
        "permission retrieval:admin отсутствует; audit security.permission.denied",
    ):
        failures += 1

    r_op_audit = client.get("/api/security/audit/recent?limit=5", headers=op_h)
    if not _step(
        "operator: audit UI denied → 403",
        r_op_audit.status_code == 403,
        "нет audit:read",
    ):
        failures += 1

    r_aud_audit = client.get("/api/security/audit/recent?limit=10", headers=aud_h)
    if not _step(
        "auditor: audit read-only → 200",
        r_aud_audit.status_code == 200,
        "auditor видит security console data",
    ):
        failures += 1

    r_admin_audit = client.get("/api/security/audit/recent?limit=30", headers=admin_h)
    if r_admin_audit.status_code == 200:
        items = r_admin_audit.json().get("items") or []
        types = {it.get("event_type") for it in items}
        blob = json.dumps(items)
        if not _step(
            "admin audit recent: auth.login.success",
            "auth.login.success" in types,
            f"типы: {sorted(types)[:6]}",
        ):
            failures += 1
        if not _step(
            "audit response без секретов",
            "password" not in blob.lower() or "[redacted]" in blob,
            "sanitize AuditService",
        ):
            failures += 1
    else:
        _step("admin audit recent", False, str(r_admin_audit.status_code))
        failures += 1

    r_sum = client.get("/api/security/audit/summary", headers=admin_h)
    if not _step(
        "audit summary → 200",
        r_sum.status_code == 200 and "by_event_type" in (r_sum.json() or {}),
        "summary для верхней панели Security console",
    ):
        failures += 1

    _section("5. Documents access (HTTP)")
    r_docs = client.get("/api/documents?limit=1", headers=admin_h)
    if not _step(
        "admin: documents list",
        r_docs.status_code in (200, 404),
        f"status {r_docs.status_code}",
    ):
        failures += 1

    r_op_docs = client.get("/api/documents?limit=1", headers=op_h)
    if not _step(
        "operator: documents read (если есть corpus)",
        r_op_docs.status_code in (200, 403, 404),
        f"status {r_op_docs.status_code}",
    ):
        failures += 1

    _section("Итог")
    if failures:
        print(f"  FAILURES: {failures}")
        return 1
    print("  Все сценарии P9.5b пройдены — Security console готова к demo walkthrough.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
