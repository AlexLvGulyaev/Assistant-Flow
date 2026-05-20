"""
FastAPI dependencies для principal и RBAC (P9.2–P9.4).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from services.security.auth_policy import get_auth_mode
from services.security.auth_middleware import get_request_principal
from services.security.principal import PrincipalContext


def current_principal(request: Request) -> PrincipalContext:
    return get_request_principal(request)


def _rbac_applies(principal: PrincipalContext) -> bool:
    mode = get_auth_mode()
    if mode == "disabled":
        return False
    if mode == "optional" and not principal.is_authenticated:
        return False
    return True


def require_authenticated_principal(
    principal: PrincipalContext = Depends(current_principal),
) -> PrincipalContext:
    """401 если principal не аутентифицирован."""
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


def require_permission(permission: str) -> Callable[..., PrincipalContext]:
    """403 если нет permission; в ``disabled`` / anonymous ``optional`` — пропуск."""

    def _dep(
        request: Request,
        principal: PrincipalContext = Depends(current_principal),
    ) -> PrincipalContext:
        if not _rbac_applies(principal):
            return principal
        if not principal.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "unauthorized",
                    "message": "Authentication required",
                    "auth_mode": get_auth_mode(),
                },
            )
        if not principal.has_permission(permission):
            try:
                from services.security.audit_service import get_audit_service

                get_audit_service().log_permission_denied(
                    principal=principal,
                    permission=permission,
                    request=request,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": f"Insufficient permissions: requires {permission}",
                    "permission": permission,
                    "platform_role": principal.platform_role,
                },
            )
        return principal

    return _dep


def require_any_permission(*permissions: str) -> Callable[..., PrincipalContext]:
    def _dep(
        request: Request,
        principal: PrincipalContext = Depends(current_principal),
    ) -> PrincipalContext:
        if not _rbac_applies(principal):
            return principal
        if not principal.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "unauthorized",
                    "message": "Authentication required",
                    "auth_mode": get_auth_mode(),
                },
            )
        if not principal.has_any_permission(*permissions):
            try:
                from services.security.audit_service import get_audit_service

                get_audit_service().log_permission_denied(
                    principal=principal,
                    permission=permissions[0] if permissions else "unknown",
                    request=request,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": f"Insufficient permissions: requires one of {list(permissions)}",
                    "permissions": list(permissions),
                    "platform_role": principal.platform_role,
                },
            )
        return principal

    return _dep


def require_platform_roles(
    *roles: str,
):
    """Зависимость: platform_role из списка (legacy; предпочтительно require_permission)."""

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
