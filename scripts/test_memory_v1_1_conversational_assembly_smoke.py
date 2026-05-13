#!/usr/bin/env python3
"""Memory v1.1 smoke: conversational assembly + follow-up heuristic (no live LLM / no DB)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.conversational_context_assembly import (  # noqa: E402
    build_rag_conversational_context,
    detect_followup_question,
)


def test_followup() -> None:
    assert not detect_followup_question("А для удалённых?", has_prior_dialog=False)
    assert detect_followup_question("А для удалённых?", has_prior_dialog=True)
    assert not detect_followup_question("x" * 250, has_prior_dialog=True)
    assert detect_followup_question("А сколько дней?", has_prior_dialog=True)


def test_char_trim() -> None:
    hist = [
        {"role": "user", "content": "a" * 50},
        {"role": "assistant", "content": "b" * 50},
    ]
    assy = build_rag_conversational_context(
        query="short",
        conversation_history=hist,
        max_history_messages=10,
        max_history_chars=60,
    )
    assert assy.history_trimming_chars
    assert assy.history_chars <= 60


def test_message_cap() -> None:
    many = [{"role": "user", "content": str(i)} for i in range(20)]
    assy = build_rag_conversational_context(
        query="q",
        conversation_history=many,
        max_history_messages=4,
        max_history_chars=100_000,
    )
    assert len(assy.history_for_llm) <= 4


def main() -> int:
    test_followup()
    test_char_trim()
    test_message_cap()
    print("OK: memory_v1_1_conversational_assembly_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
