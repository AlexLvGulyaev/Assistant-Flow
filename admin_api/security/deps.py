"""
FastAPI dependencies для principal (P9.2).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from services.security.auth_policy import get_auth_mode
from services.security.auth_middleware import get_request_principal
from services.security.principal import PrincipalContext


def current_principal(request: Request) -> PrincipalContext:
    return get_request_principal(request)


def require_authenticated_principal(
    principal: PrincipalContext = Depends(current_principal),
) -> PrincipalContext:
    """401 если principal не аутентифицирован (независимо от middleware mode)."""
    if not principal.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "Authentication required",
                "auth_mode": get_auth_mode(),
            },
        )
    return principal


def require_platform_roles(
    *roles: str,
):
    """Зависимость: platform_role из списка."""

    def _dep(
        principal: PrincipalContext = Depends(require_authenticated_principal),
    ) -> PrincipalContext:
        if principal.platform_role not in roles and "*" not in principal.permissions:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": f"Requires platform role: {', '.join(roles)}",
                    "role": principal.platform_role,
                },
            )
        return principal

    return _dep
