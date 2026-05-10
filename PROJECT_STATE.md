# PROJECT_STATE.md

Operational architecture snapshot of the **assistant-flow** repository.  
Statements below are grounded in the codebase and `docker-compose.assistant.yml` as of the document generation date; items not verifiable from this repo are marked **needs verification**.

---

## 1. Project Overview

- **Purpose:** Multimodal “career / knowledge” assistant: Telegram bot (`pyTelegramBotAPI`), text via GigaChat, optional RAG over documents in **Chroma**, image generation, optional voice (STT/TTS) when configured.
- **Admin surfaces:**
  - **FastAPI Admin API** (`admin_api/`, entry `run_admin_api.py`, default port **8600**): JSON for the React admin UI.
  - **Streamlit** legacy admin (`admin_ui/app.py`, port **8501** in `docker-compose.assistant.yml`).
  - **React/Vite admin** (`frontend/admin-ui/`, dev server **5173**).
- **Primary runtime container command** (`Dockerfile`): `python run_telegram_bot.py` — **does not** start FastAPI or React by default.
- **Data planes:**
  - **PostgreSQL** (when `DATABASE_URL` set): intake, `processing_logs`, documents/versions/chunks metadata, summary queries, async job table (schema present).
  - **SQLite** (`RequestLogger`, path from config, default `logs.db`): outbound provider request logging — **separate** from PostgreSQL lifecycle logs.
  - **Chroma**: vector index; **HTTP** (`chroma_use_http`) or **local persistent** client (`chroma_persist_dir`).

---

## 2. Current Architecture

### 2.1 Backend / Admin API (`admin_api/`)

- **Framework:** FastAPI, CORS from `ADMIN_API_CORS_ORIGINS` merged with dev defaults (`localhost:5173`, etc.) — see `admin_api/app.py`.
- **Auth:** **No** authentication/authorization middleware on Admin API routes inspected; endpoints are open to callers that can reach the service (**security risk** if exposed).
- **Routers (prefix `/api` unless noted):**
  - `GET /api/health` — aggregates `run_system_healthchecks`: PostgreSQL, Chroma, RAG readiness, LLM config snapshots; overall `ok` vs `degraded` if Postgres down or RAG error (`admin_api/routes/health.py`).
  - `GET /api/overview` — KB stats, Chroma/RAG snapshots, modalities list (`text`, `rag`, `image`, `audio`, `documents`), provider status, asset/audio config flags (`admin_api/routes/overview.py`).
  - `GET /api/summary?hours=` — dashboard stats from `AdminService.get_summary_payload` (`admin_api/routes/summary.py`).
  - `GET /api/logs/recent` — capped recent `processing_logs` rows (limit ≤ 2000) (`admin_api/routes/logs.py`).
  - `GET /api/assets/preview?asset_ref=` — file response for **`image/`** and **`audio/`** refs only (`admin_api/routes/assets.py`).
  - `GET /api/documents` — document list + global index sync hints + observability slice from recent logs (`admin_api/routes/documents.py`).
  - `POST /api/documents/upload` — multipart upload, `upload_txt_and_index` (`admin_api/routes/documents.py`).
  - `POST /api/documents/reindex` — body `scope`: `all` | `document` (+ `document_id`) (`admin_api/routes/documents.py`).
  - `GET /api/documents/{document_id}/detail` — detail bundle + timeline (`admin_api/routes/documents.py`).
- **Exception handling:** Global handler returns JSON `internal_error` with truncated message (`admin_api/app.py`).
- **Shared service layer:** `AdminService` (`services/admin_service.py`) — documents, Chroma counts, reindex, logs, asset preview, summary aggregation.

### 2.2 Core assistant (`core/`)

- **`core/orchestrator.py` — `PromptOrchestrator`:** Text routing (`route_request`), prompt enhancement, image generation path via `ImageGenerationService`, optional `RuntimeLifecycleService` hooks for stages like `route_selected`, `image_text_enhancement_done`, etc. Uses `RequestLogger` for legacy SQLite logging in some paths.

### 2.3 Telegram (`interfaces/telegram_bot.py`)

- **Bot:** `telebot.TeleBot`, long-polling (`run_polling`).
- **Orchestrator:** GigaChat-based `build_orchestrator()`; separate **lazy RAG** init (`try_init_rag`, `RagQueryService`) with degraded startup if Chroma/embeddings fail (errors logged; system may continue without RAG).
- **User mode:** `InMemoryTelegramUserStore` — **text/rag mode not persisted**; code/TODO explicitly notes future PostgreSQL `chat_sessions` sync (`interfaces/telegram_bot.py`, `utils/telegram_user_state.py`).
- **Voice:** `AudioPipelineService` + STT/TTS providers from config; disabled providers log degraded startup.
- **Lifecycle:** `RuntimeLifecycleService` writes **best-effort** to PostgreSQL; failures are swallowed after stderr print.

### 2.4 Services (selected)

- **`services/rag_chroma_store.py`:** Chroma **HttpClient** or **PersistentClient**; collection name **`assistant_flow_rag`**. Reindex can reset collection or wipe local persist dir.
- **`services/rag_query_service.py`:** Retrieval + OpenAI chat answer; builds **`RagRequestDiagnostics`** / chunk diagnostics for `processing_logs` (`services/rag_types.py`); query/chunk previews redact suspected secrets.
- **`services/admin_knowledge_indexer.py`:** Indexes `.txt`/`.md`/`.pdf` from disk into Chroma + PostgreSQL `document_versions` / `document_chunks` (uses **`RAG_CHROMA_COLLECTION_NAME`** for `chroma_collection` column).
- **`services/runtime_lifecycle_service.py`:** PostgreSQL intake + processing + error logging; no-op if `DATABASE_URL` missing.
- **`services/healthcheck_service.py`:** Short-timeout probes; Chroma: HTTP heartbeat paths, client heartbeat, collection count worker; documents intentional **disabled** Docker healthcheck for Chroma image (comment in compose).
- **`services/async_job_service.py` + `async_reindex_worker.py`:** **Foundation:** PostgreSQL `async_jobs` table + enqueue/claim helpers; worker module states it does **not** start background loops; synchronous reindex remains primary (**partially implemented** orchestration).

### 2.5 Providers (`providers/`)

- **Chat:** `gigachat_provider`, `openai_chat_provider`.
- **Embeddings:** `rag_embeddings.py` (OpenAI embeddings for RAG).
- **Image:** `openai_image_provider`, `proxy_image_provider`, `image_provider` abstraction.
- **Audio:** `openai_stt_provider`, `openai_tts_provider`, `DisabledSTTProvider`, `DisabledTTSProvider`.

### 2.6 Repositories (`repositories/`)

- **`document_repository.py`:** Documents, versions, chunk metadata CRUD.
- **`processing_logs_repository.py`:** Read models for admin summary/logs (route inference, time windows, etc.).
- **`runtime_lifecycle_repository.py`:** Writes intake/processing/error rows (used by lifecycle service).
- **`connection.py`:** `DATABASE_URL` / `get_connection` — **needs verification** for connection pooling settings in production.

### 2.7 Logging / telemetry (dual system)

- **PostgreSQL `processing_logs`:** Primary source for **Admin API logs**, **RAG/Text/Audio modality pages** in React (route/stage/details JSON, truncated in API layer).
- **SQLite `RequestLogger`:** Provider-centric HTTP/completion logging; **not** the same schema as `request_logs` in PostgreSQL (`database/schema.sql` defines PostgreSQL `request_logs` — **needs verification** whether application code fully writes there or only schema exists).

---

## 3. Infrastructure

- **Compose file in repo:** `docker-compose.assistant.yml` (only file found; **no Traefik** references in repository).
- **Services defined:**
  - **`assistant-chroma`:** `chromadb/chroma:1.0.15`, port **8000**, volume **`assistant_chroma_data`** → `/data`. **No** Docker `healthcheck` (by design in comments). Networks: `assistant-net`, `n8n_default` (**external**).
  - **`assistant-flow`:** Build `Dockerfile`, `env_file: .env.server`, mounts `./data/documents`, `./outputs`, `./storage` → `/app/storage`. Networks: same externals. **Default CMD:** Telegram bot only.
  - **`assistant-admin`:** Same image, **Streamlit** `admin_ui/app.py` on **8501**, Docker healthcheck curls Streamlit health endpoint.
- **Traefik / edge routing:** **Not defined in this repository** — if used, configuration lives elsewhere (**needs verification**).
- **Rebuild/redeploy:** Standard `docker compose -f docker-compose.assistant.yml build/up` (**needs verification** for production host layout).

---

## 4. Active Services

| Service | Role | Notes |
|--------|------|--------|
| Telegram bot process | User-facing runtime | `run_telegram_bot.py` |
| FastAPI Admin API | JSON API for React | `run_admin_api.py`, port **8600** (not in compose CMD) |
| Streamlit admin | Legacy UI | Compose service `assistant-admin` |
| React dev server | Local admin UI | Vite port **5173** |
| Chroma | Vector DB | HTTP or embedded per config |

---

## 5. Database

- **Canonical schema:** `database/schema.sql` (comments reference migrations through **`002_runtime_lifecycle`**; files also include `003_document_versions_active.sql`, `004_async_jobs_foundation.sql`).
- **Relevant tables (non-exhaustive):** `app_users`, `documents`, `document_versions` ( **`is_active` unique per document** ), `document_chunks` (metadata; vectors in Chroma), `intake_events`, `chat_sessions`, `chat_messages`, `processing_logs`, `request_logs`, `error_logs`, `indexing_jobs`, `async_jobs`.
- **`document_chunks.chroma_collection`:** Schema default comment/string may say `assistant_flow_documents`; **application indexer** passes **`assistant_flow_rag`** — treat schema default as **historical/misaligned** with runtime.
- **Migrations:** SQL files under `database/migrations/`; **needs verification** whether all environments apply them in order.

---

## 6. AI Providers

- **Text (primary orchestrator path):** GigaChat (`utils/config.py`: token/prompt URLs, model, max tokens).
- **RAG answer LLM:** `OpenAIChatProvider` in `rag_query_service` (config-driven).
- **Embeddings:** OpenAI embedding model (default `text-embedding-3-small`).
- **Image:** `image_provider` config — `proxy` vs OpenAI paths.
- **Audio:** Gated by `audio_enabled`, `stt_provider`, `tts_provider` (often `disabled`).

---

## 7. Telegram Integration

- **Library:** pyTelegramBotAPI (`telebot`).
- **Commands:** `/start`, `/help`, `/mode`, `/stats`, `/reset` (unknown slash commands rejected).
- **Modes:** `text` and `rag` in memory only; **not** synced to PostgreSQL yet (explicit TODOs in code).
- **RAG:** Initialized at startup with error capture; users can stay in RAG mode while service is down — behavior depends on message handlers (**needs verification** for every edge path).

---

## 8. RAG / Knowledge Base

- **Collection name (code):** **`assistant_flow_rag`** (`services/rag_chroma_store.py`).
- **Retrieval:** `ChromaRagStore` + LangChain documents; similarity search with timeout config; relevance filtering by **`rag_max_distance`**; diagnostics struct logged to `processing_logs`.
- **Indexing:** `AdminKnowledgeIndexer` — chunking (`RecursiveCharacterTextSplitter`, sizes from config), embeddings, upsert to Chroma, PostgreSQL version/chunk rows; full reindex can **reset** Chroma collection (HTTP) or delete local persist dir.
- **Versioning:** `document_versions.is_active` uniqueness enforced in SQL; indexer creates new versions when content hash changes (**partially observable** via admin API document detail).
- **Duplication protection:** File hash comparison in indexer; Chroma reset on full reindex — operational risk if reset misused (volume loss / full rebuild).
- **Diagnostics:** `RagRequestDiagnostics.to_log_details()` includes counts, scores, `retrieved_chunks` previews; React **RAG page** parses `execution_id` sessions from `processing_logs` (**needs verification** that all diagnostic fields always reach logs in production).

---

## 9. Admin UI

- **Stack:** React 18 + Vite + React Router (`frontend/admin-ui/src/App.tsx`).
- **Routes:** `/` Overview, `/summary`, `/text`, `/rag`, `/images`, `/audio`, `/documents`, `/logs` (`frontend/admin-ui/src/navigation/routes.ts`).
- **API client:** `frontend/admin-ui/src/api/client.ts` — `getApiBaseUrl()` uses `VITE_ADMIN_API_BASE_URL` or **`http://localhost:8600`**.
- **README vs Vite config:** `frontend/admin-ui/README.md` claims API via **Vite proxy `/api`**, but **`vite.config.ts` in repo has no `server.proxy`** — current setup likely expects direct API URL or proxy added elsewhere (**inconsistency / operational debt**).
- **Modality pages:** Consume `/api/logs/recent` with client-side filtering (Text, RAG, Images, Audio); **RAG** includes operational panels, chunk list, modal for full chunk text, collapsed pipeline + “Технический снимок сессии (JSON)” aligned with Logs naming.
- **Documents:** List/upload/reindex, detail timeline, Chroma vs Postgres chunk sum mismatch flag from API.
- **Assets:** Preview URLs built as `/api/assets/preview?asset_ref=` (images/audio).
- **Placeholder page:** Exists (`PlaceholderPage.tsx`) but **not** wired in `App.tsx`.

---

## 10. Current Workflow Status

- **Production-like compose:** Telegram + Streamlit + Chroma + volumes; **Admin API and React not first-class services** in compose (must be run manually or **needs verification** in external orchestration).
- **RAG indexing:** Supported via Admin API upload/reindex and indexer services; async reindex queue is **scaffold** (DB + worker class, no always-on worker in compose).
- **Degraded startup:** Telegram bot tolerates STT/TTS init failure and RAG init failure with logging; lifecycle may record `system_degraded`-style events when implemented in paths.

---

## 11. Known Problems

- **Admin API exposure:** No auth layer in code; relies on network isolation (**high risk** if port published).
- **Dual logging confusion:** SQLite provider logs vs PostgreSQL lifecycle vs schema `request_logs` — operators must know which UI/API reads which source.
- **Telegram mode persistence:** In-memory only; restart loses mode; PostgreSQL `chat_sessions` unused for this (**TODO** in code).
- **Vite proxy documentation drift:** README mentions `/api` proxy; `vite.config.ts` does not implement it.
- **Schema vs runtime naming:** `document_chunks` default collection name in SQL vs **`assistant_flow_rag`** in code — confusing for raw SQL readers.
- **Chroma persistence:** Volume `assistant_chroma_data` must not be deleted casually (documented in compose); historical “lost index” class of incidents possible on volume misuse (**operational**, not code bug).

---

## 12. Decisions Log

- **Chroma Docker healthcheck disabled:** Avoid false unhealthy loops when image lacks shell tools; rely on app-level checks (`docker-compose.assistant.yml`, `healthcheck_service.py`).
- **Admin API as JSON sidecar:** FastAPI added alongside Streamlit; `admin_api/app.py` description still mentions Streamlit unchanged.
- **CORS defaults include specific LAN IP** (`216.57.108.80:5173`) — environment-specific coupling.
- **Lifecycle logging best-effort:** Failures must not crash user flows; stderr as fallback observability.
- **RAG diagnostics in `processing_logs`:** Structured `details` for admin transparency; truncation in `log_row_to_entry` for API payloads.

---

## 13. Operational Rules

- **Do not remove** `./storage` mount casually — assets and uploads depend on it (compose comment).
- **Do not remove** `assistant_chroma_data` volume unless full reindex intended.
- **Chroma availability:** System designed to **boot in degraded mode** without Chroma (`assistant-chroma` service comment).
- **Admin API:** Run `python run_admin_api.py` (or uvicorn) when React admin needs backend; ensure `DATABASE_URL` for full log features.

---

## 14. Testing Checklist

- **No centralized pytest suite** in repo; ad-hoc scripts: `scripts/test_rag_regression.py`, `scripts/test_rag_embedding.py`, `scripts/test_image_providers.py`, `scripts/test_telegram_formatter.py`, `scripts/test_orchestrator_pipeline.py`.
- **Frontend:** `npm run build` in `frontend/admin-ui/` (verified in recent dev iterations).
- **Manual:** Health endpoint, overview, documents upload, reindex, Telegram text/rag/image/voice paths, Chroma down scenario.

---

## 15. Security Notes

- **Secrets:** `.env` / `.env.server` (compose); API keys for GigaChat, OpenAI, proxy; Telegram token.
- **Admin API:** No token validation; CORS wide open to configured origins.
- **Asset preview:** Path validation via `AssetRepository` / allowed prefixes — depends on implementation correctness (**needs verification** for path traversal audits).
- **Logs:** Details JSON may contain previews — treat as sensitive in aggregate.

---

## 16. Deployment Commands

- **Install deps:** `pip install -r requirements.txt` (inside image or venv).
- **Telegram bot:** `python run_telegram_bot.py` (Docker default CMD).
- **Admin API:** `python run_admin_api.py` (uvicorn `0.0.0.0:8600`).
- **Streamlit (compose):** Service `assistant-admin` on 8501.
- **React dev:** `cd frontend/admin-ui && npm install && npm run dev`.
- **Compose:** `docker compose -f docker-compose.assistant.yml up -d` (**needs verification** for env files and network names `assistant-net`, `n8n_default`).

---

## 17. Roadmap (inferred, not a product charter)

- Persist Telegram modes and history in PostgreSQL (explicit TODOs).
- Async reindex worker / background processing beyond scaffold (`async_jobs`, `AsyncReindexWorker`).
- Possible consolidation: single admin surface (React) vs Streamlit — **not decided in code**.
- Stronger Admin API auth and unified logging to PostgreSQL `request_logs` — **needs verification** / likely gaps.

---

## 18. Current Priorities

- Align **dev docs** with actual Vite/API wiring (proxy vs `VITE_ADMIN_API_BASE_URL`).
- **Secure Admin API** if exposed beyond localhost.
- **Telemetry completeness:** token accounting and provider fields in `processing_logs` for all modalities (**partially implemented** — admin UI shows gaps explicitly in RAG operational panels).
- **Operational runbooks:** Chroma volume, full reindex impact, Postgres migration order.

---

## 19. Important Paths

| Path | Purpose |
|------|---------|
| `run_telegram_bot.py` | Bot entry |
| `run_admin_api.py` | FastAPI entry |
| `admin_api/app.py` | FastAPI app factory |
| `admin_api/routes/*.py` | HTTP endpoints |
| `interfaces/telegram_bot.py` | Bot handlers, RAG init |
| `core/orchestrator.py` | Text/image orchestration |
| `services/rag_chroma_store.py` | Chroma client + collection |
| `services/rag_query_service.py` | RAG read path + diagnostics |
| `services/admin_knowledge_indexer.py` | Indexing write path |
| `services/admin_service.py` | Admin API backing service |
| `services/runtime_lifecycle_service.py` | PostgreSQL lifecycle |
| `services/healthcheck_service.py` | Dependency probes |
| `database/schema.sql` | PostgreSQL schema reference |
| `database/migrations/*.sql` | Incremental DDL |
| `docker-compose.assistant.yml` | Runtime services |
| `frontend/admin-ui/src/api/client.ts` | React API base URL |
| `frontend/admin-ui/src/pages/*.tsx` | Admin pages |
| `utils/config.py` | Environment configuration |

---

## 20. Team Workflow

- **needs verification** — no repository-local documentation of branching, review, or release process was audited for this snapshot. Use org standards outside this repo.

---

### Unresolved areas requiring manual verification

- Whether **Traefik** or another reverse proxy terminates TLS/routes in production.
- Whether **`request_logs`** (PostgreSQL) is populated by application code or only defined in schema.
- **Production process** for running **FastAPI** and **React** (systemd, separate compose, k8s, etc.).
- Full **embedding / retrieval token** accounting coverage in logs vs UI expectations.
- **Connection pooling** and Postgres HA strategy.
