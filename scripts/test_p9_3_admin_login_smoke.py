#!/usr/bin/env python3
"""
Smoke: P9.3 Admin UI login & session flow.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_3_admin_login_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    errors: list[str] = []

    from services.security.auth_policy import get_auth_mode, is_public_path
    from services.security.session_token import (
        issue_session_token,
        principal_from_token_payload,
        revoke_session_token,
        verify_session_token,
    )
    from services.security.principal import PLATFORM_ADMIN, PrincipalContext
    from services.retrieval_security.context import ROLE_ADMIN
    import uuid

    assert is_public_path("/api/auth/login", "POST", "required")
    assert is_public_path("/api/auth/logout", "POST", "required")

    uid = uuid.UUID("00000000-0000-4000-8000-000000000099")
    p = PrincipalContext.from_user_row(
        {
            "id": str(uid),
            "email": "smoke@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        },
        auth_source="bearer",
    )
    token, expires_in, _jti = issue_session_token(p, ttl_seconds=600)
    assert expires_in == 600
    payload = verify_session_token(token)
    assert payload and payload.get("sub") == str(uid)
    p2 = principal_from_token_payload(payload)
    assert p2 and p2.is_authenticated and p2.email == "smoke@test.local"
    assert revoke_session_token(token)
    assert verify_session_token(token) is None

    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        print("[p9.3] token unit checks OK; skip HTTP (no INITIAL_ADMIN_*)")
        return 0

    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app
    except ImportError as e:
        print(f"[p9.3] token OK; TestClient unavailable: {e}")
        return 0

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
    app = create_admin_api_app()
    client = TestClient(app, raise_server_exceptions=False)

    r_me = client.get("/api/auth/me")
    if r_me.status_code != 200 or r_me.json().get("authenticated"):
        errors.append(f"/api/auth/me anonymous: {r_me.status_code} {r_me.text[:200]}")

    r_bad = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-password-smoke"},
    )
    if r_bad.status_code != 401:
        errors.append(f"login invalid: expected 401 got {r_bad.status_code}")

    r_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    if r_login.status_code != 200:
        errors.append(f"login: {r_login.status_code} {r_login.text[:300]}")
        for msg in errors:
            print(f"FAIL: {msg}")
        return 1

    body = r_login.json()
    token = body.get("access_token")
    if not token:
        errors.append("login: no access_token")
    else:
        headers = {"Authorization": f"Bearer {token}"}
        r_me2 = client.get("/api/auth/me", headers=headers)
        j = r_me2.json()
        if not j.get("authenticated") or j.get("email") != email.strip().lower():
            errors.append(f"/api/auth/me authed: {j}")

        r_logs = client.get("/api/logs/recent?limit=1", headers=headers)
        if r_logs.status_code not in (200, 404):
            errors.append(f"protected route: {r_logs.status_code}")

        r_logout = client.post("/api/auth/logout", headers=headers)
        if r_logout.status_code != 200:
            errors.append(f"logout: {r_logout.status_code}")

        r_after = client.get("/api/auth/me", headers=headers)
        if r_after.json().get("authenticated"):
            errors.append("me still authenticated after logout revoke")

        r_prot = client.get("/api/logs/recent?limit=1")
        if r_prot.status_code != 401:
            errors.append(f"required without auth: expected 401 got {r_prot.status_code}")

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "disabled"
    assert get_auth_mode() == "disabled"
    r_open = client.get("/api/logs/recent?limit=1")
    if r_open.status_code not in (200, 404):
        errors.append(f"disabled mode: {r_open.status_code}")

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}")
        return 1

    print("[p9.3] smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
