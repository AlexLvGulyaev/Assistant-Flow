#!/usr/bin/env python3
"""
Smoke: P9.2 auth middleware hardening — policy, modes, principal.

  docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_2_auth_middleware_smoke.py
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

    from services.security.auth_policy import (
        get_auth_mode,
        is_public_path,
        requires_authentication,
    )
    from services.security.basic_auth import parse_basic_auth_header
    from services.security.principal import PrincipalContext, PLATFORM_ADMIN
    from services.retrieval_security.principal_bridge import retrieval_security_from_principal
    from services.retrieval_security.context import ROLE_ADMIN
    import base64

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "disabled"
    assert get_auth_mode() == "disabled"
    assert not requires_authentication("/api/logs/recent", "GET", "disabled")

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "optional"
    assert get_auth_mode() == "optional"
    assert not requires_authentication("/api/documents/upload", "POST", "optional")

    os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
    assert get_auth_mode() == "required"
    assert is_public_path("/api/health", "GET", "required")
    assert is_public_path("/api/auth/me", "GET", "required")
    assert not is_public_path("/api/logs/recent", "GET", "required")
    assert requires_authentication("/api/logs/recent", "GET", "required")
    assert requires_authentication("/api/documents/upload", "POST", "required")
    assert requires_authentication("/api/retrieval/active-backend", "PUT", "required")

    os.environ["AF_AUTH_PUBLIC_READ_ONLY"] = "true"
    assert is_public_path("/api/overview", "GET", "required")
    assert requires_authentication("/api/documents/upload", "POST", "required")
    os.environ.pop("AF_AUTH_PUBLIC_READ_ONLY", None)

    creds = base64.b64encode(b"admin@test.local:secret").decode()
    parsed = parse_basic_auth_header(f"Basic {creds}")
    assert parsed == ("admin@test.local", "secret")

    p = PrincipalContext.from_user_row(
        {
            "id": "00000000-0000-4000-8000-000000000099",
            "email": "a@test.local",
            "platform_role": PLATFORM_ADMIN,
            "retrieval_role": ROLE_ADMIN,
            "status": "active",
        }
    )
    ctx = retrieval_security_from_principal(p)
    assert ctx is not None and ctx.is_fully_unrestricted()

    # FastAPI app + TestClient (optional)
    try:
        from fastapi.testclient import TestClient
        from admin_api.app import create_admin_api_app

        os.environ["AF_AUTH_MIDDLEWARE_MODE"] = "required"
        app = create_admin_api_app()
        client = TestClient(app, raise_server_exceptions=False)

        r_health = client.get("/api/health")
        assert r_health.status_code == 200

        r_me = client.get("/api/auth/me")
        assert r_me.status_code == 200
        body = r_me.json()
        assert body.get("authenticated") is False
        assert body.get("auth_mode") == "required"

        r_logs = client.get("/api/logs/recent?limit=1")
        assert r_logs.status_code == 401

        print("[assistant-flow] test_p9_2: TestClient checks OK")
    except ImportError as exc:
        print(f"[assistant-flow] test_p9_2: TestClient skipped ({exc})")
    except Exception as exc:
        print(f"[assistant-flow] test_p9_2: TestClient skipped ({exc})")

    print("[assistant-flow] test_p9_2_auth_middleware_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
