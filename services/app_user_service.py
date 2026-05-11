"""Application service for Telegram users (table app_users)."""

from __future__ import annotations

import uuid

from repositories.connection import get_connection
from repositories.user_repository import UserRepository


class AppUserService:
    """Координация app_users."""

    def __init__(self, repository: UserRepository | None = None) -> None:
        self._repository = repository or UserRepository()

    def ensure_user_for_telegram(
        self,
        telegram_user_id: int,
        *,
        telegram_chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> uuid.UUID:
        """Найти или создать app_users по telegram_user_id."""
        with get_connection() as conn:
            row = self._repository.get_by_telegram_user_id(conn, telegram_user_id)
            if row:
                uid = row["id"]
                patch: dict[str, object] = {}
                if telegram_chat_id is not None:
                    patch["telegram_chat_id"] = telegram_chat_id
                if username is not None:
                    patch["username"] = username
                if first_name is not None:
                    patch["first_name"] = first_name
                if last_name is not None:
                    patch["last_name"] = last_name
                if patch:
                    self._repository.update_profile(conn, uid, **patch)
                return uid
            return self._repository.insert(
                conn,
                telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

    def set_role(self, telegram_user_id: int, role: str) -> None:
        """Обновить роль по telegram_user_id."""
        with get_connection() as conn:
            row = self._repository.get_by_telegram_user_id(conn, telegram_user_id)
            if not row:
                raise ValueError("user not found for telegram id")
            self._repository.update_profile(conn, row["id"], role=role)
