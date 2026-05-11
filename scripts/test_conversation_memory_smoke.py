#!/usr/bin/env python3
"""
Smoke: dialog history foundation (P6.3).

Проверки: пустая история, детерминированный порядок, limit, total char budget,
целостность ролей user/assistant, metadata roundtrip, trim по max_message_chars.

Запуск в portfolio-контуре (контейнер assistant-flow с DATABASE_URL на postgres).
Без новых таблиц — только chat_sessions / chat_messages.
"""

from __future__ import annotations

import os
import random
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _unique_telegram_ids(rng: random.SystemRandom, n: int) -> list[int]:
    ids: set[int] = set()
    out: list[int] = []
    while len(out) < n:
        tid = -(10**15 + rng.randrange(10**9))
        if tid not in ids:
            ids.add(tid)
            out.append(tid)
    return out


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()
    if not (os.getenv("DATABASE_URL") or "").strip():
        print("SKIP: DATABASE_URL не задан — smoke пропущен")
        return 0

    from services.app_user_service import AppUserService
    from services.chat_session_service import ChatSessionService
    from services.memory.base import MemoryBudgetPolicy
    from services.memory.conversation_memory_service import ConversationMemoryService

    rng = random.SystemRandom()
    (
        tid_main,
        tid_trim,
        tid_order,
        tid_limit,
        tid_budget,
        tid_empty,
    ) = _unique_telegram_ids(rng, 6)

    users = AppUserService()
    sessions = ChatSessionService()

    # --- Пустая история (новая сессия без сообщений) ---
    uid_empty = users.ensure_user_for_telegram(tid_empty, telegram_chat_id=1)
    sid_empty = sessions.get_or_create_active_session(uid_empty, mode="text")
    mem_empty = ConversationMemoryService()
    assert mem_empty.get_recent_messages(str(sid_empty), limit=50) == []
    assert mem_empty.get_session_messages(str(sid_empty), limit=10) == []

    # --- Основной сценарий: metadata, execution_id, роли ---
    uid = users.ensure_user_for_telegram(tid_main, telegram_chat_id=1)
    sid = sessions.get_or_create_active_session(uid, mode="text")
    mem = ConversationMemoryService()
    exec_id = f"p6-memory-smoke-{uuid.uuid4().hex[:12]}"
    meta = {"p6_smoke": True, "nested": {"k": 1}}
    mem.append_user_message(
        str(sid), str(uid), "hello smoke", execution_id=exec_id, metadata=meta
    )
    mem.append_assistant_message(str(sid), str(uid), "world smoke", execution_id=exec_id)

    recent = mem.get_recent_messages(str(sid), limit=50)
    assert len(recent) >= 2, recent
    tail = recent[-2:]
    assert [r.role for r in tail] == ["user", "assistant"], [r.role for r in tail]
    assert tail[0].content == "hello smoke"
    assert tail[1].content == "world smoke"
    assert tail[0].metadata.get("p6_smoke") is True
    assert tail[0].metadata.get("memory_layer") == "dialog_history"
    assert tail[0].execution_id == exec_id
    assert tail[1].execution_id == exec_id

    # --- Trim по max_message_chars (политика) ---
    uid_trim = users.ensure_user_for_telegram(tid_trim, telegram_chat_id=1)
    sid_trim = sessions.get_or_create_active_session(uid_trim, mode="text")
    tiny = MemoryBudgetPolicy(
        max_recent_messages=50,
        max_message_chars=4,
        total_memory_chars_budget=100_000,
    )
    mem_tiny = ConversationMemoryService(policy=tiny)
    mem_tiny.append_user_message(str(sid_trim), str(uid_trim), "abcdefgh", execution_id=None)
    one = mem_tiny.get_recent_messages(str(sid_trim), limit=50)
    assert len(one) == 1
    assert one[0].content == "abcd", one[0].content
    assert one[0].role == "user"

    # --- Детерминированный порядок (chronological): несколько реплик ---
    uid_o = users.ensure_user_for_telegram(tid_order, telegram_chat_id=1)
    sid_o = sessions.get_or_create_active_session(uid_o, mode="text")
    mem_o = ConversationMemoryService()
    for i in range(3):
        mem_o.append_user_message(str(sid_o), str(uid_o), f"ORD-U{i}", execution_id=None)
        mem_o.append_assistant_message(str(sid_o), str(uid_o), f"ORD-A{i}", execution_id=None)
    chron = mem_o.get_recent_messages(str(sid_o), limit=50)
    assert [r.role for r in chron] == ["user", "assistant"] * 3
    assert [r.content for r in chron] == [
        "ORD-U0",
        "ORD-A0",
        "ORD-U1",
        "ORD-A1",
        "ORD-U2",
        "ORD-A2",
    ]

    # --- Trimming по limit (fetch последних N сообщений по времени) ---
    uid_l = users.ensure_user_for_telegram(tid_limit, telegram_chat_id=1)
    sid_l = sessions.get_or_create_active_session(uid_l, mode="text")
    mem_l = ConversationMemoryService()
    for i in range(5):
        mem_l.append_user_message(str(sid_l), str(uid_l), f"LIM-U{i}", execution_id=None)
        mem_l.append_assistant_message(str(sid_l), str(uid_l), f"LIM-A{i}", execution_id=None)
    lim_rows = mem_l.get_recent_messages(str(sid_l), limit=2)
    assert len(lim_rows) == 2
    # Последние по времени реплики — пятый user и пятый assistant
    assert [r.content for r in lim_rows] == ["LIM-U4", "LIM-A4"]
    assert [r.role for r in lim_rows] == ["user", "assistant"]

    # --- Total memory chars budget (детерминированная обрезка суммарной выдачи) ---
    uid_b = users.ensure_user_for_telegram(tid_budget, telegram_chat_id=1)
    sid_b = sessions.get_or_create_active_session(uid_b, mode="text")
    budget_pol = MemoryBudgetPolicy(
        max_recent_messages=50,
        max_message_chars=100,
        total_memory_chars_budget=25,
    )
    mem_b = ConversationMemoryService(policy=budget_pol)
    mem_b.append_user_message(str(sid_b), str(uid_b), "X" * 100, execution_id=None)
    budget_rows = mem_b.get_recent_messages(str(sid_b), limit=50)
    assert len(budget_rows) == 1
    assert len(budget_rows[0].content) == 25
    assert budget_rows[0].content == "X" * 25

    mem_b.append_assistant_message(str(sid_b), str(uid_b), "second", execution_id=None)
    budget_rows2 = mem_b.get_recent_messages(str(sid_b), limit=50)
    total_len = sum(len(r.content) for r in budget_rows2)
    assert total_len <= 25, total_len
    assert len(budget_rows2) == 2
    assert [r.role for r in budget_rows2] == ["user", "assistant"]
    assert budget_rows2[0].content == "X" * 19
    assert budget_rows2[1].content == "second"

    print("OK: test_conversation_memory_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
