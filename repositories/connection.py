"""PostgreSQL connection helpers. Uses DATABASE_URL (see database/db_contract.md)."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg
from dotenv import find_dotenv, load_dotenv
from psycopg import Connection, pq


def get_database_url() -> str:
    """Return ``DATABASE_URL`` after dotenv load — same value as ``AppConfig.database_url``."""
    load_dotenv(find_dotenv())
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set or empty")
    return url


@contextmanager
def get_connection(**kwargs: Any) -> Generator[Connection, None, None]:
    """
    Yield a synchronous connection.

    On normal exit, commits if a transaction is still open (e.g. code ran SQL
    without ``with conn.transaction()``). On exception, rolls back an open
    transaction. The connection is always closed afterward.

    Closing psycopg with an open transaction would otherwise roll back work and
    can leave metadata (e.g. ``document_versions``) out of sync with side
    effects already applied elsewhere in the same request.
    """
    conn = psycopg.connect(get_database_url(), **kwargs)
    try:
        yield conn
    except BaseException:
        if (
            not conn.closed
            and conn.info.transaction_status == pq.TransactionStatus.INTRANS
        ):
            try:
                conn.rollback()
            except Exception as exc:
                print(
                    f"get_connection: rollback failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
        raise
    else:
        if (
            not conn.closed
            and conn.info.transaction_status == pq.TransactionStatus.INTRANS
        ):
            conn.commit()
    finally:
        if not conn.closed:
            conn.close()


def check_connection() -> bool:
    """Return True if the database accepts a connection and answers SELECT 1."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
    except Exception as exc:
        print(
            f"check_connection: connection or query failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False

    if row is None:
        print("check_connection: SELECT 1 returned no row", file=sys.stderr)
        return False

    value = row[0]
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        print(
            f"check_connection: expected numeric 1, got {type(value).__name__}: {value!r}",
            file=sys.stderr,
        )
        return False

    if numeric != 1:
        print(
            f"check_connection: expected 1, got {numeric!r}",
            file=sys.stderr,
        )
        return False

    return True
