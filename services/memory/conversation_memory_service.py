"""
Сервис доступа к persistent dialog history (PostgreSQL chat_messages).

Отдельный **memory subsystem**: не спрятан в orchestrator, не смешан с KB retrieval.
Не semantic memory retrieval и не hybrid с KB — только чистые user/assistant реплики.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from services.chat_session_service import ChatSessionService
from services.memory.base import (
    ConversationMemoryRecord,
    MemoryBudgetPolicy,
)
from services.runtime_lifecycle_service import RuntimeLifecycleService


def _trim(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    t = s or ""
    return t if len(t) <= max_chars else t[:max_chars]


def _row_to_record(row: dict[str, Any]) -> ConversationMemoryRecord:
    md = row.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    return ConversationMemoryRecord(
        message_id=str(row["id"]),
        session_id=str(row["session_id"]),
        user_id=str(row["user_id"]),
        role=str(row["role"]),
        content=str(row.get("content") or ""),
        created_at=row["created_at"],
        metadata=dict(md),
        execution_id=str(row["execution_id"]) if row.get("execution_id") else None,
    )


class ConversationMemoryService:
    """
    Read/write dialog history: budget discipline, stable ordering, compact operational logs.

    Запись идёт через `ChatSessionService` (PostgreSQL SoT); этот класс — единая точка
    политики memory для приложения (без ad-hoc list последних сообщений снаружи).
    """

    def __init__(
        self,
        *,
        chat_sessions: ChatSessionService | None = None,
        policy: MemoryBudgetPolicy | None = None,
    ) -> None:
        self._sessions = chat_sessions or ChatSessionService()
        self._policy = policy or MemoryBudgetPolicy()

    def get_recent_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        return self._load_budgeted(session_id, limit=limit)

    def get_session_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        """Семантически то же, что get_recent_messages (alias для явного API)."""
        return self._load_budgeted(session_id, limit=limit)

    def _load_budgeted(self, session_id: str, *, limit: int) -> list[ConversationMemoryRecord]:
        t0 = time.monotonic()
        sid = uuid.UUID(str(session_id))
        fetch_limit = max(1, min(int(limit), self._policy.max_recent_messages, 500))
        raw = self._sessions.list_recent_messages_raw(sid, limit=fetch_limit)
        # raw: newest first; выдача — chronological после reverse
        budget_applied = False
        picked: list[dict[str, Any]] = []
        total_chars = 0
        max_msg = self._policy.max_message_chars
        budget = max(0, int(self._policy.total_memory_chars_budget))
        for row in raw:
            c = _trim(str(row.get("content") or ""), max_msg)
            room = budget - total_chars
            if room <= 0:
                if picked:
                    budget_applied = True
                break
            if len(c) > room:
                budget_applied = True
                c = c[:room]
            row = {**row, "content": c}
            picked.append(row)
            total_chars += len(c)
        picked.reverse()
        records = [_row_to_record(r) for r in picked]
        latency_ms = int((time.monotonic() - t0) * 1000)
        print(
            "[assistant-flow] memory: "
            f"session_id={session_id} messages_loaded={len(records)} "
            f"budget_applied={'true' if budget_applied else 'false'} "
            f"limit={fetch_limit} latency_ms={latency_ms}",
            flush=True,
        )
        return records

    def append_user_message(
        self,
        session_id: str,
        user_id: str,
        content: str,
        *,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        emit_log: bool = True,
    ) -> str:
        return self._append(
            session_id,
            user_id,
            role="user",
            content=content,
            execution_id=execution_id,
            metadata=metadata,
            emit_log=emit_log,
        )

    def append_assistant_message(
        self,
        session_id: str,
        user_id: str,
        content: str,
        *,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        emit_log: bool = True,
    ) -> str:
        return self._append(
            session_id,
            user_id,
            role="assistant",
            content=content,
            execution_id=execution_id,
            metadata=metadata,
            emit_log=emit_log,
        )

    def _append(
        self,
        session_id: str,
        user_id: str,
        *,
        role: str,
        content: str,
        execution_id: str | None,
        metadata: dict[str, Any] | None,
        emit_log: bool = True,
    ) -> str:
        t0 = time.monotonic()
        sid = uuid.UUID(session_id)
        uid = uuid.UUID(user_id)
        body = _trim(content, self._policy.max_message_chars)
        meta = {**(metadata or {}), "memory_layer": "dialog_history"}
        mid = self._sessions.record_message(
            sid,
            uid,
            role=role,
            content=body,
            modality="text",
            metadata=meta,
            execution_id=execution_id,
            intake_event_id=None,
        )
        if emit_log:
            latency_ms = int((time.monotonic() - t0) * 1000)
            print(
                "[assistant-flow] memory: "
                f"session_id={session_id} messages_saved=1 role={role} "
                f"message_id={mid} latency_ms={latency_ms}",
                flush=True,
            )
        return str(mid)

    def get_llm_turns_for_session(
        self,
        session_id: str,
        *,
        max_pairs: int,
        max_messages_cap: int = 24,
    ) -> list[dict[str, str]]:
        """
        Последние реплики для LLM: только role user|assistant, хронологический порядок.
        Без char-budget trim из `_load_budgeted` (отдельный read path для RAG context).
        """
        pairs = max(1, int(max_pairs))
        cap = max(2, min(int(max_messages_cap), 500))
        fetch_lim = min(cap, pairs * 2)
        sid = uuid.UUID(str(session_id))
        raw = self._sessions.list_recent_messages_raw(sid, limit=fetch_lim)
        raw = list(reversed(raw))
        out: list[dict[str, str]] = []
        for row in raw:
            role = str(row.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            c = _trim(str(row.get("content") or ""), self._policy.max_message_chars)
            out.append({"role": role, "content": c})
        return out

    def rotate_active_session_for_app_user(
        self, user_id: uuid.UUID, *, new_mode: str = "text"
    ) -> uuid.UUID:
        """Новая активная сессия; предыдущие деактивированы (сообщения сохранены)."""
        return self._sessions.rotate_active_session(user_id, mode=new_mode)


def _memory_details(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    telegram_user_id: int | None = None,
    messages_loaded: int | None = None,
    messages_saved: int | None = None,
    limit: int | None = None,
    latency_ms: int | None = None,
    command: str | None = None,
    status: str | None = None,
    deactivated_sessions: int | None = None,
    route: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if session_id is not None:
        d["session_id"] = session_id
    if user_id is not None:
        d["user_id"] = user_id
    if telegram_user_id is not None:
        d["telegram_user_id"] = telegram_user_id
    if messages_loaded is not None:
        d["messages_loaded"] = messages_loaded
    if messages_saved is not None:
        d["messages_saved"] = messages_saved
    if limit is not None:
        d["limit"] = limit
    if latency_ms is not None:
        d["latency_ms"] = latency_ms
    if command is not None:
        d["command"] = command
    if status is not None:
        d["status"] = status
    if deactivated_sessions is not None:
        d["deactivated_sessions"] = deactivated_sessions
    if route is not None:
        d["route"] = route
    if mode is not None:
        d["mode"] = mode
    return d


def load_telegram_rag_history_for_llm(
    *,
    telegram_user_id: int,
    max_pairs: int,
    max_messages_cap: int,
    lifecycle: RuntimeLifecycleService | None = None,
    execution_id: str,
    intake_event_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, str]], str | None, str | None]:
    """
    Активная сессия пользователя + последние чистые user/assistant turns из PG.

    Возвращает (history, session_id_str, app_user_id_str).
    Без DATABASE_URL или при ошибке — ([], None, None); in-memory fallback снаружи.
    """
    if not (os.getenv("DATABASE_URL") or "").strip():
        return [], None, None
    t0 = time.monotonic()
    if lifecycle:
        lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=intake_event_id,
            stage="memory_load_started",
            status="success",
            details=_memory_details(
                telegram_user_id=telegram_user_id,
                limit=max_pairs,
                route="rag",
                mode="rag",
            ),
        )
    try:
        from services.app_user_service import AppUserService

        users = AppUserService()
        uid = users.ensure_user_for_telegram(telegram_user_id)
        sessions = ChatSessionService()
        sid = sessions.get_or_create_active_session(uid, mode="rag")
        mem = ConversationMemoryService(chat_sessions=sessions)
        hist = mem.get_llm_turns_for_session(
            str(sid), max_pairs=max_pairs, max_messages_cap=max_messages_cap
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if lifecycle:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_load_done",
                status="success",
                details=_memory_details(
                    session_id=str(sid),
                    user_id=str(uid),
                    telegram_user_id=telegram_user_id,
                    messages_loaded=len(hist),
                    limit=max_pairs,
                    latency_ms=latency_ms,
                    route="rag",
                    mode="rag",
                ),
            )
        print(
            "[assistant-flow] memory: "
            f"session_id={sid} user_id={uid} telegram_user_id={telegram_user_id} "
            f"messages_loaded={len(hist)} limit_pairs={max_pairs} latency_ms={latency_ms}",
            flush=True,
        )
        return hist, str(sid), str(uid)
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        if lifecycle:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_error",
                status="error",
                details=_memory_details(
                    telegram_user_id=telegram_user_id,
                    limit=max_pairs,
                    latency_ms=latency_ms,
                    status="memory_load_failed",
                    route="rag",
                    mode="rag",
                ),
                error_text=f"{type(exc).__name__}: {exc}"[:4000],
            )
        print(
            "[assistant-flow] memory_error: "
            f"telegram_user_id={telegram_user_id} latency_ms={latency_ms} "
            f"exc={type(exc).__name__}",
            flush=True,
        )
        return [], None, None


def rotate_telegram_conversation_session_best_effort(
    *,
    telegram_user_id: int,
    new_session_mode: str,
    lifecycle: RuntimeLifecycleService | None = None,
    execution_id: str,
    intake_event_id: uuid.UUID | None = None,
    command: str,
) -> str | None:
    """
    PG: деактивировать активную сессию(и), создать новую с указанным mode.
    Возвращает новый session_id или None если пропуск/ошибка.
    """
    if not (os.getenv("DATABASE_URL") or "").strip():
        return None
    t0 = time.monotonic()
    valid_modes = ("text", "rag", "voice", "image", "career", "hr_screening")
    mode = new_session_mode if new_session_mode in valid_modes else "text"
    try:
        from services.app_user_service import AppUserService

        users = AppUserService()
        uid = users.ensure_user_for_telegram(telegram_user_id)
        sessions = ChatSessionService()
        new_sid = sessions.rotate_active_session(uid, mode=mode)
        sessions.set_mode(new_sid, mode)
        latency_ms = int((time.monotonic() - t0) * 1000)
        if lifecycle:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_session_cleared",
                status="success",
                details=_memory_details(
                    session_id=str(new_sid),
                    user_id=str(uid),
                    telegram_user_id=telegram_user_id,
                    latency_ms=latency_ms,
                    command=command,
                    status="rotated",
                    route=mode,
                    mode=mode,
                ),
            )
        print(
            "[assistant-flow] memory: "
            f"session_rotated new_session_id={new_sid} user_id={uid} "
            f"telegram_user_id={telegram_user_id} command={command} latency_ms={latency_ms}",
            flush=True,
        )
        return str(new_sid)
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        if lifecycle:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_error",
                status="error",
                details=_memory_details(
                    telegram_user_id=telegram_user_id,
                    latency_ms=latency_ms,
                    command=command,
                    status="session_rotate_failed",
                    route=mode,
                    mode=mode,
                ),
                error_text=f"{type(exc).__name__}: {exc}"[:4000],
            )
        print(
            f"[assistant-flow] memory_session_rotate skipped: {type(exc).__name__}",
            flush=True,
        )
        return None


def persist_telegram_dialog_turn_best_effort(
    *,
    telegram_user_id: int,
    telegram_chat_id: int | None,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    user_text: str,
    assistant_text: str,
    execution_id: str | None,
    session_mode: str,
    lifecycle: RuntimeLifecycleService | None = None,
    intake_event_id: uuid.UUID | None = None,
) -> None:
    """
    Best-effort: user + assistant в PostgreSQL. Не бросает наружу (ошибки → короткий лог).

    Сохраняются только чистые реплики (без RAG chunk context).
    """
    import os

    if not (os.getenv("DATABASE_URL") or "").strip():
        return

    t0 = time.monotonic()
    valid_modes = ("text", "rag", "ocr", "voice", "image", "career", "hr_screening")
    initial_mode = session_mode if session_mode in valid_modes else "text"
    route_mode = initial_mode if initial_mode in ("rag", "text") else "text"
    try:
        from services.app_user_service import AppUserService

        users = AppUserService()
        uid = users.ensure_user_for_telegram(
            telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        sessions = ChatSessionService()
        sid = sessions.get_or_create_active_session(uid, mode=initial_mode)
        if session_mode in valid_modes:
            sessions.set_mode(sid, session_mode)
        mem = ConversationMemoryService(chat_sessions=sessions)
        ut = _trim(user_text, mem._policy.max_message_chars)
        at = _trim(assistant_text, mem._policy.max_message_chars)
        mem.append_user_message(
            str(sid), str(uid), ut, execution_id=execution_id, emit_log=False
        )
        mem.append_assistant_message(
            str(sid), str(uid), at, execution_id=execution_id, emit_log=False
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        print(
            "[assistant-flow] memory: "
            f"session_id={sid} messages_saved=2 latency_ms={latency_ms}",
            flush=True,
        )
        if lifecycle and execution_id:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_append_done",
                status="success",
                details=_memory_details(
                    session_id=str(sid),
                    user_id=str(uid),
                    telegram_user_id=telegram_user_id,
                    messages_saved=2,
                    latency_ms=latency_ms,
                    status="persisted",
                    route=route_mode,
                    mode=route_mode,
                ),
            )
    except Exception as exc:
        if lifecycle and execution_id:
            lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=intake_event_id,
                stage="memory_error",
                status="error",
                details=_memory_details(
                    telegram_user_id=telegram_user_id,
                    status="persist_failed",
                    route=route_mode,
                    mode=route_mode,
                ),
                error_text=f"{type(exc).__name__}: {exc}"[:4000],
            )
        print(
            f"[assistant-flow] memory persist skipped: {type(exc).__name__}",
            flush=True,
        )
