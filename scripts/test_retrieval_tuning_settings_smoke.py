#!/usr/bin/env python3
"""
P6.12: smoke retrieval tuning (platform_settings.retrieval_tuning) + validation.

- Pure validation without DB;
- With DATABASE_URL: partial PUT, effective merge, DELETE clear, overlap >= size rejected.

Run from repo root:
  python scripts/test_retrieval_tuning_settings_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from dataclasses import replace

    from services.retrieval.retrieval_tuning import (
        TUNING_REQUIRES_REINDEX_KEYS,
        apply_db_overrides_to_config,
        strip_db_keys_matching_env,
        validate_and_normalize_patch,
    )
    from utils.config import AppConfig, load_config

    cfg = load_config()

    # --- validation unit tests (no DB) ---
    try:
        validate_and_normalize_patch(cfg, {}, {"rag_top_k": 0})
        return _fail("rag_top_k=0 must be rejected")
    except ValueError:
        pass

    try:
        validate_and_normalize_patch(cfg, {}, {"rag_chunk_size": 500, "rag_chunk_overlap": 500})
        return _fail("overlap >= chunk_size must be rejected")
    except ValueError:
        pass

    try:
        validate_and_normalize_patch(cfg, {}, {"unknown": 1})
        return _fail("unknown key must be rejected")
    except ValueError:
        pass

    p = validate_and_normalize_patch(cfg, {}, {"rag_top_k": 5})
    if p.get("rag_top_k") != 5:
        return _fail("partial normalize rag_top_k")

    merged = {**{}, **p}
    eff = apply_db_overrides_to_config(cfg, merged)
    if eff.rag_top_k != 5:
        return _fail("effective rag_top_k after merge")

    # strip keys matching env
    base2 = replace(cfg, rag_top_k=7)
    stripped = strip_db_keys_matching_env({"rag_top_k": 7}, base2)
    if stripped:
        return _fail("strip should remove env-equal rag_top_k")

    # --- optional Postgres integration ---
    db_url = (cfg.database_url or "").strip()
    if not db_url:
        print("[retrieval_tuning_smoke] SKIP DB tests: DATABASE_URL unset")
        print("OK: test_retrieval_tuning_settings_smoke (validation only)")
        return 0

    try:
        import psycopg  # noqa: F401, PLC0415
    except ImportError:
        print("[retrieval_tuning_smoke] SKIP DB tests: psycopg not installed")
        print("OK: test_retrieval_tuning_settings_smoke (validation only)")
        return 0

    from repositories.connection import get_connection
    from repositories.platform_settings_repository import KEY_RETRIEVAL_TUNING, PlatformSettingsRepository
    from services.admin_service import AdminService

    repo = PlatformSettingsRepository()
    with get_connection() as conn:
        repo.delete_setting(conn, KEY_RETRIEVAL_TUNING)
        conn.commit()

    svc = AdminService(cfg)
    target_top = 7 if int(cfg.rag_top_k) != 7 else 6
    snap0 = svc.get_retrieval_tuning()
    if snap0.get("db_overrides"):
        return _fail("db_overrides should be empty after delete")

    eff0 = snap0["effective"]["rag_top_k"]
    if eff0 != cfg.rag_top_k:
        return _fail("effective top_k should match env when no DB row")

    out1 = svc.put_retrieval_tuning({"rag_top_k": target_top})
    if out1["effective"]["rag_top_k"] != target_top:
        return _fail("PUT partial rag_top_k effective mismatch")
    if out1.get("reindex_required"):
        return _fail("reindex_required should be false when only runtime key changes")

    out2 = svc.put_retrieval_tuning(
        {"rag_chunk_size": 900, "rag_chunk_overlap": 100},
    )
    if out2["effective"]["rag_chunk_size"] != 900 or out2["effective"]["rag_chunk_overlap"] != 100:
        return _fail("chunk PUT merge")
    if not out2.get("reindex_required"):
        return _fail("reindex_required should be true after chunk change")

    # overlap boundary ok
    svc.put_retrieval_tuning({"rag_chunk_overlap": 50})

    try:
        svc.put_retrieval_tuning({"rag_chunk_overlap": 900})
        return _fail("rag_chunk_overlap >= rag_chunk_size must fail")
    except ValueError:
        pass

    svc.delete_retrieval_tuning()
    snap_end = svc.get_retrieval_tuning()
    if snap_end["db_overrides"]:
        return _fail("after delete db_overrides empty")

    for k in TUNING_REQUIRES_REINDEX_KEYS:
        if snap_end["effective"][k] != getattr(cfg, k):
            return _fail(f"chunk field {k} should match env after delete")

    print("OK: test_retrieval_tuning_settings_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
