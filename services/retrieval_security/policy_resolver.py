"""
Policy resolver для Telegram RAG (P8.1): env/config → RetrievalSecurityContext.

Без production IAM и таблицы пользователей. Заменяемый тонкий слой.
"""

from __future__ import annotations

import os

from services.retrieval_security.context import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_GUEST,
    RetrievalSecurityContext,
)
from services.retrieval_security.visibility import (
    VISIBILITY_INTERNAL,
    VISIBILITY_PUBLIC,
    VISIBILITY_UNSPECIFIED,
)

_KNOWN_ROLES = frozenset({ROLE_GUEST, ROLE_EMPLOYEE, ROLE_ADMIN})


def _parse_telegram_user_id_set(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for part in (raw or "").split(","):
        s = part.strip()
        if not s:
            continue
        try:
            out.add(int(s))
        except ValueError:
            continue
    return frozenset(out)


def _normalize_role(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in _KNOWN_ROLES:
        return s
    return ROLE_EMPLOYEE


def resolve_role_for_telegram_user(telegram_user_id: int | None) -> str:
    """
    Определяет retrieval-роль по env overrides и дефолту.

    Env:
    - ``TELEGRAM_ADMIN_USER_IDS`` — список id через запятую → admin;
    - ``TELEGRAM_GUEST_USER_IDS`` — guest (приоритет ниже admin);
    - ``TELEGRAM_DEFAULT_RETRIEVAL_ROLE`` — guest | employee | admin
      (default: ``employee`` для совместимости с corpus ``visibility=unspecified``).
    """
    admin_ids = _parse_telegram_user_id_set(os.getenv("TELEGRAM_ADMIN_USER_IDS", ""))
    guest_ids = _parse_telegram_user_id_set(os.getenv("TELEGRAM_GUEST_USER_IDS", ""))
    default_role = _normalize_role(os.getenv("TELEGRAM_DEFAULT_RETRIEVAL_ROLE"))

    if telegram_user_id is not None:
        uid = int(telegram_user_id)
        if uid in admin_ids:
            return ROLE_ADMIN
        if uid in guest_ids:
            return ROLE_GUEST

    return default_role


def build_retrieval_security_context_for_role(role: str) -> RetrievalSecurityContext:
    """Строит ``RetrievalSecurityContext`` для известной роли."""
    r = _normalize_role(role)
    if r == ROLE_ADMIN:
        return RetrievalSecurityContext.permissive_default()

    if r == ROLE_GUEST:
        return RetrievalSecurityContext(
            role=ROLE_GUEST,
            allowed_sources=None,
            retrieval_scope="public_only",
            metadata_filters=(),
            required_tags=frozenset(),
            allowed_visibility=frozenset({VISIBILITY_PUBLIC}),
        )

    # employee: public + internal + legacy unspecified (без restricted)
    return RetrievalSecurityContext(
        role=ROLE_EMPLOYEE,
        allowed_sources=None,
        retrieval_scope="employee_kb",
        metadata_filters=(),
        required_tags=frozenset(),
        allowed_visibility=frozenset(
            {VISIBILITY_PUBLIC, VISIBILITY_INTERNAL, VISIBILITY_UNSPECIFIED}
        ),
    )


def resolve_telegram_retrieval_security(
    telegram_user_id: int | None,
) -> RetrievalSecurityContext:
    """Главная точка входа для Telegram RAG path."""
    role = resolve_role_for_telegram_user(telegram_user_id)
    return build_retrieval_security_context_for_role(role)
