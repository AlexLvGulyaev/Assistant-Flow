"""
Bounded RBAC (P9.4): platform_role → permissions → enforcement.

Не enterprise IAM — явная матрица для Admin API control plane.
"""

from __future__ import annotations

from services.retrieval_security.context import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_GUEST

# Platform roles (control plane) — единый источник для principal + RBAC
PLATFORM_END_USER = "end_user"
PLATFORM_EMPLOYEE = "employee"
PLATFORM_OPERATOR = "operator"
PLATFORM_ADMIN = "admin"
PLATFORM_AUDITOR = "auditor"
PLATFORM_SUPERADMIN = "superadmin"
# Демо-роль для витринного входа (демо-стандарт APL): read-only, без мутаций.
PLATFORM_DEMO = "demo"

# --- Permission names ---
PERM_DOCUMENTS_READ = "documents:read"
PERM_DOCUMENTS_WRITE = "documents:write"
PERM_DOCUMENTS_REINDEX = "documents:reindex"
PERM_LOGS_READ = "logs:read"
PERM_LOGS_FORENSIC = "logs:forensic"
PERM_RETRIEVAL_READ = "retrieval:read"
PERM_RETRIEVAL_ADMIN = "retrieval:admin"
PERM_SETTINGS_READ = "settings:read"
PERM_SETTINGS_WRITE = "settings:write"
PERM_USERS_READ = "users:read"
PERM_USERS_WRITE = "users:write"
PERM_AUDIT_READ = "audit:read"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_DOCUMENTS_READ,
        PERM_DOCUMENTS_WRITE,
        PERM_DOCUMENTS_REINDEX,
        PERM_LOGS_READ,
        PERM_LOGS_FORENSIC,
        PERM_RETRIEVAL_READ,
        PERM_RETRIEVAL_ADMIN,
        PERM_SETTINGS_READ,
        PERM_SETTINGS_WRITE,
        PERM_USERS_READ,
        PERM_USERS_WRITE,
        PERM_AUDIT_READ,
    }
)

_ADMIN_OPERATIONAL: frozenset[str] = frozenset(
    {
        PERM_DOCUMENTS_READ,
        PERM_DOCUMENTS_WRITE,
        PERM_DOCUMENTS_REINDEX,
        PERM_LOGS_READ,
        PERM_LOGS_FORENSIC,
        PERM_RETRIEVAL_READ,
        PERM_RETRIEVAL_ADMIN,
        PERM_SETTINGS_READ,
        PERM_SETTINGS_WRITE,
        PERM_USERS_READ,
        PERM_AUDIT_READ,
    }
)

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    # guest / end_user — без Admin API
    PLATFORM_END_USER: frozenset(),
    # employee — без control-plane по умолчанию
    PLATFORM_EMPLOYEE: frozenset(),
    PLATFORM_OPERATOR: frozenset(
        {
            PERM_DOCUMENTS_READ,
            PERM_DOCUMENTS_WRITE,
            PERM_DOCUMENTS_REINDEX,
            PERM_LOGS_READ,
            PERM_RETRIEVAL_READ,
            PERM_SETTINGS_READ,
        }
    ),
    PLATFORM_AUDITOR: frozenset(
        {
            PERM_LOGS_READ,
            PERM_LOGS_FORENSIC,
            PERM_AUDIT_READ,
            PERM_DOCUMENTS_READ,
            PERM_RETRIEVAL_READ,
        }
    ),
    PLATFORM_ADMIN: _ADMIN_OPERATIONAL,
    PLATFORM_SUPERADMIN: frozenset({"*"}),
    # Демо-вход (только просмотр): читаемые разделы консоли без мутаций.
    PLATFORM_DEMO: frozenset(
        {
            PERM_DOCUMENTS_READ,
            PERM_LOGS_READ,
            PERM_RETRIEVAL_READ,
            PERM_SETTINGS_READ,
            PERM_AUDIT_READ,
        }
    ),
}

# Алиасы
_ROLE_PERMISSIONS["guest"] = _ROLE_PERMISSIONS[PLATFORM_END_USER]


def resolve_permissions(platform_role: str) -> frozenset[str]:
    role = (platform_role or PLATFORM_END_USER).strip().lower()
    perms = _ROLE_PERMISSIONS.get(role, frozenset())
    if "*" in perms:
        return _ADMIN_OPERATIONAL | frozenset({PERM_USERS_WRITE})
    return perms


def retrieval_role_for_platform(platform_role: str) -> str:
    """Platform role → retrieval role (P8 bridge)."""
    role = (platform_role or PLATFORM_END_USER).strip().lower()
    if role in (PLATFORM_ADMIN, PLATFORM_SUPERADMIN):
        return ROLE_ADMIN
    if role in (PLATFORM_END_USER, "guest"):
        return ROLE_GUEST
    if role == PLATFORM_DEMO:
        return ROLE_GUEST
    return ROLE_EMPLOYEE


def expand_permissions_for_response(perms: frozenset[str]) -> list[str]:
    """Список для /api/auth/me (без wildcard)."""
    if "*" in perms:
        return sorted(ALL_PERMISSIONS | {PERM_USERS_WRITE})
    return sorted(perms)
