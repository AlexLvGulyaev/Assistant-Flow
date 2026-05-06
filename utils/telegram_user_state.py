"""In-memory Telegram user mode and RAG conversation buffer.

TODO: Persist mode and history in PostgreSQL (`chat_sessions`, `chat_messages`)
per database/db_contract.md; replace this module with repository-backed services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["text", "rag"]


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

    def rag_history_snapshot(self, user_id: int) -> list[dict[str, str]]:
        return list(self.state_for(user_id).rag_conversation_history)

    def append_rag_turn(self, user_id: int, user_text: str, assistant_text: str) -> None:
        st = self.state_for(user_id)
        st.rag_conversation_history.append({"role": "user", "content": user_text})
        st.rag_conversation_history.append({"role": "assistant", "content": assistant_text})
        if len(st.rag_conversation_history) > 12:
            st.rag_conversation_history = st.rag_conversation_history[-12:]
