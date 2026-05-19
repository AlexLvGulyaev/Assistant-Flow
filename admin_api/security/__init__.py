"""Admin API security (P9.2)."""

from admin_api.security.auth_policy import (
    get_auth_mode,
    is_public_path,
    requires_authentication,
)
from admin_api.security.deps import (
    current_principal,
    require_authenticated_principal,
    require_platform_roles,
)

__all__ = [
    "current_principal",
    "get_auth_mode",
    "is_public_path",
    "require_authenticated_principal",
    "require_platform_roles",
    "requires_authentication",
]
