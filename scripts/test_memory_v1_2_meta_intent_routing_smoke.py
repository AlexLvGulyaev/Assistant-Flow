#!/usr/bin/env python3
"""Memory v1.2 smoke: meta-intent detection + deterministic reply builder (no DB / no retrieval)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.memory_meta_answer_service import build_memory_meta_reply  # noqa: E402
from services.memory_meta_intent import (  # noqa: E402
    MemoryMetaIntent,
    MemoryMetaIntentKind,
    detect_memory_meta_intent,
)


def test_kb_not_meta() -> None:
    assert detect_memory_meta_intent("Каков функционал системы Assistant Flow?") is None
    assert detect_memory_meta_intent("Как настроить RAG в Docker?") is None


def test_previous_question() -> None:
    m = detect_memory_meta_intent("О чем был мой предыдущий вопрос?")
    assert m is not None and m.kind == MemoryMetaIntentKind.PREVIOUS_QUESTION
    turns = [
        {"role": "user", "content": "Первый вопрос"},
        {"role": "assistant", "content": "Ответ 1"},
        {"role": "user", "content": "Второй вопрос про индексацию"},
        {"role": "assistant", "content": "Ответ 2"},
    ]
    r = build_memory_meta_reply(intent=m, turns=turns)
    assert "Второй вопрос" in r.text and r.matched_turns == 1


def test_summary() -> None:
    m = detect_memory_meta_intent("Что мы обсуждали?")
    assert m is not None and m.kind == MemoryMetaIntentKind.CONVERSATION_SUMMARY
    turns = [{"role": "user", "content": "Тема А"}, {"role": "assistant", "content": "Ок"}]
    r = build_memory_meta_reply(intent=m, turns=turns)
    assert "Тема А" in r.text


def test_topic() -> None:
    m = detect_memory_meta_intent("Что ты уже сказал про индексацию документов?")
    assert m is not None
    assert m.kind == MemoryMetaIntentKind.PREVIOUS_ANSWER_ABOUT_TOPIC
    assert m.topic_substring and "индексац" in m.topic_substring
    turns = [
        {"role": "user", "content": "Расскажи про индексацию"},
        {"role": "assistant", "content": "Индексация идёт через AdminKnowledgeIndexer."},
    ]
    r = build_memory_meta_reply(intent=m, turns=turns)
    assert "Индексация" in r.text or "индексац" in r.text.lower()


def test_bounded_summary() -> None:
    many = [{"role": "user", "content": f"Q{i}"} for i in range(20)]
    m = detect_memory_meta_intent("Кратко резюмируй нашу беседу")
    assert m is not None
    r = build_memory_meta_reply(intent=m, turns=many, max_bullets=4, max_turns_scan=10)
    assert r.text.count("-") <= 4


def main() -> int:
    test_kb_not_meta()
    test_previous_question()
    test_summary()
    test_topic()
    test_bounded_summary()
    print("OK: memory_v1_2_meta_intent_routing_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
