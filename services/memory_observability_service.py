"""Admin-oriented memory / chat_sessions observability (compact metadata, no secrets)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from repositories.connection import get_connection
from repositories.processing_logs_repository import ProcessingLogsRepository
from repositories.session_repository import SessionRepository
from utils.config import AppConfig, load_config

_ALLOWED_MEMORY_DETAIL_KEYS = frozenset(
    {
        "session_id",
        "user_id",
        "telegram_user_id",
        "messages_loaded",
        "messages_saved",
        "limit",
        "latency_ms",
        "command",
        "status",
        "deactivated_sessions",
        "route",
        "mode",
    }
)


def _iso_utc(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return None


def _slim_memory_details(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k in _ALLOWED_MEMORY_DETAIL_KEYS:
        if k in raw and raw[k] is not None:
            out[k] = raw[k]
    return out


def _preview_text(content: str, max_len: int = 120) -> str:
    t = (content or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


class MemoryObservabilityService:
    """Read-only operators' view: sessions, PG vs configured in-memory fallback, memory_* logs."""

    def __init__(
        self,
        *,
        sessions: SessionRepository | None = None,
        logs: ProcessingLogsRepository | None = None,
    ) -> None:
        self._sessions = sessions or SessionRepository()
        self._logs = logs or ProcessingLogsRepository()

    @staticmethod
    def database_configured() -> bool:
        try:
            from repositories.connection import get_database_url

            return bool(get_database_url().strip())
        except Exception:
            return False

    @staticmethod
    def _memory_runtime_source(cfg: AppConfig) -> str:
        if (cfg.database_url or "").strip() and cfg.telegram_pg_conversation_memory:
            return "pg"
        return "fallback_in_memory"

    def get_summary(self, *, hours: int = 24) -> dict[str, Any]:
        cfg = load_config()
        h = max(1, min(int(hours), 24 * 365))
        base = {
            "database_available": False,
            "memory_runtime_source": self._memory_runtime_source(cfg),
            "telegram_pg_conversation_memory": cfg.telegram_pg_conversation_memory,
            "database_url_configured": bool((cfg.database_url or "").strip()),
            "active_sessions_count": 0,
            "avg_turns_sessions_touched": 0.0,
            "clear_reset_events_count": 0,
            "hours": h,
            "budget_limits": {
                "max_turn_pairs": cfg.telegram_memory_max_turn_pairs,
                "max_llm_messages": cfg.telegram_memory_max_llm_messages,
            },
            "llm_conversation_tail_cap": cfg.telegram_memory_max_llm_messages,
            "chat_session_idle_timeout_seconds": cfg.chat_session_idle_timeout_seconds,
        }
        if not self.database_configured():
            return base
        try:
            with get_connection() as conn:
                active = self._sessions.count_active_sessions(conn)
                avg_turns = self._sessions.avg_turns_for_sessions_touched_within_hours(
                    conn, hours=h
                )
                cleared = self._logs.count_stage_last_hours(
                    conn, stage="memory_session_cleared", hours=h
                )
        except Exception:
            return base
        base["database_available"] = True
        base["active_sessions_count"] = active
        base["avg_turns_sessions_touched"] = round(float(avg_turns), 2)
        base["clear_reset_events_count"] = cleared
        return base

    def list_sessions(
        self,
        *,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        cfg = load_config()
        src = self._memory_runtime_source(cfg)
        lim = max(1, min(int(limit), 200))
        off = max(0, int(offset))
        out: dict[str, Any] = {
            "memory_runtime_source": src,
            "count": 0,
            "limit": lim,
            "offset": off,
            "items": [],
        }
        if not self.database_configured():
            return out
        try:
            with get_connection() as conn:
                rows = self._sessions.list_sessions_for_admin(
                    conn, active_only=active_only, limit=lim, offset=off
                )
                try:
                    clear_ids = self._logs.telegram_user_ids_with_recent_memory_clear(
                        conn, within_hours=2.0
                    )
                except Exception:
                    clear_ids = set()
        except Exception:
            return out
        items = []
        for r in rows:
            tid = r.get("telegram_user_id")
            tid_str = str(tid) if tid is not None else ""
            mc = int(r.get("messages_count") or 0)
            items.append(
                {
                    "session_id": str(r["id"]),
                    "user_id": str(r["user_id"]),
                    "telegram_user_id": tid_str,
                    "user_label": _user_label_row(r),
                    "mode": str(r.get("mode") or ""),
                    "is_active": bool(r.get("is_active")),
                    "updated_at": _iso_utc(r.get("updated_at")),
                    "messages_count": mc,
                    "turns_approx": round(mc / 2.0, 1) if mc else 0.0,
                    "memory_source": src,
                    "recent_clear_badge": tid_str in clear_ids,
                }
            )
        out["items"] = items
        out["count"] = len(items)
        return out

    def get_session_detail(self, session_id: str) -> dict[str, Any] | None:
        cfg = load_config()
        if not self.database_configured():
            return None
        try:
            sid = uuid.UUID(str(session_id).strip())
        except ValueError:
            return None
        try:
            with get_connection() as conn:
                row = self._sessions.get_session_with_user_for_admin(conn, sid)
                if not row:
                    return None
                msgs_raw = self._sessions.list_messages_for_session(
                    conn, sid, limit=80
                )
                log_rows = self._logs.list_memory_events_for_session(
                    conn, session_id_str=str(sid), limit=40
                )
                clears = self._logs.list_memory_session_cleared_for_user(
                    conn, app_user_id_str=str(row["user_id"]), limit=3
                )
        except Exception:
            return None

        msgs_chrono = list(reversed(msgs_raw))
        recent_turns: list[dict[str, str]] = []
        for m in msgs_chrono:
            role = str(m.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            recent_turns.append(
                {
                    "role": role,
                    "preview": _preview_text(str(m.get("content") or ""), 120),
                }
            )

        last_load: dict[str, Any] | None = None
        last_append: dict[str, Any] | None = None
        for lr in log_rows:
            st = str(lr.get("stage") or "")
            entry: dict[str, Any] = {
                "stage": st,
                "created_at": _iso_utc(lr.get("created_at")),
                "status": str(lr.get("status") or ""),
                "details": _slim_memory_details(lr.get("details")),
            }
            if st == "memory_load_done" and last_load is None:
                last_load = entry
            if st == "memory_append_done" and last_append is None:
                last_append = entry

        last_clear: dict[str, Any] | None = None
        if clears:
            c0 = clears[0]
            last_clear = {
                "stage": str(c0.get("stage") or ""),
                "created_at": _iso_utc(c0.get("created_at")),
                "status": str(c0.get("status") or ""),
                "details": _slim_memory_details(c0.get("details")),
            }

        cnt_dialog = sum(
            1
            for m in msgs_raw
            if str(m.get("role") or "").strip().lower() in ("user", "assistant")
        )
        max_lm = max(1, int(cfg.telegram_memory_max_llm_messages))
        trimmed = cnt_dialog > max_lm
        ml_loaded: int | None = None
        limit_pairs: Any = None
        if last_load and isinstance(last_load.get("details"), dict):
            d = last_load["details"]
            raw_ml = d.get("messages_loaded")
            if isinstance(raw_ml, int):
                ml_loaded = raw_ml
                if ml_loaded < cnt_dialog:
                    trimmed = True
            limit_pairs = d.get("limit")

        lifecycle: list[dict[str, Any]] = []
        for lr in log_rows[:18]:
            lifecycle.append(
                {
                    "stage": str(lr.get("stage") or ""),
                    "created_at": _iso_utc(lr.get("created_at")),
                    "status": str(lr.get("status") or ""),
                    "details": _slim_memory_details(lr.get("details")),
                }
            )

        tid = row.get("telegram_user_id")
        return {
            "session_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "telegram_user_id": str(tid) if tid is not None else "",
            "mode": str(row.get("mode") or ""),
            "is_active": bool(row.get("is_active")),
            "created_at": _iso_utc(row.get("created_at")),
            "updated_at": _iso_utc(row.get("updated_at")),
            "memory_source": self._memory_runtime_source(cfg),
            "messages_count": int(row.get("messages_count") or 0),
            "recent_turns": recent_turns[-24:],
            "last_memory_load": last_load,
            "last_memory_append": last_append,
            "last_clear_event": last_clear,
            "memory_lifecycle_recent": lifecycle,
            "budget": {
                "max_turn_pairs": cfg.telegram_memory_max_turn_pairs,
                "max_llm_messages": cfg.telegram_memory_max_llm_messages,
                "llm_conversation_tail_cap": cfg.telegram_memory_max_llm_messages,
                "dialog_messages_in_session": cnt_dialog,
                "last_load_messages_loaded": ml_loaded,
                "last_load_limit_pairs": limit_pairs,
                "trimmed": trimmed,
            },
        }


def _user_label_row(r: dict[str, Any]) -> str:
    un = (r.get("username") or "").strip()
    fn = (r.get("first_name") or "").strip()
    if un:
        return un if un.startswith("@") else f"@{un}"
    if fn:
        return fn
    tid = r.get("telegram_user_id")
    return f"tg:{tid}" if tid is not None else "?"
