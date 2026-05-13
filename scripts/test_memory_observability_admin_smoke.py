#!/usr/bin/env python3
"""
Smoke: Admin API /api/memory/* + optional ``npm run build`` for admin-ui.

Не требует запущенного сервера (TestClient). DATABASE_URL опционален.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_api_memory_routes() -> None:
    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError:
        print("SKIP: fastapi / TestClient (install requirements.txt in venv)")
        return

    from admin_api.app import create_admin_api_app

    client = TestClient(create_admin_api_app())
    r = client.get("/api/memory/observability/summary?hours=24")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "memory_runtime_source" in body
    assert "budget_limits" in body

    r2 = client.get("/api/memory/sessions?limit=5")
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert "items" in j2

    bad = client.get(
        "/api/memory/sessions/00000000-0000-4000-8000-000000000001"
    )
    assert bad.status_code in (200, 404)

    print("OK: admin_api /api/memory observability routes")


def test_ui_build() -> int:
    ui = ROOT / "frontend" / "admin-ui"
    pkg = ui / "package.json"
    if not pkg.is_file():
        print("SKIP: admin-ui package.json missing")
        return 0
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(ui),
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "CI": "1"},
    )
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        return proc.returncode
    print("OK: admin-ui npm run build")
    return 0


def main() -> int:
    test_api_memory_routes()
    return test_ui_build()


if __name__ == "__main__":
    raise SystemExit(main())
