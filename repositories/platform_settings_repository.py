"""PostgreSQL key/value settings (P6.10: active RAG backend)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Json

from services.retrieval.factory import (
    KNOWN_RAG_BACKENDS,
    effective_rag_backend_from_sources,
    normalize_rag_backend,
)

KEY_ACTIVE_RAG_BACKEND = "active_rag_backend"
KEY_RETRIEVAL_TUNING = "retrieval_tuning"


class PlatformSettingsRepository:
    """Minimal ``platform_settings`` access (no silent coercion to Chroma on write)."""

    def get_setting(self, conn: Connection, key: str) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value_json FROM platform_settings WHERE key = %s",
                (key,),
            )
            row = cur.fetchone()
        if not row:
            return None
        val = row[0]
        return dict(val) if isinstance(val, dict) else None

    def set_setting(self, conn: Connection, key: str, value_json: dict[str, Any]) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO platform_settings (key, value_json, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value_json = EXCLUDED.value_json,
                    updated_at = NOW()
                """,
                (key, Json(value_json)),
            )

    def delete_setting(self, conn: Connection, key: str) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM platform_settings WHERE key = %s", (key,))

    def peek_active_rag_backend(self, conn: Connection) -> str | None:
        """
        Прочитать активный backend из БД без записи.
        Невалидное значение → ``None`` (caller использует env default).
        """
        row = self.get_setting(conn, KEY_ACTIVE_RAG_BACKEND)
        if not row:
            return None
        raw = row.get("backend")
        if not isinstance(raw, str):
            return None
        name = normalize_rag_backend(raw)
        return name if name in KNOWN_RAG_BACKENDS else None

    def get_active_rag_backend(self, conn: Connection, *, default_backend: str) -> str:
        """Эффективный backend: валидная запись в БД или ``default_backend`` (обычно env)."""
        db = self.peek_active_rag_backend(conn)
        return effective_rag_backend_from_sources(
            env_backend=default_backend,
            db_backend=db,
        )

    def set_active_rag_backend(self, conn: Connection, backend: str) -> str:
        """Сохранить backend; ``ValueError`` если не chroma/faiss/weaviate."""
        name = normalize_rag_backend(backend)
        if name not in KNOWN_RAG_BACKENDS:
            raise ValueError(
                f"unsupported active_rag_backend {name!r}; "
                f"allowed: {', '.join(sorted(KNOWN_RAG_BACKENDS))}"
            )
        self.set_setting(conn, KEY_ACTIVE_RAG_BACKEND, {"backend": name})
        return name
