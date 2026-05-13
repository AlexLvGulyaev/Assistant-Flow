"""In-memory Telegram user mode and optional RAG conversation buffer (fallback).

Основной short-term контекст для RAG в Telegram при ``DATABASE_URL`` и включённой
PG-памяти — ``chat_messages`` (см. ``ConversationMemoryService`` / ``load_telegram_rag_history_for_llm``).
Этот буфер используется как fallback, если PG-память выключена или БД недоступна.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["text", "rag", "ocr"]


@dataclass
class TelegramUserState:
    mode: Mode = "text"
    rag_conversation_history: list[dict[str, str]] = field(default_factory=list)


class InMemoryTelegramUserStore:
    """Per Telegram user_id (from message.from_user.id)."""

    def __init__(self) -> None:
        self._states: dict[int, TelegramUserState] = {}

    def state_for(self, user_id: int) -> TelegramUserState:
        if user_id not in self._states:
            self._states[user_id] = TelegramUserState()
        return self._states[user_id]

    def set_mode(self, user_id: int, mode: Mode) -> None:
        self.state_for(user_id).mode = mode

    def get_mode(self, user_id: int) -> Mode:
        return self.state_for(user_id).mode

    def reset(self, user_id: int) -> None:
        st = self.state_for(user_id)
        st.mode = "text"
        st.rag_conversation_history.clear()

    def clear_rag_history_only(self, user_id: int) -> None:
        """Очистить только in-memory RAG buffer (режим не меняется)."""
        self.state_for(user_id).rag_conversation_history.clear()

    def rag_history_snapshot(self, user_id: int) -> list[dict[str, str]]:
        return list(self.state_for(user_id).rag_conversation_history)

    def append_rag_turn(self, user_id: int, user_text: str, assistant_text: str) -> None:
        st = self.state_for(user_id)
        st.rag_conversation_history.append({"role": "user", "content": user_text})
        st.rag_conversation_history.append({"role": "assistant", "content": assistant_text})
        if len(st.rag_conversation_history) > 12:
            st.rag_conversation_history = st.rag_conversation_history[-12:]
