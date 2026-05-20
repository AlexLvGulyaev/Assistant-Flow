"""
Мост PrincipalContext → RetrievalSecurityContext (P9.1).

Backward-compatible: env-based Telegram resolver остаётся fallback.
"""

from __future__ import annotations

from services.retrieval_security.context import RetrievalSecurityContext
from services.retrieval_security.policy_resolver import (
    build_retrieval_security_context_for_role,
    resolve_role_for_telegram_user,
    resolve_telegram_retrieval_security,
)
from services.security.principal import PrincipalContext


def retrieval_security_from_principal(
    principal: PrincipalContext | None,
) -> RetrievalSecurityContext | None:
    if principal is None or not principal.is_authenticated:
        return None
    role = (principal.retrieval_role or "").strip().lower()
    if not role:
        return None
    base = build_retrieval_security_context_for_role(role)
    return RetrievalSecurityContext(
        role=base.role,
        allowed_sources=base.allowed_sources,
        retrieval_scope=base.retrieval_scope,
        metadata_filters=base.metadata_filters,
        required_tags=base.required_tags,
        allowed_visibility=base.allowed_visibility,
        audit_user_id=principal.user_id,
        audit_email=principal.email,
        audit_platform_role=principal.platform_role,
        audit_execution_id=None,
    )


def resolve_retrieval_security_for_telegram(
    telegram_user_id: int | None,
    *,
    telegram_chat_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> RetrievalSecurityContext:
    """
    Главная точка для Telegram RAG после P9.1.

    1. Platform user + ``retrieval_role`` из БД (channel identity).
    2. Env overrides внутри ``resolve_principal_for_telegram``.
    3. Legacy env-only ``resolve_telegram_retrieval_security``.
    """
    try:
        from services.security.identity_service import get_identity_service

        principal = get_identity_service().resolve_principal_for_telegram(
            telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        ctx = retrieval_security_from_principal(principal)
        if ctx is not None:
            return ctx
    except Exception:
        pass
    return resolve_telegram_retrieval_security(telegram_user_id)
