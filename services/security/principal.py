"""Runtime principal (P9.1–P9.4) — RBAC, auth, audit, retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from services.retrieval_security.context import ROLE_EMPLOYEE
from services.security.rbac import (
    PLATFORM_ADMIN,
    PLATFORM_AUDITOR,
    PLATFORM_DEMO,
    PLATFORM_EMPLOYEE,
    PLATFORM_END_USER,
    PLATFORM_OPERATOR,
    PLATFORM_SUPERADMIN,
    resolve_permissions,
    retrieval_role_for_platform,
)

AUTH_SOURCE_ANONYMOUS = "anonymous"
AUTH_SOURCE_BASIC = "basic"
AUTH_SOURCE_BEARER = "bearer"
AUTH_SOURCE_OPS_TOKEN = "ops_token"
AUTH_SOURCE_TELEGRAM = "telegram"
AUTH_SOURCE_DEV_HEADER = "dev_header"

# Re-export platform roles for backward compatibility
__all__ = [
    "AUTH_SOURCE_ANONYMOUS",
    "AUTH_SOURCE_BASIC",
    "AUTH_SOURCE_BEARER",
    "AUTH_SOURCE_DEV_HEADER",
    "AUTH_SOURCE_TELEGRAM",
    "PLATFORM_ADMIN",
    "PLATFORM_AUDITOR",
    "PLATFORM_DEMO",
    "PLATFORM_EMPLOYEE",
    "PLATFORM_END_USER",
    "PLATFORM_OPERATOR",
    "PLATFORM_SUPERADMIN",
    "PrincipalContext",
]


@dataclass(frozen=True)
class PrincipalContext:
    """
    Субъект запроса в runtime.

    ``user_id is None`` — anonymous / unauthenticated (demo mode).
    """

    user_id: uuid.UUID | None = None
    platform_role: str = PLATFORM_END_USER
    retrieval_role: str = ROLE_EMPLOYEE
    permissions: frozenset[str] = field(default_factory=frozenset)
    auth_source: str = AUTH_SOURCE_ANONYMOUS
    is_authenticated: bool = False
    email: str | None = None
    display_name: str | None = None
    actor_id: str | None = None

    @classmethod
    def anonymous(cls) -> PrincipalContext:
        return cls(
            user_id=None,
            platform_role=PLATFORM_END_USER,
            retrieval_role=ROLE_EMPLOYEE,
            permissions=frozenset(),
            auth_source=AUTH_SOURCE_ANONYMOUS,
            is_authenticated=False,
        )

    @classmethod
    def from_ops_token(cls, platform_role: str) -> PrincipalContext:
        """Static ops-токен (демо-стандарт APL): без пользователя в БД."""
        return cls(
            user_id=None,
            platform_role=platform_role,
            retrieval_role=retrieval_role_for_platform(platform_role),
            permissions=resolve_permissions(platform_role),
            auth_source=AUTH_SOURCE_OPS_TOKEN,
            is_authenticated=True,
            email=None,
            display_name=("Demo console" if platform_role == PLATFORM_DEMO else "Ops Console"),
            actor_id=f"ops:{platform_role}",
        )

    @classmethod
    def from_user_row(
        cls,
        row: dict[str, Any],
        *,
        auth_source: str = AUTH_SOURCE_BASIC,
    ) -> PrincipalContext:
        platform_role = str(row.get("platform_role") or PLATFORM_END_USER).strip()
        retrieval_role = str(row.get("retrieval_role") or "").strip()
        if not retrieval_role:
            retrieval_role = retrieval_role_for_platform(platform_role)
        perms = resolve_permissions(platform_role)
        uid = row.get("id")
        user_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
        return cls(
            user_id=user_uuid,
            platform_role=platform_role,
            retrieval_role=retrieval_role,
            permissions=perms,
            auth_source=auth_source,
            is_authenticated=True,
            email=(str(row["email"]).strip() if row.get("email") else None),
            display_name=(str(row["display_name"]).strip() if row.get("display_name") else None),
            actor_id=str(user_uuid),
        )

    @property
    def require_authenticated(self) -> bool:
        return self.is_authenticated

    def has_permission(self, permission: str) -> bool:
        if "*" in self.permissions:
            return True
        return permission in self.permissions

    def has_any_permission(self, *permissions: str) -> bool:
        if "*" in self.permissions:
            return True
        return any(p in self.permissions for p in permissions)
