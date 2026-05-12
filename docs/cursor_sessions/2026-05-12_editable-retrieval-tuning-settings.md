# Session: Editable retrieval tuning (P6.12)

**Date:** 2026-05-12  
**Goal:** DB-backed runtime + indexing tuning via `platform_settings` key `retrieval_tuning` (JSON object), Admin API + Admin UI, Telegram RAG + indexer consume effective values without mutating global `AppConfig`.  
**Commit:** none (manual verification pending).

## Changed files

| Area | Files |
|------|--------|
| Platform settings | `repositories/platform_settings_repository.py` — `KEY_RETRIEVAL_TUNING`, `delete_setting()` |
| Tuning core | `services/retrieval/retrieval_tuning.py` — merge, validation, strip env-equal keys |
| Resolver | `services/retrieval/retrieval_tuning_resolver.py` — TTL cache (~2.5s) for effective `AppConfig` |
| Runtime manager | `services/retrieval/runtime_manager.py` — optional `tuning_resolver`; embeddings rebuilt when embedding timeout/model/key fingerprint changes |
| RAG query | `services/rag_query_service.py` — `_eff()` from resolver for top_k, max_distance, answer tokens, retrieval timeout; diagnostics embedding model from effective |
| Telegram | `interfaces/telegram_bot.py` — shared `RetrievalTuningResolver` wired into manager + `RagQueryService` |
| Admin service | `services/admin_service.py` — `_indexing_config()` uses effective tuning; overview snapshot `field_sources`; `get/put/delete_retrieval_tuning` |
| Admin API | `admin_api/routes/retrieval.py` — `GET/PUT/DELETE /api/retrieval/tuning` |
| Admin UI | `frontend/admin-ui/src/api/client.ts`, `src/pages/RetrievalSettingsPage.tsx`, `src/styles/globals.css` |
| CLI indexer | `scripts/admin_index_documents.py` — applies DB tuning when `DATABASE_URL` set |
| Smoke | `scripts/test_retrieval_tuning_settings_smoke.py` |

## `platform_settings` key

- **Key:** `retrieval_tuning`
- **Value:** JSON object with optional fields only (partial overrides). Keys equal to env defaults are stripped on PUT to keep the row minimal; empty object removes the row (`DELETE`).

## API contract

### `GET /api/retrieval/tuning`

Returns:

- `effective` — merged values for all seven fields  
- `env_defaults` — bootstrap from process `AppConfig`  
- `db_overrides` — raw keys present in DB  
- `requires_reindex_keys` — `["rag_chunk_size", "rag_chunk_overlap"]`  
- `runtime_keys` — the five runtime field names  

### `PUT /api/retrieval/tuning`

- JSON body: partial update (any subset of the seven keys).  
- `400` with clear `detail` string on unknown keys, range violations, or `rag_chunk_overlap >= rag_chunk_size` on merged effective config.  
- Response: same shape as GET plus `reindex_required: bool` if any indexing field’s **effective** value changed vs pre-commit baseline.

### `DELETE /api/retrieval/tuning`

- Removes DB overrides (`DELETE` row).  
- Response includes `reindex_required` when chunk effective values change after clearing.

## Validation rules (server)

| Field | Rule |
|-------|------|
| `rag_top_k` | int 1..20 |
| `rag_max_distance` | float 0.1..10.0 |
| `rag_answer_max_tokens` | int 100..8000 |
| `rag_retrieval_timeout` | number 5..300 → stored as `int(round(...))` |
| `rag_embedding_request_timeout` | float 5..300 |
| `rag_chunk_size` | int 200..5000 |
| `rag_chunk_overlap` | int 0..1000 and **&lt;** effective `rag_chunk_size` after merge |

## UI behavior

- Loads `/api/retrieval/overview` and `/api/retrieval/tuning`.  
- Editable numeric fields for runtime + indexing; subtle **env** / **db** chip from `field_sources` (overview) or `db_overrides` membership.  
- **Save** sends only keys whose draft values differ from last loaded `effective` (partial PUT).  
- **Clear DB overrides** → `DELETE /api/retrieval/tuning`.  
- Dirty / saved hint; inline validation message if any field empty/NaN.  
- Banner when last save returned `reindex_required`.  
- Save/clear disabled without `DATABASE_URL` (same as backend switch).

## Runtime integration

- **Telegram:** `RetrievalTuningResolver` shared by `RetrievalBackendManager` and `RagQueryService`; effective config refreshed on TTL (no container rebuild).  
- **Embeddings:** if `rag_embedding_request_timeout` or embedding model / API key presence changes, embeddings client is rebuilt on next access.  
- **Indexing / reindex:** `AdminService._indexing_config()` uses `tuning_resolver.effective_config()` + effective RAG backend; `admin_index_documents.py` merges DB tuning when Postgres URL is set.  
- **No mutation** of the frozen base `AppConfig` loaded at startup — only `dataclasses.replace` views.

## Tests

- `scripts/test_retrieval_tuning_settings_smoke.py` — validation without DB; with `DATABASE_URL` + `psycopg`: wipe key, PUT partial, chunk PUT + `reindex_required`, invalid overlap, DELETE.  
- **Note:** requires project venv or Docker image that includes `psycopg` and repo copy of the script (rebuild image after adding the file).

## Limitations

- **Cache tuning** not editable (explicit out of scope).  
- No RBAC, audit trail, per-tenant settings, async reindex, or auto-reindex after chunk change.  
- Admin UI does not split “save runtime only” vs “save indexing only” at the HTTP level — both cards submit the same merged patch of changed fields (server still validates and applies correctly).

## Next step (suggested)

- Editable cache flags / TTL / `RAG_RETRIEVAL_GENERATION` with the same `platform_settings` pattern and explicit “invalidate caches” operator note.
