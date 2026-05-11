"""
Сервис доступа к persistent dialog history (PostgreSQL chat_messages).

Отдельный **memory subsystem**: не спрятан в orchestrator, не смешан с KB retrieval.
Не semantic memory retrieval и не hybrid с KB — только чистые user/assistant реплики.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from services.chat_session_service import ChatSessionService
from services.memory.base import (
    ConversationMemoryRecord,
    MemoryBudgetPolicy,
)


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
) -> None:
    """
    Best-effort: user + assistant в PostgreSQL. Не бросает наружу (ошибки → короткий лог).

    Сохраняются только чистые реплики (без RAG chunk context).
    """
    import os

    if not (os.getenv("DATABASE_URL") or "").strip():
        return

    t0 = time.monotonic()
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
        valid_modes = ("text", "rag", "ocr", "voice", "image", "career", "hr_screening")
        initial_mode = session_mode if session_mode in valid_modes else "text"
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
    except Exception as exc:
        print(
            f"[assistant-flow] memory persist skipped: {type(exc).__name__}",
            flush=True,
        )
