"""
Bounded session tokens для Admin UI (P9.3) — HMAC-signed payload, без refresh platform.

Формат: ``base64url(payload).base64url(hmac-sha256)``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from typing import Any

from services.security.principal import PrincipalContext

logger = logging.getLogger(__name__)

_revoked_jti: set[str] = set()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def session_secret() -> bytes:
    raw = (
        os.getenv("AF_SESSION_SECRET")
        or os.getenv("AF_JWT_SECRET")
        or ""
    ).strip()
    if not raw:
        logger.warning(
            "[assistant-flow] AF_SESSION_SECRET not set — using dev-only secret"
        )
        raw = "assistant-flow-dev-session-secret-change-me"
    return raw.encode("utf-8")


def default_ttl_seconds() -> int:
    try:
        return max(300, int(os.getenv("AF_SESSION_TTL_SECONDS", "28800")))
    except ValueError:
        return 28800


def issue_session_token(
    principal: PrincipalContext,
    *,
    ttl_seconds: int | None = None,
) -> tuple[str, int, str]:
    """Возвращает (token, expires_in, jti)."""
    ttl = ttl_seconds if ttl_seconds is not None else default_ttl_seconds()
    now = int(time.time())
    jti = secrets.token_urlsafe(18)
    payload: dict[str, Any] = {
        "sub": str(principal.user_id),
        "email": principal.email,
        "platform_role": principal.platform_role,
        "retrieval_role": principal.retrieval_role,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(session_secret(), body.encode("ascii"), hashlib.sha256).digest()
    token = f"{body}.{_b64url_encode(sig)}"
    return token, ttl, jti


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Проверка подписи и срока; ``None`` если невалиден или revoked."""
    t = (token or "").strip()
    if not t or "." not in t:
        return None
    body, _, sig_part = t.partition(".")
    if not body or not sig_part:
        return None
    try:
        expected = hmac.new(
            session_secret(), body.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_encode(expected), sig_part):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or int(exp) < int(time.time()):
        return None
    jti = str(payload.get("jti") or "")
    if jti and jti in _revoked_jti:
        return None
    return payload


def revoke_session_token(token: str) -> bool:
    payload = verify_session_token(token)
    if not payload:
        return False
    jti = str(payload.get("jti") or "")
    if jti:
        _revoked_jti.add(jti)
        return True
    return False


def principal_from_token_payload(payload: dict[str, Any]) -> PrincipalContext | None:
    from services.security.principal import (
        AUTH_SOURCE_BEARER,
        _PERMISSIONS_BY_PLATFORM_ROLE,
        PLATFORM_ADMIN,
        PLATFORM_END_USER,
    )

    sub = str(payload.get("sub") or "").strip()
    if not sub:
        return None
    try:
        uid = uuid.UUID(sub)
    except ValueError:
        return None
    platform_role = str(payload.get("platform_role") or PLATFORM_END_USER).strip()
    retrieval_role = str(payload.get("retrieval_role") or "employee").strip()
    perms = _PERMISSIONS_BY_PLATFORM_ROLE.get(platform_role, frozenset())
    if "*" in perms:
        perms = _PERMISSIONS_BY_PLATFORM_ROLE.get(PLATFORM_ADMIN, frozenset())
    return PrincipalContext(
        user_id=uid,
        platform_role=platform_role,
        retrieval_role=retrieval_role,
        permissions=perms,
        auth_source=AUTH_SOURCE_BEARER,
        is_authenticated=True,
        email=str(payload.get("email") or "") or None,
        display_name=None,
        actor_id=sub,
    )
