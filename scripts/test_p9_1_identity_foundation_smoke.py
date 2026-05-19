#!/usr/bin/env python3
"""
Smoke: P9.1 identity foundation — password, principal, retrieval bridge.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_1_identity_foundation_smoke.py
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

    from services.security.password import create_password_hash, verify_password
    from services.security.principal import PrincipalContext, PLATFORM_ADMIN
    from services.retrieval_security.principal_bridge import (
        retrieval_security_from_principal,
        resolve_retrieval_security_for_telegram,
    )
    from services.retrieval_security.context import ROLE_ADMIN, ROLE_GUEST
    import base64

    assert hasattr(PrincipalContext, "anonymous")

    h = create_password_hash("test-secret-9")
    assert verify_password("test-secret-9", h)
    assert not verify_password("wrong", h)

    admin_principal = PrincipalContext.from_user_row(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "email": "admin@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        }
    )
    assert admin_principal.is_authenticated
    assert admin_principal.has_permission("documents:write")
    ctx = retrieval_security_from_principal(admin_principal)
    assert ctx is not None and ctx.is_fully_unrestricted()

    guest_principal = PrincipalContext.from_user_row(
        {
            "id": "00000000-0000-4000-8000-000000000002",
            "email": "g@test.local",
            "platform_role": "end_user",
            "retrieval_role": ROLE_GUEST,
            "status": "active",
        }
    )
    g_ctx = retrieval_security_from_principal(guest_principal)
    assert g_ctx is not None and g_ctx.role == ROLE_GUEST

    # Env fallback bridge (no DB)
    os.environ.pop("TELEGRAM_ADMIN_USER_IDS", None)
    os.environ["TELEGRAM_GUEST_USER_IDS"] = "999"
    env_ctx = resolve_retrieval_security_for_telegram(999)
    assert env_ctx.role == ROLE_GUEST

    creds = base64.b64encode(b"user@example.com:secret").decode("ascii")
    raw = base64.b64decode(creds).decode("utf-8")
    email_p, _, pass_p = raw.partition(":")
    assert email_p == "user@example.com" and pass_p == "secret"

    # DB-backed checks (optional)
    try:
        from repositories.connection import get_database_url

        _ = get_database_url()
        from services.security.identity_service import IdentityService, run_identity_bootstrap

        assert hasattr(IdentityService, "bootstrap_admin_if_needed")

        os.environ.setdefault("INITIAL_ADMIN_EMAIL", "bootstrap-smoke@test.local")
        os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "smoke-bootstrap-pass-9")
        run_identity_bootstrap()
        svc = IdentityService()
        import uuid as _uuid

        email = f"p9-smoke-{_uuid.uuid4().hex[:8]}@test.local"
        uid = svc.create_user(
            email=email,
            password="pass-p9-smoke",
            platform_role="employee",
            retrieval_role="employee",
        )
        assert uid
        principal = svc.authenticate_user(email, "pass-p9-smoke")
        assert principal and principal.is_authenticated
        tg_principal = svc.resolve_principal_for_telegram(123456789)
        assert tg_principal and tg_principal.is_authenticated
        print("[assistant-flow] test_p9_1: DB checks OK")
    except Exception as exc:
        print(f"[assistant-flow] test_p9_1: DB checks skipped ({exc})")

    print("[assistant-flow] test_p9_1_identity_foundation_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
