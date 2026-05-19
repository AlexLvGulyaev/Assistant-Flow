"""
Identity foundation (P9.1): platform users, channel identities, principal resolution.

Без JWT/OAuth — foundation для P9.2+.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from typing import Any

from repositories.channel_identity_repository import (
    CHANNEL_TELEGRAM,
    ChannelIdentityRepository,
)
from repositories.connection import get_connection
from repositories.user_repository import UserRepository
from services.retrieval_security.context import ROLE_EMPLOYEE
from services.retrieval_security.policy_resolver import resolve_role_for_telegram_user
from services.security.password import create_password_hash, verify_password
from services.security.principal import (
    AUTH_SOURCE_BASIC,
    AUTH_SOURCE_TELEGRAM,
    PLATFORM_ADMIN,
    PLATFORM_END_USER,
    PrincipalContext,
)

logger = logging.getLogger(__name__)

_identity_service: IdentityService | None = None


class IdentityService:
    """Bounded identity operations."""

    def __init__(
        self,
        *,
        user_repo: UserRepository | None = None,
        channel_repo: ChannelIdentityRepository | None = None,
    ) -> None:
        self._users = user_repo or UserRepository()
        self._channels = channel_repo or ChannelIdentityRepository()

    def create_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        platform_role: str = PLATFORM_END_USER,
        retrieval_role: str = ROLE_EMPLOYEE,
    ) -> uuid.UUID:
        email_norm = email.strip().lower()
        if not email_norm:
            raise ValueError("email required")
        pwd_hash = create_password_hash(password)
        legacy_role = "admin" if platform_role in (PLATFORM_ADMIN, "superadmin") else "user"
        with get_connection() as conn:
            existing = self._users.get_by_email(conn, email_norm)
            if existing:
                raise ValueError("user with this email already exists")
            uid = self._users.insert_platform_user(
                conn,
                email=email_norm,
                password_hash=pwd_hash,
                display_name=display_name or email_norm,
                platform_role=platform_role,
                retrieval_role=retrieval_role,
                legacy_role=legacy_role,
            )
            conn.commit()
        return uid

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            return self._users.get_by_email(conn, email.strip().lower())

    def get_user_by_channel_identity(
        self,
        channel: str,
        external_user_id: str,
    ) -> dict[str, Any] | None:
        with get_connection() as conn:
            link = self._channels.get_by_channel_external(
                conn, channel=channel, external_user_id=external_user_id
            )
            if not link:
                return None
            return self._users.get_by_id(conn, link["user_id"])

    def attach_channel_identity(
        self,
        user_id: uuid.UUID,
        *,
        channel: str,
        external_user_id: str,
        external_chat_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        with get_connection() as conn:
            existing = self._channels.get_by_channel_external(
                conn, channel=channel, external_user_id=external_user_id
            )
            if existing:
                if existing["user_id"] != user_id:
                    raise ValueError("channel identity already linked to another user")
                return existing["id"]
            cid = self._channels.insert(
                conn,
                user_id=user_id,
                channel=channel,
                external_user_id=external_user_id,
                external_chat_id=external_chat_id,
                metadata=metadata,
            )
            conn.commit()
        return cid

    def authenticate_user(
        self,
        email: str,
        password: str,
        *,
        auth_source: str = AUTH_SOURCE_BASIC,
        ip_hash: str | None = None,
    ) -> PrincipalContext | None:
        email_norm = email.strip().lower()
        with get_connection() as conn:
            row = self._users.get_by_email(conn, email_norm)
            if not row or str(row.get("status") or "active") != "active":
                self._record_login_event(
                    conn,
                    user_id=row["id"] if row else None,
                    event_type="login",
                    auth_source=auth_source,
                    outcome="failure",
                    actor_role=str(row.get("platform_role")) if row else None,
                    ip_hash=ip_hash,
                    metadata={"reason": "invalid_credentials"},
                )
                conn.commit()
                return None
            if not verify_password(password, row.get("password_hash")):
                self._record_login_event(
                    conn,
                    user_id=row["id"],
                    event_type="login",
                    auth_source=auth_source,
                    outcome="failure",
                    actor_role=str(row.get("platform_role")),
                    ip_hash=ip_hash,
                    metadata={"reason": "invalid_password"},
                )
                conn.commit()
                return None
            self._users.update_last_login(conn, row["id"])
            self._record_login_event(
                conn,
                user_id=row["id"],
                event_type="login",
                auth_source=auth_source,
                outcome="success",
                actor_role=str(row.get("platform_role")),
                ip_hash=ip_hash,
                metadata={},
            )
            conn.commit()
        return PrincipalContext.from_user_row(row, auth_source=auth_source)

    def resolve_principal(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> PrincipalContext:
        if email and password:
            principal = self.authenticate_user(email, password)
            if principal:
                return principal
            return PrincipalContext.anonymous()
        if user_id:
            with get_connection() as conn:
                row = self._users.get_by_id(conn, user_id)
            if row and str(row.get("status") or "active") == "active":
                return PrincipalContext.from_user_row(row, auth_source=AUTH_SOURCE_BASIC)
        return PrincipalContext.anonymous()

    def resolve_principal_for_telegram(
        self,
        telegram_user_id: int | None,
        *,
        telegram_chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> PrincipalContext | None:
        """Platform user + channel link; создаёт user при первом контакте."""
        if telegram_user_id is None:
            return None
        ext_id = str(int(telegram_user_id))
        with get_connection() as conn:
            link = self._channels.get_by_channel_external(
                conn, channel=CHANNEL_TELEGRAM, external_user_id=ext_id
            )
            row = None
            if link:
                row = self._users.get_by_id(conn, link["user_id"])
            if row is None:
                row = self._users.get_by_telegram_user_id(conn, int(telegram_user_id))
            if row is None:
                env_role = resolve_role_for_telegram_user(int(telegram_user_id))
                legacy_role = "admin" if env_role == "admin" else "user"
                uid = self._users.insert(
                    conn,
                    int(telegram_user_id),
                    telegram_chat_id=telegram_chat_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    role=legacy_role,
                )
                row = self._users.get_by_id(conn, uid)
            if not row:
                return None
            uid = row["id"]
            if not isinstance(uid, uuid.UUID):
                uid = uuid.UUID(str(uid))
            if not link:
                self._channels.insert(
                    conn,
                    user_id=uid,
                    channel=CHANNEL_TELEGRAM,
                    external_user_id=ext_id,
                    external_chat_id=(
                        str(telegram_chat_id) if telegram_chat_id is not None else None
                    ),
                    metadata={"username": username} if username else {},
                )
            conn.commit()
        if not row or str(row.get("status") or "active") != "active":
            return None
        principal = PrincipalContext.from_user_row(row, auth_source=AUTH_SOURCE_TELEGRAM)
        # Env overrides для retrieval_role, если в БД employee но user в TELEGRAM_GUEST list
        env_role = resolve_role_for_telegram_user(int(telegram_user_id))
        if env_role != principal.retrieval_role:
            return PrincipalContext(
                user_id=principal.user_id,
                platform_role=principal.platform_role,
                retrieval_role=env_role,
                permissions=principal.permissions,
                auth_source=principal.auth_source,
                is_authenticated=True,
                email=principal.email,
                display_name=principal.display_name,
                actor_id=principal.actor_id,
            )
        return principal

    def bootstrap_admin_if_needed(self) -> bool:
        """
        Idempotent: создать bootstrap admin из env, если активных admin ещё нет.

        Env: ``INITIAL_ADMIN_EMAIL``, ``INITIAL_ADMIN_PASSWORD`` (оба обязательны для создания).
        """
        email = (os.getenv("INITIAL_ADMIN_EMAIL") or "").strip().lower()
        password = os.getenv("INITIAL_ADMIN_PASSWORD") or ""
        if not email or not password.strip():
            logger.info(
                "[assistant-flow] identity bootstrap: INITIAL_ADMIN_EMAIL/PASSWORD not set — skip"
            )
            return False
        with get_connection() as conn:
            if self._users.count_by_platform_role(conn, PLATFORM_ADMIN) > 0:
                existing = self._users.get_by_email(conn, email)
                if existing:
                    logger.info(
                        "[assistant-flow] identity bootstrap: admin exists (email already registered)"
                    )
                    conn.commit()
                    return False
                logger.info(
                    "[assistant-flow] identity bootstrap: platform admin exists — skip new bootstrap"
                )
                return False
            if self._users.get_by_email(conn, email):
                logger.info(
                    "[assistant-flow] identity bootstrap: email exists but no admin role — skip auto-promote"
                )
                return False
        try:
            uid = self.create_user(
                email=email,
                password=password,
                display_name="Bootstrap Admin",
                platform_role=PLATFORM_ADMIN,
                retrieval_role="admin",
            )
            logger.info(
                "[assistant-flow] identity bootstrap: created platform admin user_id=%s "
                "(use INITIAL_ADMIN_EMAIL with HTTP Basic auth; password not logged)",
                uid,
            )
            try:
                self.record_bootstrap_event(user_id=uid, created=True)
            except Exception:
                pass
            return True
        except ValueError as exc:
            logger.warning("[assistant-flow] identity bootstrap: %s", exc)
            return False

    def record_access_denied(
        self,
        *,
        path: str,
        method: str,
        auth_mode: str,
        ip_hash: str | None = None,
    ) -> None:
        """Foundation audit: неавторизованный доступ к защищённому маршруту."""
        try:
            with get_connection() as conn:
                self._record_login_event(
                    conn,
                    user_id=None,
                    event_type="access.denied",
                    auth_source=auth_mode,
                    outcome="failure",
                    actor_role=None,
                    ip_hash=ip_hash,
                    metadata={"path": path, "method": method.upper()},
                )
                conn.commit()
        except Exception as exc:
            logger.debug("record_access_denied: %s", exc)

    def record_bootstrap_event(self, *, user_id: uuid.UUID, created: bool) -> None:
        try:
            with get_connection() as conn:
                self._record_login_event(
                    conn,
                    user_id=user_id,
                    event_type="bootstrap.admin",
                    auth_source="startup",
                    outcome="success",
                    actor_role=PLATFORM_ADMIN,
                    ip_hash=None,
                    metadata={"created": created},
                )
                conn.commit()
        except Exception as exc:
            logger.debug("record_bootstrap_event: %s", exc)

    def _record_login_event(
        self,
        conn: Any,
        *,
        user_id: uuid.UUID | None,
        event_type: str,
        auth_source: str,
        outcome: str,
        actor_role: str | None,
        ip_hash: str | None,
        metadata: dict[str, Any],
    ) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_login_events (
                        user_id, event_type, auth_source, outcome, actor_role, ip_hash, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        event_type,
                        auth_source,
                        outcome,
                        actor_role,
                        ip_hash,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
        except Exception as exc:
            logger.debug("auth_login_events insert skipped: %s", exc)


def hash_client_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.strip().encode("utf-8")).hexdigest()[:32]


def get_identity_service() -> IdentityService:
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service


def run_identity_bootstrap() -> bool:
    """Точка входа для startup (Admin API lifespan)."""
    try:
        return get_identity_service().bootstrap_admin_if_needed()
    except Exception as exc:
        logger.warning("[assistant-flow] identity bootstrap failed: %s", exc)
        return False
