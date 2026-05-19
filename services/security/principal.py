"""Runtime principal (P9.1) — foundation для RBAC, auth, audit, retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from services.retrieval_security.context import ROLE_EMPLOYEE

AUTH_SOURCE_ANONYMOUS = "anonymous"
AUTH_SOURCE_BASIC = "basic"
AUTH_SOURCE_BEARER = "bearer"
AUTH_SOURCE_TELEGRAM = "telegram"
AUTH_SOURCE_DEV_HEADER = "dev_header"

# Platform roles (control plane)
PLATFORM_END_USER = "end_user"
PLATFORM_EMPLOYEE = "employee"
PLATFORM_OPERATOR = "operator"
PLATFORM_ADMIN = "admin"
PLATFORM_AUDITOR = "auditor"
PLATFORM_SUPERADMIN = "superadmin"

# Permission foundation (P9.4 расширит)
_PERMISSIONS_BY_PLATFORM_ROLE: dict[str, frozenset[str]] = {
    PLATFORM_ADMIN: frozenset(
        {
            "documents:read",
            "documents:write",
            "logs:read",
            "logs:forensic",
            "settings:read",
            "settings:write",
            "users:manage",
            "audit:read",
        }
    ),
    PLATFORM_SUPERADMIN: frozenset({"*"}),
    PLATFORM_OPERATOR: frozenset(
        {
            "documents:read",
            "documents:write",
            "logs:read",
            "settings:read",
            "evaluation:run",
        }
    ),
    PLATFORM_AUDITOR: frozenset({"logs:read", "audit:read", "logs:forensic"}),
    PLATFORM_EMPLOYEE: frozenset({"documents:read"}),
    PLATFORM_END_USER: frozenset(),
}


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
    actor_id: str | None = None  # string for audit logs

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
    def from_user_row(
        cls,
        row: dict[str, Any],
        *,
        auth_source: str = AUTH_SOURCE_BASIC,
    ) -> PrincipalContext:
        platform_role = str(row.get("platform_role") or PLATFORM_END_USER).strip()
        retrieval_role = str(row.get("retrieval_role") or ROLE_EMPLOYEE).strip()
        perms = _PERMISSIONS_BY_PLATFORM_ROLE.get(platform_role, frozenset())
        if "*" in perms:
            perms = frozenset(_PERMISSIONS_BY_PLATFORM_ROLE[PLATFORM_ADMIN])
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

    def has_permission(self, permission: str) -> bool:
        if "*" in self.permissions:
            return True
        return permission in self.permissions
