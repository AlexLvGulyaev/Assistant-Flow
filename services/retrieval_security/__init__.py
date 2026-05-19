"""
Retrieval security groundwork (P6.7): контекст, where, post-filter, masking, telemetry.
"""

from services.retrieval_security.context import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_GUEST,
    RetrievalSecurityContext,
)
from services.retrieval_security.masking import (
    mask_common_pii,
    mask_common_pii_with_telemetry,
    mask_email,
    mask_long_digit_runs,
    mask_phone,
)
from services.retrieval_security.policy_resolver import (
    build_retrieval_security_context_for_role,
    resolve_role_for_telegram_user,
    resolve_telegram_retrieval_security,
)

__all__ = [
    "ROLE_ADMIN",
    "ROLE_EMPLOYEE",
    "ROLE_GUEST",
    "RetrievalSecurityContext",
    "build_retrieval_security_context_for_role",
    "mask_common_pii",
    "mask_common_pii_with_telemetry",
    "mask_email",
    "mask_long_digit_runs",
    "mask_phone",
    "resolve_role_for_telegram_user",
    "resolve_telegram_retrieval_security",
]
