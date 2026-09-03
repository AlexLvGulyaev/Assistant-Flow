"""
Статические ops-токены консоли (демо-стандарт APL).

Канон RF/AIC/LQ: Bearer-токен из окружения вместо email/password в UI.
- ``AF_ADMIN_TOKEN``      — полный доступ (платформенная роль ``admin``);
- ``AF_ADMIN_DEMO_TOKEN`` — витринный вход, роль ``demo`` (read-only).

Токены не заданы → ops-авторизация недоступна (локальная разработка).
"""

from __future__ import annotations

import os
import secrets

from services.security.rbac import PLATFORM_ADMIN, PLATFORM_DEMO


def get_admin_token() -> str | None:
    token = (os.getenv("AF_ADMIN_TOKEN") or "").strip()
    return token or None


def get_demo_token() -> str | None:
    token = (os.getenv("AF_ADMIN_DEMO_TOKEN") or "").strip()
    return token or None


def ops_auth_configured() -> bool:
    """True, если задан хотя бы один ops-токен."""
    return bool(get_admin_token() or get_demo_token())


def resolve_ops_role(token: str | None) -> str | None:
    """Bearer-токен → платформенная роль или None (не совпал)."""
    if not token:
        return None
    admin_token = get_admin_token()
    if admin_token and secrets.compare_digest(token, admin_token):
        return PLATFORM_ADMIN
    demo_token = get_demo_token()
    if demo_token and secrets.compare_digest(token, demo_token):
        return PLATFORM_DEMO
    return None