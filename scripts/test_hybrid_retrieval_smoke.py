#!/usr/bin/env python3
"""
Smoke: hybrid context assembly (P6.4).

DB/RAG/runtime: только внутри portfolio-контейнера после rebuild стека
(см. PROJECT_STATE — operational testing rule).

Локально без DATABASE_URL выполняются только проверки без записи в БД (KB-only / policy).
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _kb_docs() -> list:
    from langchain_core.documents import Document

    return [
        (Document(page_content="alpha_kb_segment", metadata={"source": "a.md"}), 0.11),
        (Document(page_content="beta_kb_segment", metadata={"source": "b.md"}), 0.22),
        (Document(page_content="gamma_kb_segment", metadata={"source": "c.md"}), 0.33),
    ]


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from services.hybrid_retrieval.base import HybridRetrievalPolicy
    from services.hybrid_retrieval.hybrid_context_service import HybridContextService

    svc = HybridContextService()
    kb = _kb_docs()

    # 1) Hybrid memory path выключен → только KB, hybrid_enabled false
    r_off = svc.build(
        kb_chunks=kb,
        session_id=None,
        user_id=None,
        include_memory=False,
    )
    assert r_off.hybrid_enabled is False
    assert len(r_off.items) >= 1
    assert all(it.source_type == "kb" for it in r_off.items)
    assert "alpha_kb_segment" in r_off.context_text

    # 2) include_memory true, но без session_id → KB-only как раньше
    r_no_sess = svc.build(
        kb_chunks=kb,
        session_id=None,
        user_id=None,
        include_memory=True,
    )
    assert r_no_sess.hybrid_enabled is False
    assert all(it.source_type == "kb" for it in r_no_sess.items)

    # 3) Детерминированный порядок: все kb перед memory
    if not (os.getenv("DATABASE_URL") or "").strip():
        print("SKIP-DB: остальные проверки (memory, budget) требуют PostgreSQL в контейнере")
        print("OK: test_hybrid_retrieval_smoke (kb-only)")
        return 0

    from services.app_user_service import AppUserService
    from services.chat_session_service import ChatSessionService
    from services.memory.conversation_memory_service import ConversationMemoryService

    rng = random.SystemRandom()
    tid = -(10**15 + rng.randrange(10**9))
    users = AppUserService()
    uid = users.ensure_user_for_telegram(tid, telegram_chat_id=1)
    sessions = ChatSessionService()
    sid = sessions.get_or_create_active_session(uid, mode="text")
    sid_str = str(sid)

    mem = ConversationMemoryService()
    mem.append_user_message(sid_str, str(uid), "user_line_hybrid", execution_id=None)
    mem.append_assistant_message(sid_str, str(uid), "assistant_line_hybrid", execution_id=None)

    r_on = svc.build(
        kb_chunks=kb,
        session_id=sid_str,
        user_id=str(uid),
        include_memory=True,
    )
    assert r_on.hybrid_enabled is True
    types = [it.source_type for it in r_on.items]
    first_mem = next((i for i, t in enumerate(types) if t == "memory"), None)
    last_kb = max(i for i, t in enumerate(types) if t == "kb")
    assert first_mem is not None
    assert last_kb < first_mem, "KB items must precede memory items"
    mem_items = [it for it in r_on.items if it.source_type == "memory"]
    assert all(it.session_id == sid_str for it in mem_items)
    assert all(it.role in ("user", "assistant") for it in mem_items)
    assert any("user_line_hybrid" in (it.content or "") for it in mem_items)

    # 4) Пустая memory: новая сессия без сообщений
    sid_empty = sessions.get_or_create_active_session(
        users.ensure_user_for_telegram(-(10**15 + rng.randrange(10**9)), telegram_chat_id=1),
        mode="text",
    )
    r_empty = svc.build(
        kb_chunks=kb[:1],
        session_id=str(sid_empty),
        user_id=None,
        include_memory=True,
    )
    assert r_empty.hybrid_enabled is True
    assert all(it.source_type == "kb" for it in r_empty.items)
    assert "ИСТОРИЯ ДИАЛОГА" not in r_empty.context_text

    # 5) Memory не вытесняет KB: жёсткий global cap, KB-блок сохраняет ключевой фрагмент
    from langchain_core.documents import Document as LCDocument

    tight = HybridRetrievalPolicy(
        max_kb_chunks=3,
        max_memory_messages=20,
        max_context_chars=80,
        max_memory_chars=2000,
        max_kb_chars=2000,
    )
    long_kb = [
        (
            LCDocument(
                page_content="KEEP_KB_HEAD" + "x" * 500,
                metadata={"source": "long.md"},
            ),
            0.1,
        )
    ]
    mem2 = ConversationMemoryService()
    for _ in range(5):
        mem2.append_user_message(sid_str, str(uid), "noise_memory_line", execution_id=None)
    r_tight = svc.build(
        kb_chunks=long_kb,
        session_id=sid_str,
        user_id=str(uid),
        include_memory=True,
        policy=tight,
    )
    assert "KEEP_KB_HEAD" in r_tight.context_text
    assert r_tight.items[0].source_type == "kb"
    # При малом max_context_chars memory обрезается или отсутствует в выдаче
    assert r_tight.total_context_chars <= tight.max_context_chars

    # 6) source_type / metadata roundtrip для memory
    m0 = next(it for it in r_on.items if it.source_type == "memory" and it.role == "user")
    assert m0.metadata.get("memory_layer") == "dialog_history"

    print("OK: test_hybrid_retrieval_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
