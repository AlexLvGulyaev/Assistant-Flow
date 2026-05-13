"""Memory v1.1: short-term conversational context assembly for RAG (not semantic memory).

Explicit orchestration between dialog tail, current query intent, and retrieval output sizes.
Does not persist anything; safe telemetry only via callers (counts / flags).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagConversationalContextAssembly:
    """LLM-ready dialog tail plus safe assembly metadata."""

    history_for_llm: tuple[dict[str, str], ...]
    followup_question_detected: bool
    history_messages_loaded: int
    history_messages_used: int
    history_turns_used: int
    history_chars: int
    history_trimming_messages: bool
    history_trimming_chars: bool


def _normalize_history_message(msg: object) -> dict[str, str] | None:
    if not isinstance(msg, dict):
        return None
    role = str(msg.get("role") or "").strip().lower()
    if role not in ("user", "assistant"):
        return None
    return {"role": role, "content": str(msg.get("content") or "")}


def detect_followup_question(query: str, *, has_prior_dialog: bool) -> bool:
    """Lightweight heuristic for elliptical / continuation questions (no ML)."""
    if not has_prior_dialog:
        return False
    q = (query or "").strip()
    if not q:
        return False
    if len(q) > 200:
        return False
    ql = q.lower()
    starters = (
        "а ",
        "а,",
        "а если",
        "а как",
        "а для",
        "а у ",
        "а у",
        "а тогда",
        "а почему",
        "а сколько",
        "а что",
        "а где",
        "а когда",
        "почему ",
        "почему?",
        "сколько ",
        "а\n",
        "а\t",
    )
    if any(ql.startswith(s) for s in starters):
        return True
    # Short continuation-style utterances often depend on prior turn.
    if len(q) <= 42:
        return True
    return False


def build_rag_conversational_context(
    *,
    query: str,
    conversation_history: list[dict[str, str]] | None,
    max_history_messages: int,
    max_history_chars: int,
) -> RagConversationalContextAssembly:
    """
    Apply message-count cap (turn budget) then character budget on the dialog tail.

    ``max_history_messages`` aligns with ``telegram_memory_max_llm_messages``.
    ``max_history_chars`` is a separate RAG-side cap on total characters in the tail.
    """
    normalized: list[dict[str, str]] = []
    for raw in conversation_history or []:
        n = _normalize_history_message(raw)
        if n is not None:
            normalized.append(n)
    loaded = len(normalized)
    followup = detect_followup_question(query, has_prior_dialog=loaded > 0)

    cap_m = max(0, min(int(max_history_messages or 0), 500))
    tail = normalized[-cap_m:] if cap_m else []
    trim_m = loaded > len(tail)

    budget = max(0, int(max_history_chars or 0))
    trim_c = False
    if budget == 0:
        if tail:
            trim_c = True
        tail = []
    else:
        while tail:
            total = sum(len(x["content"]) for x in tail)
            if total <= budget:
                break
            tail = tail[1:]
            trim_c = True

    used = len(tail)
    hist_chars = sum(len(x["content"]) for x in tail)
    turns = sum(1 for x in tail if x["role"] == "user")

    return RagConversationalContextAssembly(
        history_for_llm=tuple(tail),
        followup_question_detected=followup,
        history_messages_loaded=loaded,
        history_messages_used=used,
        history_turns_used=turns,
        history_chars=hist_chars,
        history_trimming_messages=trim_m,
        history_trimming_chars=trim_c,
    )
