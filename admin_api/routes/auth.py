"""Auth API: login, logout, /me (P9.2–P9.3)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.security.auth_middleware import get_request_principal, hash_client_ip
from services.security.auth_policy import get_auth_mode, is_public_path, requires_authentication
from services.security.identity_service import get_identity_service
from services.security.principal import AUTH_SOURCE_BEARER
from services.security.session_token import issue_session_token, revoke_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


def _me_payload(request: Request) -> dict[str, object]:
    principal = get_request_principal(request)
    mode = get_auth_mode()
    path = request.url.path
    method = request.method

    payload: dict[str, object] = {
        "authenticated": principal.is_authenticated,
        "auth_mode": mode,
        "auth_enforced": requires_authentication(path, method, mode),
        "path_public": is_public_path(path, method, mode),
        "user_id": str(principal.user_id) if principal.user_id else None,
        "email": principal.email,
        "platform_role": principal.platform_role if principal.is_authenticated else None,
        "retrieval_role": principal.retrieval_role if principal.is_authenticated else None,
        "permissions": sorted(principal.permissions) if principal.is_authenticated else [],
        "auth_source": principal.auth_source if principal.is_authenticated else None,
    }
    if principal.is_authenticated:
        payload["principal"] = {
            "user_id": payload["user_id"],
            "platform_role": principal.platform_role,
            "retrieval_role": principal.retrieval_role,
            "auth_source": principal.auth_source,
            "email": principal.email,
            "display_name": principal.display_name,
            "permissions": payload["permissions"],
        }
    else:
        payload["principal"] = None
        if mode == "required":
            payload["hint"] = (
                "Войдите через Admin UI (email/password) или задайте "
                "AF_AUTH_MIDDLEWARE_MODE=disabled для локальной разработки"
            )
    return payload


@router.get("/me")
def api_auth_me(request: Request) -> dict[str, object]:
    """Source of truth для frontend auth state."""
    return _me_payload(request)


@router.post("/login")
def api_auth_login(body: LoginBody, request: Request) -> dict[str, object]:
    svc = get_identity_service()
    ip_hash = hash_client_ip(request.client.host if request.client else None)
    principal = svc.authenticate_user(
        body.email,
        body.password,
        auth_source=AUTH_SOURCE_BEARER,
        ip_hash=ip_hash,
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token, expires_in, _jti = issue_session_token(principal)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user_id": str(principal.user_id),
        "email": principal.email,
        "platform_role": principal.platform_role,
    }


def _bearer_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


@router.post("/logout")
def api_auth_logout(request: Request) -> dict[str, object]:
    tok = _bearer_from_request(request)
    if tok:
        revoke_session_token(tok)
    return {"ok": True}

