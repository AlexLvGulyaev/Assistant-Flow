import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class RequestLogger:
    """SQLite logger for all outbound provider requests."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).touch(exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP,
                    provider TEXT,
                    endpoint TEXT,
                    operation TEXT,
                    input_type TEXT,
                    model TEXT,
                    duration_ms INTEGER,
                    status TEXT,
                    status_code INTEGER,
                    error_text TEXT,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    cost_rub REAL
                )
                """
            )
            cursor.execute("PRAGMA table_info(request_logs)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            required_columns = {
                "created_at": "TIMESTAMP",
                "provider": "TEXT",
                "endpoint": "TEXT",
                "operation": "TEXT",
                "input_type": "TEXT",
                "model": "TEXT",
                "duration_ms": "INTEGER",
                "status": "TEXT",
                "status_code": "INTEGER",
                "error_text": "TEXT",
                "tokens_input": "INTEGER",
                "tokens_output": "INTEGER",
                "cost_rub": "REAL",
            }
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    cursor.execute(
                        f"ALTER TABLE request_logs ADD COLUMN {column_name} {column_type}"
                    )
            connection.commit()

    def log_request(
        self,
        provider: Optional[str] = None,
        endpoint: Optional[str] = None,
        operation: Optional[str] = None,
        input_type: Optional[str] = None,
        model: Optional[str] = None,
        duration_ms: Optional[int] = None,
        status: Optional[str] = None,
        status_code: Optional[int] = None,
        error_text: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_rub: Optional[float] = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self._db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO request_logs (
                        created_at, provider, endpoint, operation, input_type, model,
                        duration_ms, status, status_code, error_text, tokens_input,
                        tokens_output, cost_rub
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_at,
                        provider,
                        endpoint,
                        operation,
                        input_type,
                        model,
                        duration_ms,
                        status,
                        status_code,
                        error_text,
                        tokens_input,
                        tokens_output,
                        cost_rub,
                    ),
                )
                connection.commit()
