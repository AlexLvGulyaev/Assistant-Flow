#!/usr/bin/env python3
"""
Smoke: Memory v1 — app_users, chat_sessions, chat_messages, LLM-ready history, rotate.

Требует DATABASE_URL и применённую database/schema.sql.
Не пишет system/chunks в chat_messages — только user/assistant.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if not (os.getenv("DATABASE_URL") or "").strip():
        print("SKIP: DATABASE_URL not set")
        return 0

    from services.app_user_service import AppUserService
    from services.chat_session_service import ChatSessionService
    from services.memory.conversation_memory_service import (
        ConversationMemoryService,
        load_telegram_rag_history_for_llm,
        rotate_telegram_conversation_session_best_effort,
    )

    telegram_user_id = random.randint(9_000_000_000_000, 9_999_999_999_999)
    users = AppUserService()
    uid = users.ensure_user_for_telegram(telegram_user_id)
    sessions = ChatSessionService()
    sid = sessions.get_or_create_active_session(uid, mode="rag")
    mem = ConversationMemoryService(chat_sessions=sessions)

    mem.append_user_message(str(sid), str(uid), "hello smoke user")
    mem.append_assistant_message(str(sid), str(uid), "hello smoke assistant")

    turns = mem.get_llm_turns_for_session(str(sid), max_pairs=6, max_messages_cap=24)
    assert len(turns) == 2, turns
    assert turns[0]["role"] == "user" and "hello smoke user" in turns[0]["content"]
    assert turns[1]["role"] == "assistant"

    hist, sid_str, uid_str = load_telegram_rag_history_for_llm(
        telegram_user_id=telegram_user_id,
        max_pairs=6,
        max_messages_cap=24,
        lifecycle=None,
        execution_id="smoke-memory-v1",
        intake_event_id=None,
    )
    assert sid_str == str(sid), (sid_str, sid)
    assert uid_str == str(uid)
    assert len(hist) == 2

    exec_rotate = "smoke-memory-v1-rotate"
    new_sid_str = rotate_telegram_conversation_session_best_effort(
        telegram_user_id=telegram_user_id,
        new_session_mode="rag",
        lifecycle=None,
        execution_id=exec_rotate,
        intake_event_id=None,
        command="clear",
    )
    assert new_sid_str is not None
    assert new_sid_str != str(sid)

    hist2, sid2_str, _ = load_telegram_rag_history_for_llm(
        telegram_user_id=telegram_user_id,
        max_pairs=6,
        max_messages_cap=24,
        lifecycle=None,
        execution_id="smoke-memory-v1-after-rotate",
        intake_event_id=None,
    )
    assert sid2_str == new_sid_str
    assert hist2 == []

    print("OK memory_v1_pg_short_term_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
