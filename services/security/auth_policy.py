"""
Политика защиты Admin API (P9.2).

Режимы ``AF_AUTH_MIDDLEWARE_MODE``:
- ``disabled`` — без enforcement;
- ``optional`` — principal если есть credentials, маршруты открыты;
- ``required`` — все ``/api/*`` кроме public allowlist требуют authenticated principal.
"""

from __future__ import annotations

import os
import re
from typing import Literal

AuthMode = Literal["disabled", "optional", "required"]

PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/api/health",
        "/api/auth/me",
        "/api/auth/login",
        "/api/auth/logout",
    }
)

DOCS_PATHS: frozenset[str] = frozenset(
    {
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

PUBLIC_READONLY_GET_PATHS: frozenset[str] = frozenset(
    {
        "/api/overview",
        "/api/summary",
        "/api/documents",
    }
)

SENSITIVE_PATH_PREFIXES: tuple[str, ...] = (
    "/api/logs",
    "/api/documents/upload",
    "/api/documents/reindex",
    "/api/retrieval",
    "/api/evaluation",
    "/api/sessions",
    "/api/preview",
    "/api/active-backend",
)

_DOCUMENT_DETAIL_RE = re.compile(r"^/api/documents/[^/]+/(detail|edit-text)$")


def get_auth_mode() -> AuthMode:
    raw = (os.getenv("AF_AUTH_MIDDLEWARE_MODE") or "disabled").strip().lower()
    if raw in ("disabled", "optional", "required"):
        return raw  # type: ignore[return-value]
    return "disabled"


def public_readonly_enabled() -> bool:
    return (os.getenv("AF_AUTH_PUBLIC_READ_ONLY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def is_public_path(path: str, method: str, mode: AuthMode) -> bool:
    if path in DOCS_PATHS:
        return True
    if path in PUBLIC_PATHS:
        return True
    if mode != "required":
        return False
    if public_readonly_enabled() and method.upper() == "GET":
        if path in PUBLIC_READONLY_GET_PATHS:
            return True
    return False


def requires_authentication(path: str, method: str, mode: AuthMode) -> bool:
    if mode == "disabled":
        return False
    if mode == "optional":
        return False
    if not path.startswith("/api/"):
        return False
    if is_public_path(path, method, mode):
        return False
    return True


def is_sensitive_path(path: str) -> bool:
    if _DOCUMENT_DETAIL_RE.match(path):
        return True
    return any(path.startswith(p) for p in SENSITIVE_PATH_PREFIXES)
