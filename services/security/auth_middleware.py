"""
Auth middleware (P9.1 foundation, P9.2 enforcement).

Режимы ``AF_AUTH_MIDDLEWARE_MODE``: ``disabled`` | ``optional`` | ``required``.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.security.auth_policy import get_auth_mode, requires_authentication
from services.security.basic_auth import parse_basic_auth_header
from services.security.identity_service import get_identity_service, hash_client_ip
from services.security.principal import (
    AUTH_SOURCE_BASIC,
    AUTH_SOURCE_BEARER,
    AUTH_SOURCE_DEV_HEADER,
    PrincipalContext,
)
from services.security.ops_token import resolve_ops_role
from services.security.session_token import principal_from_token_payload, verify_session_token

logger = logging.getLogger(__name__)

STATE_PRINCIPAL_KEY = "af_principal"


def get_request_principal(request: Request) -> PrincipalContext:
    p = getattr(request.state, STATE_PRINCIPAL_KEY, None)
    if isinstance(p, PrincipalContext):
        return p
    return PrincipalContext.anonymous()


def unauthorized_response(
    *,
    message: str = "Authentication required",
    auth_mode: str | None = None,
) -> JSONResponse:
    mode = auth_mode or get_auth_mode()
    return JSONResponse(
        status_code=401,
        content={
            "detail": "unauthorized",
            "code": "unauthorized",
            "message": message,
            "auth_mode": mode,
        },
        headers={"WWW-Authenticate": 'Basic realm="assistant-flow-admin"'},
    )


def _parse_bearer_token(header: str | None) -> str | None:
    if not header or not header.lower().startswith("bearer "):
        return None
    tok = header[7:].strip()
    return tok or None


def _resolve_principal_from_request(request: Request) -> PrincipalContext:
    svc = get_identity_service()
    ip_hash = hash_client_ip(request.client.host if request.client else None)

    bearer = _parse_bearer_token(request.headers.get("authorization"))
    if bearer:
        # Демо-стандарт APL: статические ops-токены (admin / demo).
        ops_role = resolve_ops_role(bearer)
        if ops_role:
            return PrincipalContext.from_ops_token(ops_role)

        payload = verify_session_token(bearer)
        if payload:
            principal = principal_from_token_payload(payload)
            if principal:
                return principal

    basic = parse_basic_auth_header(request.headers.get("authorization"))
    if basic:
        email, password = basic
        auth_principal = svc.authenticate_user(
            email, password, auth_source=AUTH_SOURCE_BASIC, ip_hash=ip_hash
        )
        if auth_principal:
            return auth_principal

    if _dev_headers_enabled():
        dev_email = (request.headers.get("x-af-principal-email") or "").strip()
        dev_password = request.headers.get("x-af-principal-password") or ""
        if dev_email and dev_password:
            auth_principal = svc.authenticate_user(
                dev_email,
                dev_password,
                auth_source=AUTH_SOURCE_DEV_HEADER,
                ip_hash=ip_hash,
            )
            if auth_principal:
                return auth_principal

    return PrincipalContext.anonymous()


class IdentityAuthMiddleware(BaseHTTPMiddleware):
    """Principal в ``request.state`` + enforcement в режиме ``required``."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        mode = get_auth_mode()
        path = request.url.path
        method = request.method

        principal = PrincipalContext.anonymous()
        if mode != "disabled":
            principal = _resolve_principal_from_request(request)

        setattr(request.state, STATE_PRINCIPAL_KEY, principal)

        if requires_authentication(path, method, mode) and not principal.is_authenticated:
            try:
                from services.security.audit_service import get_audit_service

                get_audit_service().log_access_denied(
                    path=path,
                    method=method,
                    request=request,
                    reason="unauthenticated",
                )
                get_identity_service().record_access_denied(
                    path=path,
                    method=method,
                    auth_mode=mode,
                    ip_hash=hash_client_ip(request.client.host if request.client else None),
                )
            except Exception as exc:
                logger.debug("record_access_denied skipped: %s", exc)
            logger.info(
                "[assistant-flow] auth: denied path=%s method=%s mode=%s",
                path,
                method,
                mode,
            )
            return unauthorized_response(auth_mode=mode)

        return await call_next(request)


def _dev_headers_enabled() -> bool:
    return (os.getenv("AF_IDENTITY_DEV_HEADERS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
