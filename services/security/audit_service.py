"""
Security audit trail (P9.5) — отдельно от operational processing_logs.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.requests import Request

from repositories.audit_repository import insert_audit_row, list_recent, summary_counts
from repositories.connection import get_connection
from services.security.identity_service import hash_client_ip
from services.security.principal import PrincipalContext

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "access_token",
        "token",
        "authorization",
        "secret",
        "api_key",
        "refresh_token",
    }
)

_DENY_DEDUP_SECONDS = 60
_recent_denials: dict[str, float] = {}

_audit_service: AuditService | None = None


def _sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    out: dict[str, Any] = {}
    for k, v in details.items():
        lk = str(k).lower()
        if lk in _SENSITIVE_KEYS or "password" in lk or "token" in lk:
            out[k] = "[redacted]"
            continue
        if isinstance(v, dict):
            out[k] = _sanitize_details(v)
        elif isinstance(v, str) and len(v) > 4000:
            out[k] = v[:3997] + "…"
        else:
            out[k] = v
    return out


def _request_meta(request: Request | None) -> dict[str, Any]:
    if request is None:
        return {
            "path": None,
            "method": None,
            "ip_hash": None,
            "user_agent": None,
        }
    client = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:512]
    return {
        "path": request.url.path,
        "method": request.method.upper(),
        "ip_hash": hash_client_ip(client),
        "user_agent": ua or None,
    }


def _parse_target_uuid(target_id: str | uuid.UUID | None) -> uuid.UUID | None:
    if target_id is None:
        return None
    if isinstance(target_id, uuid.UUID):
        return target_id
    try:
        return uuid.UUID(str(target_id).strip())
    except ValueError:
        return None


class AuditService:
    """Bounded audit writer + reader."""

    def log_event(
        self,
        *,
        event_type: str,
        action: str,
        principal: PrincipalContext | None = None,
        request: Request | None = None,
        target_type: str | None = None,
        target_id: str | uuid.UUID | None = None,
        status: str = "success",
        reason: str | None = None,
        execution_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        meta = _request_meta(request)
        safe_details = _sanitize_details(details)
        uid = principal.user_id if principal and principal.user_id else None
        try:
            with get_connection() as conn:
                insert_audit_row(
                    conn,
                    admin_user_id=uid,
                    execution_id=execution_id,
                    event_type=event_type,
                    action=action,
                    target_type=target_type,
                    target_id=_parse_target_uuid(target_id),
                    principal_email=principal.email if principal else None,
                    platform_role=(
                        principal.platform_role if principal and principal.is_authenticated else None
                    ),
                    status=status,
                    reason=reason,
                    request_path=meta["path"],
                    request_method=meta["method"],
                    ip_hash=meta["ip_hash"],
                    user_agent=meta["user_agent"],
                    details=safe_details,
                )
                conn.commit()
        except Exception as exc:
            logger.warning("[assistant-flow] audit log skipped: %s", exc)

    def log_security_event(self, **kwargs: Any) -> None:
        kwargs.setdefault("event_type", f"security.{kwargs.get('action', 'event')}")
        self.log_event(**kwargs)

    def log_privileged_action(
        self,
        *,
        action: str,
        principal: PrincipalContext,
        request: Request | None = None,
        target_type: str | None = None,
        target_id: str | uuid.UUID | None = None,
        status: str = "success",
        reason: str | None = None,
        execution_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event_type = f"privileged.{action.replace(':', '.')}"
        self.log_event(
            event_type=event_type,
            action=action,
            principal=principal,
            request=request,
            target_type=target_type,
            target_id=target_id,
            status=status,
            reason=reason,
            execution_id=execution_id,
            details=details,
        )

    def log_auth_login_success(
        self,
        principal: PrincipalContext,
        request: Request | None = None,
    ) -> None:
        self.log_event(
            event_type="auth.login.success",
            action="login",
            principal=principal,
            request=request,
            target_type="auth",
            target_id=principal.user_id,
            status="success",
            details={"auth_source": principal.auth_source},
        )

    def log_auth_login_failure(
        self,
        *,
        email: str,
        request: Request | None = None,
        reason: str = "invalid_credentials",
    ) -> None:
        self.log_event(
            event_type="auth.login.failure",
            action="auth.login",
            principal=None,
            request=request,
            status="failure",
            reason=reason,
            details={"email": email.strip().lower()},
        )

    def log_auth_logout(
        self,
        principal: PrincipalContext | None,
        request: Request | None = None,
    ) -> None:
        self.log_event(
            event_type="auth.logout",
            action="auth.logout",
            principal=principal,
            request=request,
            status="success",
        )

    def log_permission_denied(
        self,
        *,
        principal: PrincipalContext,
        permission: str,
        request: Request | None = None,
    ) -> None:
        self.log_event(
            event_type="security.permission.denied",
            action="rbac.forbidden",
            principal=principal,
            request=request,
            status="failure",
            reason="insufficient_permissions",
            details={"permission": permission},
        )

    def log_access_denied(
        self,
        *,
        path: str,
        method: str,
        request: Request | None = None,
        reason: str = "unauthenticated",
    ) -> None:
        key = f"{method}:{path}:{reason}"
        now = time.time()
        last = _recent_denials.get(key, 0)
        if now - last < _DENY_DEDUP_SECONDS:
            return
        _recent_denials[key] = now
        self.log_event(
            event_type="security.access.denied",
            action="auth.unauthorized",
            principal=None,
            request=request,
            status="failure",
            reason=reason,
            details={"path": path, "method": method.upper()},
        )

    def log_retrieval_policy_denied(
        self,
        *,
        event_type: str,
        action: str,
        retrieval_role: str,
        retrieval_scope: str,
        dropped_total: int = 0,
        restricted_dropped: int = 0,
        denied_source: int = 0,
        kept: int = 0,
        audit_user_id: uuid.UUID | None = None,
        audit_email: str | None = None,
        audit_platform_role: str | None = None,
        execution_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """P9.6: retrieval visibility / scope deny → admin_audit_log."""
        if dropped_total <= 0 and restricted_dropped <= 0 and denied_source <= 0:
            return
        details: dict[str, Any] = {
            "retrieval_role": retrieval_role,
            "retrieval_scope": retrieval_scope,
            "dropped_total": dropped_total,
            "restricted_dropped": restricted_dropped,
            "denied_source": denied_source,
            "kept": kept,
        }
        if extra:
            details.update(extra)
        principal = None
        if audit_user_id or audit_email:
            platform_for_audit = (audit_platform_role or "").strip()
            if not platform_for_audit:
                rr = (retrieval_role or "").strip().lower()
                if rr == "admin":
                    platform_for_audit = "admin"
                elif rr == "employee":
                    platform_for_audit = "employee"
                else:
                    platform_for_audit = "end_user"
            principal = PrincipalContext(
                user_id=audit_user_id,
                email=audit_email,
                platform_role=platform_for_audit,
                retrieval_role=retrieval_role,
                permissions=frozenset(),
                is_authenticated=bool(audit_user_id or audit_email),
                auth_source="retrieval",
            )
        self.log_event(
            event_type=event_type,
            action=action,
            principal=principal,
            status="failure",
            reason="retrieval_visibility_restricted",
            execution_id=execution_id,
            details=details,
        )

    def log_document_detail_visibility_denied(
        self,
        *,
        principal: PrincipalContext,
        request: Request | None,
        document_id: str,
        document_visibility: str,
        retrieval_role: str,
        retrieval_scope: str,
    ) -> None:
        """P9.6c: denied GET /api/documents/{id}/detail (deduped)."""
        key = f"detail:{principal.user_id}:{document_id}:{document_visibility}"
        now = time.time()
        last = _recent_denials.get(key, 0)
        if now - last < _DENY_DEDUP_SECONDS:
            return
        _recent_denials[key] = now
        self.log_event(
            event_type="security.visibility.denied",
            action="documents.detail.visibility",
            principal=principal,
            request=request,
            status="failure",
            reason="document_detail_visibility_restricted",
            details={
                "document_id": document_id,
                "document_visibility": document_visibility,
                "retrieval_role": retrieval_role,
                "retrieval_scope": retrieval_scope,
            },
        )

    def get_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        status: str | None = None,
        principal_email: str | None = None,
        since_hours: int | None = 24,
    ) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = list_recent(
                conn,
                limit=min(limit, 500),
                offset=offset,
                event_type=event_type,
                status=status,
                principal_email=principal_email,
                since_hours=since_hours,
            )
        return [_row_to_api(r) for r in rows]

    def get_summary(self, *, since_hours: int = 24) -> dict[str, Any]:
        with get_connection() as conn:
            return summary_counts(conn, since_hours=min(since_hours, 24 * 90))


def _row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    created = row.get("created_at")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    tid = row.get("target_id")
    return {
        "id": str(row.get("id")),
        "principal_id": str(row["admin_user_id"]) if row.get("admin_user_id") else None,
        "principal_email": row.get("principal_email"),
        "platform_role": row.get("platform_role"),
        "event_type": row.get("event_type") or row.get("action"),
        "action": row.get("action"),
        "target_type": row.get("target_type"),
        "target_id": str(tid) if tid else None,
        "status": row.get("status") or "success",
        "reason": row.get("reason"),
        "request_path": row.get("request_path"),
        "request_method": row.get("request_method"),
        "execution_id": row.get("execution_id"),
        "details": row.get("details") or {},
        "created_at": created,
    }


def get_audit_service() -> AuditService:
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
