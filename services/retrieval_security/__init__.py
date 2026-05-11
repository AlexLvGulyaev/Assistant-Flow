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

__all__ = [
    "ROLE_ADMIN",
    "ROLE_EMPLOYEE",
    "ROLE_GUEST",
    "RetrievalSecurityContext",
    "mask_common_pii",
    "mask_common_pii_with_telemetry",
    "mask_email",
    "mask_long_digit_runs",
    "mask_phone",
]
