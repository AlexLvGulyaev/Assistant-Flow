"""Application service for Telegram users (table app_users). Not wired into Telegram yet."""

from __future__ import annotations

from repositories.user_repository import UserRepository


class AppUserService:
    """Coordinates user persistence; delegates to UserRepository."""

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
    ) -> None:
        """Resolve or create app_users by telegram_user_id."""
        raise NotImplementedError

    def set_role(self, telegram_user_id: int, role: str) -> None:
        """Update role (user | admin)."""
        raise NotImplementedError
