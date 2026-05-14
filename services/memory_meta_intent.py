"""Memory v1.2: deterministic meta-intent detection (dialog about dialog). No LLM / embeddings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class MemoryMetaIntentKind(str, Enum):
    PREVIOUS_QUESTION = "previous_question"
    CONVERSATION_SUMMARY = "conversation_summary"
    PREVIOUS_ANSWER_ABOUT_TOPIC = "previous_answer_about_topic"


@dataclass(frozen=True)
class MemoryMetaIntent:
    kind: MemoryMetaIntentKind
    """Lowercased substring to scan in turns (topic intent only)."""
    topic_substring: str | None = None


def _extract_topic_after_prepositions(ql: str) -> str | None:
    """Russian 'про X', 'об X', 'о X' — short topic tail."""
    for pat in (
        r"\bпро\s+(.{1,120}?)(?:[?.,!]|$)",
        r"\bоб\s+(.{1,120}?)(?:[?.,!]|$)",
        r"\bо\s+(.{1,120}?)(?:[?.,!]|$)",
    ):
        m = re.search(pat, ql, flags=re.IGNORECASE | re.DOTALL)
        if m:
            t = (m.group(1) or "").strip()
            t = re.sub(r"\s+", " ", t).strip(" \t\"'«»")
            if 2 <= len(t) <= 120:
                return t[:120]
    return None


def detect_memory_meta_intent(query: str) -> MemoryMetaIntent | None:
    """
    Heuristic router: meta questions about the current conversation vs KB RAG queries.

    Returns None → caller should use normal RAG retrieval path.
    """
    q = (query or "").strip()
    if len(q) < 8 or len(q) > 420:
        return None
    ql = q.lower()

    # --- Topic recall (must include conversational anchor + topic cue) ---
    topic_anchor = (
        "что ты уже сказал" in ql
        or "что вы уже сказали" in ql
        or "что было сказано" in ql
        or "из нашей беседы" in ql
        or "из беседы" in ql
        or "нашей беседы про" in ql
        or "известно из нашей беседы" in ql
    )
    if topic_anchor:
        topic = _extract_topic_after_prepositions(ql)
        if topic:
            return MemoryMetaIntent(
                MemoryMetaIntentKind.PREVIOUS_ANSWER_ABOUT_TOPIC,
                topic_substring=topic.lower(),
            )
        # Anchor without extractable topic: still meta, broad scan
        return MemoryMetaIntent(
            MemoryMetaIntentKind.PREVIOUS_ANSWER_ABOUT_TOPIC,
            topic_substring=None,
        )

    # --- Conversation summary ---
    if "что мы обсуждали" in ql or "что мы обсуждаем" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.CONVERSATION_SUMMARY)
    if "о чем мы говорили" in ql or "о чём мы говорили" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.CONVERSATION_SUMMARY)
    if "какие темы" in ql and ("затронули" in ql or "обсуждали" in ql or "говорили" in ql):
        return MemoryMetaIntent(MemoryMetaIntentKind.CONVERSATION_SUMMARY)
    if "резюмируй" in ql and ("бесед" in ql or "разговор" in ql or "диалог" in ql):
        return MemoryMetaIntent(MemoryMetaIntentKind.CONVERSATION_SUMMARY)
    if "кратко резюмируй" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.CONVERSATION_SUMMARY)

    # --- Previous user question ---
    if "предыдущий вопрос" in ql or "прошлый вопрос" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.PREVIOUS_QUESTION)
    if "предыдущ" in ql and "вопрос" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.PREVIOUS_QUESTION)
    if "повтори" in ql and "вопрос" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.PREVIOUS_QUESTION)
    if "что я спросил" in ql or "что я спрашивал" in ql:
        return MemoryMetaIntent(MemoryMetaIntentKind.PREVIOUS_QUESTION)
    if ("что спросил" in ql or "что спрашивал" in ql) and (
        "до" in ql or "раньше" in ql or "перед" in ql
    ):
        return MemoryMetaIntent(MemoryMetaIntentKind.PREVIOUS_QUESTION)

    return None
