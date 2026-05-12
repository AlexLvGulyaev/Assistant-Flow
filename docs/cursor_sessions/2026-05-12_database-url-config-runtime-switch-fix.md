# Session: database_url on AppConfig (P6.10 runtime switch fix)

**Date:** 2026-05-12  
**Issue:** `AppConfig` had no `database_url` attribute; `python -c "… c.database_url …"` failed with `AttributeError`, while PostgreSQL worked via `os.environ["DATABASE_URL"]` and `repositories.connection.get_database_url()`.

**Fix:** Single typed snapshot of `DATABASE_URL` on `AppConfig`, populated in `load_config()` from the same env var (after `load_dotenv` / `_load_dotenv`). P6.10 paths that gate DB access now prefer `config.database_url`; `get_database_url()` unchanged (still reads `DATABASE_URL` after dotenv — contract aligned in docstring).

---

## Files touched

| File | Change |
|------|--------|
| `utils/config.py` | `database_url: Optional[str]` on `AppConfig`; `load_config()` sets `database_url=_optional_stripped_url("DATABASE_URL")` |
| `services/retrieval/runtime_manager.py` | Skip `get_connection` when `database_url` empty; cache effective name when skipping DB |
| `services/admin_service.py` | All former `(os.getenv("DATABASE_URL") or "").strip()` → `(self._config.database_url or "").strip()` |
| `services/admin_knowledge_indexer.py` | Postgres gating via `self._config.database_url` |
| `scripts/admin_index_documents.py` | `db_url` from `load_config().database_url` |
| `admin_api/deps.py` | `database_url_configured` from `cfg.database_url`; removed unused `os` import |
| `repositories/connection.py` | Docstring on `get_database_url()` references `AppConfig.database_url` |
| `scripts/test_retrieval_runtime_switch_smoke.py` | Assert `database_url` matches env when set; `RetrievalBackendManager` test `AppConfig` includes `database_url=db_url` |

---

## Verification

- Host / workspace: `python -c "from utils.config import load_config; c=load_config(); print(bool(c.database_url))"` → `True` when `.env` has `DATABASE_URL`.
- **Docker:** existing image `portfolio-test-assistant-flow-1` still runs **old code** until `docker compose build assistant-flow` (or equivalent) and recreate container; then user’s `docker exec … c.database_url` checks succeed.

---

## No commit

Per request: fix applied locally; rebuild container before final acceptance.
