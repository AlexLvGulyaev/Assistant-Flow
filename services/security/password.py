"""Password hashing (P9.1) — bcrypt."""

from __future__ import annotations

import bcrypt


def create_password_hash(plain_password: str) -> str:
    """Хеш пароля для хранения в ``app_users.password_hash``."""
    pwd = (plain_password or "").strip()
    if not pwd:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """Проверка пароля против сохранённого хеша."""
    if not password_hash or not (plain_password or "").strip():
        return False
    try:
        return bcrypt.checkpw(
            plain_password.strip().encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False
