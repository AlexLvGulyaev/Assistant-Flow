"""Memory v1.2: deterministic replies for meta-intent (PG turns only, no retrieval / LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.memory_meta_intent import MemoryMetaIntent, MemoryMetaIntentKind


@dataclass(frozen=True)
class MemoryMetaAnswerResult:
    text: str
    scanned_turns: int
    matched_turns: int
    empty: bool


def _clip(s: str, max_chars: int) -> str:
    t = (s or "").strip().replace("\n", " ")
    t = re.sub(r"\s+", " ", t)
    if max_chars <= 0 or len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _topic_matches_body(topic: str, body: str) -> bool:
    bl = (body or "").lower()
    tl = (topic or "").lower().strip()
    if not tl:
        return False
    if tl in bl:
        return True
    words = [w for w in re.findall(r"[0-9a-zа-яё-]+", tl, flags=re.IGNORECASE) if len(w) >= 3]
    for w in words:
        if w in bl:
            return True
        if len(w) >= 5 and w[:5] in bl:
            return True
    return False


def build_memory_meta_reply(
    *,
    intent: MemoryMetaIntent,
    turns: list[dict[str, str]],
    max_turns_scan: int = 24,
    max_preview_chars: int = 180,
    max_bullets: int = 8,
) -> MemoryMetaAnswerResult:
    """
    ``turns``: chronological user/assistant messages from PG (current user line not included).

    Bounded output: no full history dumps.
    """
    scan = turns[-max_turns_scan:] if max_turns_scan > 0 else turns
    scanned = len(scan)

    if intent.kind is MemoryMetaIntentKind.PREVIOUS_QUESTION:
        prev_user: str | None = None
        for m in reversed(scan):
            if str(m.get("role") or "").lower().strip() == "user":
                prev_user = str(m.get("content") or "").strip()
                break
        if not prev_user:
            return MemoryMetaAnswerResult(
                text="В этой сессии ещё нет предыдущего вопроса.",
                scanned_turns=scanned,
                matched_turns=0,
                empty=True,
            )
        body = _clip(prev_user, 900)
        return MemoryMetaAnswerResult(
            text=f'Ваш предыдущий вопрос был: «{body}»',
            scanned_turns=scanned,
            matched_turns=1,
            empty=False,
        )

    if intent.kind is MemoryMetaIntentKind.CONVERSATION_SUMMARY:
        bullets: list[str] = []
        for m in scan:
            if str(m.get("role") or "").lower().strip() != "user":
                continue
            u = _clip(str(m.get("content") or ""), max_preview_chars)
            if u and u not in bullets:
                bullets.append(u)
            if len(bullets) >= max_bullets:
                break
        if not bullets:
            return MemoryMetaAnswerResult(
                text="Пока нет сохранённых реплик для краткого резюме.",
                scanned_turns=scanned,
                matched_turns=0,
                empty=True,
            )
        lines = "\n".join(f"- {b}" for b in bullets)
        n = min(len(bullets), max_bullets)
        return MemoryMetaAnswerResult(
            text=f"За последние реплики вы спрашивали (до {n} пунктов):\n{lines}",
            scanned_turns=scanned,
            matched_turns=len(bullets),
            empty=False,
        )

    # PREVIOUS_ANSWER_ABOUT_TOPIC
    topic = (intent.topic_substring or "").strip().lower()
    if intent.kind is MemoryMetaIntentKind.PREVIOUS_ANSWER_ABOUT_TOPIC and not topic:
        return MemoryMetaAnswerResult(
            text="Уточните тему, например: «Что ты уже сказал про индексацию?»",
            scanned_turns=scanned,
            matched_turns=0,
            empty=True,
        )

    hits: list[str] = []
    if topic:
        for m in reversed(scan):
            body = str(m.get("content") or "")
            if _topic_matches_body(topic, body):
                role = str(m.get("role") or "").lower().strip()
                label = "Вы" if role == "user" else "Ассистент"
                hits.append(f"{label}: {_clip(body, max_preview_chars)}")
            if len(hits) >= max_bullets:
                break

    if not hits:
        return MemoryMetaAnswerResult(
            text="В текущей беседе я не нашёл информации по этой теме.",
            scanned_turns=scanned,
            matched_turns=0,
            empty=True,
        )
    block = "\n".join(f"- {h}" for h in hits)
    return MemoryMetaAnswerResult(
        text=f"Вот что есть в недавней беседе:\n{block}",
        scanned_turns=scanned,
        matched_turns=len(hits),
        empty=False,
    )
