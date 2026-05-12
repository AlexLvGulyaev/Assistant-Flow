# Weaviate operational backend + runtime Admin UI switch — audit & implementation plan

**Scope of this document:** design-time audit and phased plan only.  
**Explicitly not done here:** no code changes, no commits, no `PROJECT_STATE.md` updates (per instruction: append PROJECT_STATE only after separate confirmation).

---

## 1. Why this audit was needed

- **P6 multi-backend retrieval** today is **env-driven** (`RAG_BACKEND`, `FAISS_INDEX_DIR`) with a **shared `RetrievalBackend` Protocol** for Chroma and FAISS, but **runtime is effectively frozen at process startup** for the Telegram bot path.
- **Weaviate** is not present; adding it as a third **operational** backend (not a one-off script) requires alignment across **indexing**, **query**, **health**, **compose**, and **multi-process** deployment (Telegram worker vs Admin API).
- **Runtime switch from Admin UI** conflicts with current **singleton / cached** patterns unless explicitly redesigned (no silent fallback, no stale in-memory FAISS after external reindex).

---

## 2. Compared / traced files (current architecture)

### 2.1 Retrieval contract

| File | Role |
|------|------|
| `services/retrieval/base.py` | **`RetrievalBackend` Protocol**: `backend_name`, `collection_count`, `reset_for_full_reindex`, `add_documents`, `delete_vectors_for_document_before_reindex`, `search`, `healthcheck`. DTOs: `RetrievalChunk`, `RetrievalSearchResult`, `RetrievalHealth`. |
| `services/retrieval/chroma_backend.py` | Wraps `ChromaRagStore`; delegates write path to store + `reset_chroma_for_reindex`. |
| `services/retrieval/faiss_backend.py` | Operational FAISS: disk persistence, manifest/embedding contract, mutating methods. **In-memory** index + chunks loaded/updated in process. |
| `services/retrieval/factory.py` | **`build_retrieval_backend`**: supports **`chroma`** and **`faiss`** only; `normalize_rag_backend` defaults empty → `chroma`. Optional `CachingRetrievalBackend` wrapper. |
| `services/cache/caching_retrieval_backend.py` | Wraps inner backend; delegates mutations; invalidates retrieval cache on reset/add/delete when cache enabled. |

### 2.2 Indexing write path

| File | Role |
|------|------|
| `services/admin_knowledge_indexer.py` | Uses **`normalize_rag_backend(self._config.rag_backend)`** from **`load_config()`** / injected `AppConfig`. Opens `ChromaBackend` or `FaissBackend`; full FAISS rebuild on single-file path when FAISS. |
| `services/admin_service.py` | Constructs `AdminKnowledgeIndexer`; `get_collection_count` / KB status use env-derived backend (Chroma count vs FAISS disk count). Reindex lifecycle logs include `retrieval_backend` / paths for FAISS. |
| `services/rag_local_indexer.py` | Takes **`RetrievalBackend`** (tooling). |
| `scripts/admin_index_documents.py` | CLI indexer; same `AdminKnowledgeIndexer`. |
| `admin_api/routes/documents.py` | Upload / reindex HTTP; delegates to `AdminService` (no backend switch API). |

### 2.3 Runtime RAG path

| File | Role |
|------|------|
| `interfaces/telegram_bot.py` | **`build_rag_query_service(config)`**: always builds **`ChromaRagStore`**, then **`build_retrieval_backend(config, chroma_store=store, embeddings=...)`**. Returns **`RagQueryService(retrieval, chat, config)`**. **`create_bot()`**: `rag_holder` dict holds singleton service; **`try_init_rag`** at startup; per RAG message uses cached service or re-inits on `None`. **`config` is captured once** from `load_config()` at `create_bot()` — **not** re-read on each message. |
| `core/orchestrator.py` | No direct retrieval backend wiring found (orchestrator is text/image routing; RAG is Telegram-side). |
| `services/rag_query_service.py` | Stores **`self._retrieval`** in constructor; **`retrieve` / `answer`** call **`self._retrieval.search(...)`** with timeout; uses `backend_name` for diagnostics. |

**Answer to mandatory Q1:** `RagQueryService` receives **`RetrievalBackend`** only via **constructor injection** at **`build_rag_query_service`** time; it does not resolve backend per request.

### 2.4 Config / env / compose

| File | Role |
|------|------|
| `utils/config.py` | `rag_backend`, `faiss_index_dir`, Chroma, RAG limits, cache flags, embeddings model, etc. **`load_config()`** reads env at call time. |
| `.env.example` | Documents core env; may lag behind optional keys (see prior env audit session logs). |
| `docker-compose.portfolio.yml` | **Postgres + Chroma + assistant-flow + admin-api + admin-ui**; **no Weaviate** service; shared `.env`; volumes for documents/outputs/storage. |

### 2.5 PostgreSQL “platform settings”

| Source | Finding |
|--------|---------|
| `database/schema.sql` | Tables include **`app_users`**, **`documents`**, **`document_versions`**, **`document_chunks`**, **`indexing_jobs`**, **`processing_logs`**, **`async_jobs`**, assets, audit, etc. **No** `app_settings` / `platform_config` / key-value settings table. |
| `repositories/*` | Document/processing repositories; no generic settings repository today. |
| `admin_api/routes/*` | health, documents, logs, summary, overview, assets — **no** retrieval-backend settings CRUD. |
| `services/admin_service.py` | Business logic for docs/reindex; **no** persisted runtime backend override. |

**Answer to mandatory Q3 (where to store active backend):** today **only env → `AppConfig`**. For Admin UI switch, **a new persisted row/table is required** (or reuse a table — none suitable without migration).

---

## 3. Proposed target architecture

### 3.1 Layering

1. **Bootstrap default:** `RAG_BACKEND` (and Weaviate/Chroma connection env) remain **process boot** configuration and safe defaults when DB is empty or unreachable.
2. **Authoritative runtime selection:** single row or small table in PostgreSQL, e.g. **`platform_settings`** with key `active_rag_backend` = `chroma` \| `faiss` \| `weaviate`, optional **`updated_at`**, **`updated_by`**, **`index_manifest_updated_at`** hints.
3. **Effective backend resolver:**  
   `effective_backend = coalesce(db_active, env_rag_backend)` with explicit rules:  
   - If DB says `weaviate` but Weaviate env URL missing → **degraded / not ready**, **no** silent fallback to Chroma.  
   - Same for any backend that fails healthcheck at switch time (operator choice: reject switch vs allow with banner — recommend **reject** or **switch + immediate health fail** on query path without fallback).

4. **`RetrievalBackendManager` (or `RagRuntime`):**
   - Owns **lazy or refreshable** instances per backend type (or single “active” instance + cold pools).
   - API sketch: `get_active_backend() -> RetrievalBackend`, `refresh_active(reason)`, `snapshot_health_all() -> dict[str, RetrievalHealth]`.
   - **FAISS stale fix:** compare **`manifest.updated_at`** (or revision) on disk vs last loaded mtime; **`refresh_active`** reloads from disk; optionally call after successful admin reindex (cross-process: Telegram still needs periodic check or IPC — see risks).

5. **`RagQueryService`:** either  
   - **A)** accept a **callable** `get_retrieval: () -> RetrievalBackend` instead of a fixed instance, or  
   - **B)** keep `RagQueryService` immutable but rebuild it when manager signals version bump (holder replaces service).

6. **Indexing:** `AdminKnowledgeIndexer` should receive **`effective_backend`** from the same resolver (or explicit parameter from Admin API “reindex target backend”) so **Documents pipeline** writes the same backend Telegram will query. **Separate concern:** “reindex all backends” vs “reindex active only” — product decision; minimum viable is **reindex active only** + explicit job for others later.

### 3.2 Multi-process (Telegram vs Admin API)

- Today **two Python processes** both call **`load_config()`**; **`get_admin_service`** is **`lru_cache(maxsize=1)`** in Admin API — config/service singleton per process.
- **DB-backed active backend** aligns processes **if** each process **re-reads** effective backend when serving traffic (or on timer), not only at import.
- **Recommendation:** `RetrievalBackendManager` reads DB **on TTL cache** (e.g. 1–5s) or **on each RAG request** (simpler, slightly more DB load). Admin API on **PUT** settings invalidates by bumping `settings_version` in DB; managers observe version.

### 3.3 Weaviate operational path (target)

- **Docker:** `weaviate` service (official image), healthcheck, optional `WEAVIATE_HOST` / `WEAVIATE_HTTP_PORT` / gRPC if needed by client.
- **Python client:** `weaviate-client` (version pinned); **schema**: single class (e.g. `AssistantFlowChunk`) with vectorizer **none** if AF supplies embeddings (matches OpenAI embedding dim), or server-side module if you later want BYOV — **operational parity** with current AF is **bring-your-own-vector** consistent with Chroma/FAISS.
- **Schema properties:** at minimum `text`, `chunk_id`, `document_id`, `document_version_id`, `source`, plus flattened metadata for filters; align with **`apply_retrieval_metadata_contract`** output keys.
- **Implement `WeaviateBackend(RetrievalBackend)`:**  
  - `add_documents` → batch insert + vectors from `embed_documents`  
  - `delete_vectors_for_document_before_reindex` → `where` filter delete by `document_id` / `source`  
  - `reset_for_full_reindex` → delete class or all objects in tenant  
  - `search` → nearVector + return metadata; map scores (distance/certainty per Weaviate version — document as backend-local)  
  - `healthcheck` / `collection_count` → aggregate count or GraphQL meta  
- **Factory:** extend `build_retrieval_backend` + `normalize_rag_backend` to include **`weaviate`**.

---

## 4. Mandatory design questions — answers

| # | Question | Answer (current / proposed) |
|---|-----------|------------------------------|
| 1 | How does `RagQueryService` get the backend? | **Injected at construction**; fixed `self._retrieval`. |
| 2 | Replace startup singleton with `RetrievalBackendManager`? | **Yes, recommended.** Singleton `RagQueryService` can remain if it holds a **reference** to manager or a **`get_retrieval` thunk**. Telegram `rag_holder` should store **manager + service factory** or rebuild service when `effective_backend` changes. |
| 3 | Best place for active backend? | **New PostgreSQL table** (minimal migration). Env = bootstrap only. |
| 4 | Admin API: read/switch/health/reindex/readiness? | **New routes** e.g. `GET/PUT /api/retrieval/settings` (active backend, version), `GET /api/retrieval/health` (all backends snapshot), `POST /api/retrieval/reindex` (optional `target_backend` body, auth required). **Readiness:** per-backend `RetrievalHealth` + PG chunk sum compare. |
| 5 | Migrations? | **`005_platform_settings.sql`** (or similar): `CREATE TABLE platform_settings (key TEXT PRIMARY KEY, value JSONB, updated_at TIMESTAMPTZ, updated_by …);` seed `active_rag_backend`. Alternatively single-row `system_config (singleton_id, active_rag_backend, …)`. |
| 6 | Env for Weaviate? | **`WEAVIATE_URL`** or `WEAVIATE_HOST`+`WEAVIATE_PORT`, **`WEAVIATE_API_KEY`** if secured, **`WEAVIATE_CLASS_NAME`** / **`WEAVIATE_GRPC_PORT`** optional; **`RAG_BACKEND=weaviate`** as bootstrap default compatibility. |
| 7 | docker-compose changes? | Add **`weaviate`** service; **`depends_on`** for assistant-flow/admin-api if Weaviate required for portfolio demo; pass env to both app containers. |
| 8 | Avoid data loss on switch? | Switching backend **does not delete** other stores; **PG remains SoT** for documents. **Risk:** user thinks “switch = migrated vectors” — UI must state **each backend has its own vector store**; switching without reindex on new backend → **empty / stale** vectors there. Optional future: export/migrate tool — out of MVP. |
| 9 | Switch without breaking in-flight RAG? | **Option A:** finish in-flight requests with old backend handle (versioned lease). **Option B (simpler):** switch is atomic at manager; in-flight uses old reference if service immutable per request — need **per-request resolve** or **short read lock**. Minimum: **document** “brief inconsistency possible”; implement **version counter** in manager. |
| 10 | Parity testing? | Extend **`scripts/test_retrieval_backend_factory.py`**; add **`test_weaviate_operational_indexing_smoke.py`** (compose or testcontainers); shared corpus golden set comparing **sources + chunk_id** presence (not raw scores across backends). |

---

## 5. Required DB / schema changes

**Minimal:**

```sql
-- Conceptual only — not applied in this audit step
CREATE TABLE platform_settings (
  key TEXT PRIMARY KEY,
  value_json JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Seed: INSERT ... ('active_rag_backend', '{"backend":"chroma"}');
```

**Optional extensions:**

- `updated_by` (admin user id if auth exists)
- `indexing_cursor` / `last_reindex_execution_id` per backend
- Store **`manifest_updated_at`** for FAISS file watcher parity

**Repository:** `PlatformSettingsRepository` with `get`, `set`, transactional updates.

**Bootstrap rule:** on empty table, insert default from `os.getenv("RAG_BACKEND")` or `chroma`.

---

## 6. Required contract / code changes (phased)

| Area | Change |
|------|--------|
| `utils/config.py` | Add Weaviate URL/auth/class name fields; keep `rag_backend` as env default. |
| `services/retrieval/base.py` | Protocol likely **sufficient**; optional `close()` / `refresh_from_disk()` for FAISS-specific interface or document in manager. |
| `services/retrieval/factory.py` | Branch `weaviate`; validate deps. |
| `services/retrieval/weaviate_backend.py` | **New** full operational implementation. |
| `services/admin_knowledge_indexer.py` | Resolve **effective** backend from DB (or passed-in override from API), not only `self._config.rag_backend`. |
| `services/admin_service.py` | Use same resolver; expose counts per backend for UI. |
| `interfaces/telegram_bot.py` | **Rebuild or refresh** RAG stack when settings version changes; avoid always constructing Chroma when active is FAISS/Weaviate (startup hygiene + cost). |
| `services/healthcheck_service.py` | **Decouple `rag` from Chroma-only**; `check_rag_readiness` should use **active** backend health + embeddings config; keep **Chroma** snapshot as one of **vector stores**, not synonym for RAG. |
| `admin_api/deps.py` | `config_readiness_summary`: add `active_rag_backend`, `weaviate_configured`, etc. |
| `admin_api/routes/` | New `retrieval.py` or `settings.py` routes + auth/audit. |
| `frontend/admin-ui` | Settings page or section under Documents/RAG: backend selector, health matrix, “reindex active backend”, warnings. |

---

## 7. Weaviate docker / config plan

- **Image:** e.g. `semitechnologies/weaviate:…` (pin digest in production README).
- **Environment:** `QUERY_DEFAULTS_LIMIT`, `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true` **only for local portfolio**; production uses API keys.
- **Networking:** internal DNS `weaviate:8080` from `assistant-flow` / `admin-api`.
- **Persistence:** named volume for Weaviate data dir.
- **Compose:** add service; extend `depends_on` where needed; document host port if operators need Weaviate console from laptop.

---

## 8. Admin API / UI plan

- **GET `/api/retrieval/overview`:** `{ env_default, db_active, effective, backends: { chroma: {...}, faiss: {...}, weaviate: {...} } }` — each with `healthcheck`, `collection_count`, `ready_for_query` boolean, `last_indexed_hint` if available.
- **PUT `/api/retrieval/active-backend`:** body `{ "backend": "weaviate" }` — validate allowed set; run preflight health; persist; return new effective + warnings. **No silent fallback** if preflight fails.
- **POST `/api/documents/reindex`:** extend existing or add `?target_backend=` — must match active for MVP or explicitly allow “reindex Weaviate while inactive” for warm-up (advanced).
- **UI:** show **three** health cards; **effective** badge; disable RAG mode in Telegram text copy if not ready (optional cross-surface).

---

## 9. Runtime `RetrievalBackendManager` plan

**Responsibilities:**

1. Load **effective backend id** (DB + env fallback).
2. Lazily construct **ChromaRagStore** only when chroma path needed (optimization).
3. Maintain **Weaviate client** lifecycle (connection pool).
4. **FAISS:** track `manifest_path` mtime; on mismatch vs in-memory, **`reload()`** or recreate `FaissBackend`.
5. Expose **`settings_generation: int`** bumped on every successful PUT from Admin API (Admin API writes DB; manager in other process polls generation).

**Telegram integration:**

- Replace `rag_holder["service"]` pattern with **`rag_runtime: RagRuntime`** holding manager + optional cached `RagQueryService`.
- On each RAG request: if `manager.generation != cached_generation`, rebuild `RagQueryService` with new retrieval backend.

**Admin API integration:**

- `AdminService` / indexer: call resolver at start of `run_reindex` / `upload_txt_and_index`.

---

## 10. Stale FAISS in-memory fix plan

| Approach | Pros | Cons |
|----------|------|------|
| **Reload on manifest `updated_at` / mtime** | Cheap; works with current disk persistence | Cross-process: indexer in admin-api, bot in assistant-flow — bot must poll or bump generation in DB |
| **Per-request new `FaissBackend`** | Always fresh | Heavy (reload index from disk each time) |
| **Manager `refresh_if_stale()`** before `search` | Balanced | Implement generation / mtime check |

**Recommended:** **DB `settings_generation` bump** after successful FAISS reindex (in indexer finalize) **+** optional **mtime** check as backup; Telegram manager compares generation on each RAG request or every N seconds.

---

## 11. Testing plan

1. **Unit:** `normalize_rag_backend`, factory errors for missing Weaviate URL.
2. **Integration (docker compose):** Weaviate up; create schema; indexer smoke; retrieval smoke; **switch** chroma → weaviate → verify **no** Chroma query path used (instrument logs / assert mock).
3. **Parity:** same three chunks indexed to three backends; assert metadata keys `source`, `chunk_id`, `document_id` present; scores not compared across backends.
4. **Regression:** existing Chroma/FAISS smokes still green when `active` unchanged.
5. **Concurrency:** two parallel RAG requests during switch — acceptable behavior documented + optional version lock.

---

## 12. Risks

| Risk | Mitigation |
|------|------------|
| **Split-brain** (Admin API indexes, Telegram old backend) | DB generation bump + manager refresh; log `effective_backend` on each RAG. |
| **Silent Chroma fallback** | Explicit errors in factory and UI; remove Chroma-only assumptions in `check_rag_readiness`. |
| **Weaviate schema drift** | Versioned class name or migration tool; startup ensure-schema. |
| **Security** | Protect `PUT` active-backend; audit log row. |
| **Performance** | Don’t reload FAISS full index per request; use generation/mtime. |
| **Operator confusion** | UI copy: switching backend **does not copy vectors**; reindex required. |

---

## 13. Phased implementation plan

| Phase | Deliverable |
|-------|-------------|
| **P0** | Migration `platform_settings` + repository + seed + `GET` effective backend (read-only API). |
| **P1** | `RetrievalBackendManager` + wire **Telegram** + **Admin indexer** to **effective** backend (still env-only if DB empty). No UI switch yet. |
| **P2** | `WeaviateBackend` + compose + env + factory branch + operational indexer path + smoke tests. |
| **P3** | Admin **PUT** switch + preflight + audit; UI panel; bump generation on reindex/switch. |
| **P4** | Health report refactor (per-backend RAG readiness); Overview/RAG pages. |
| **P5** | Hardening: lease/lock for switch, optional “reindex non-active backend”, metrics. |

---

## 14. FAISS operational check vs env (relation to this work)

- **Today:** FAISS operational path is driven by **`RAG_BACKEND=faiss`** (+ `FAISS_INDEX_DIR`, OpenAI for embeddings) at **`load_config()`** time in each process.
- **After runtime switch:** env remains **bootstrap**; **active** `faiss` comes from DB. **Env changes alone** are insufficient once UI owns selection — unless DB is uninitialized and falls back to env.

---

## 15. Files to touch later (implementation checklist — not executed now)

- `database/migrations/005_*.sql`, `database/schema.sql` (aggregated doc if you maintain single file)
- `repositories/platform_settings_repository.py` (new)
- `services/retrieval/weaviate_backend.py` (new)
- `services/retrieval/runtime.py` or `retrieval_backend_manager.py` (new)
- `interfaces/telegram_bot.py`, `services/admin_knowledge_indexer.py`, `services/admin_service.py`
- `services/healthcheck_service.py`, `admin_api/routes/*.py`, `admin_api/deps.py`
- `docker-compose.portfolio.yml`, `.env.example`
- `frontend/admin-ui` — new page or settings section
- `scripts/test_*`, `PROJECT_STATE.md` (**after explicit approval**)

---

*End of audit / plan document.*
