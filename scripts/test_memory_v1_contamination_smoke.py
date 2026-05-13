#!/usr/bin/env python3
"""
Static contamination / budget-alignment checks for Memory v1 (no live Telegram).

* RAG persist: assistant must come from model answer path, not Telegram formatter.
* RAG LLM: history tail must use config cap (no stray ``history[-6:]``).
* Optional: DATABASE_URL smoke from test_memory_v1_pg_short_term_smoke patterns.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_rag_persist_uses_answer_not_telegram_reply() -> None:
    text = _read(ROOT / "interfaces" / "telegram_bot.py")
    if "assistant_text=(result.answer or \"\").strip()" not in text:
        raise AssertionError(
            "RAG path must persist assistant_text from result.answer, not telegram_reply"
        )


def test_rag_llm_history_tail_not_hardcoded_six() -> None:
    rq = _read(ROOT / "services" / "rag_query_service.py")
    if re.search(r"extend\(\s*history\[-6", rq):
        raise AssertionError("rag_query_service must not extend history[-6:…]")
    if "_history_tail_for_llm" not in rq:
        raise AssertionError("rag_query_service should define _history_tail_for_llm")


def test_memory_log_details_allowlist() -> None:
    obs = _read(ROOT / "services" / "memory_observability_service.py")
    if "_ALLOWED_MEMORY_DETAIL_KEYS" not in obs:
        raise AssertionError("memory observability must slim memory log details")


def main() -> int:
    test_rag_persist_uses_answer_not_telegram_reply()
    test_rag_llm_history_tail_not_hardcoded_six()
    test_memory_log_details_allowlist()
    print("OK: memory_v1_contamination_smoke (static checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
