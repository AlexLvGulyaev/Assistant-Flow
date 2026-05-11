# PROJECT STATE

## 1. Project Overview

Project: `assistant-flow`

Current positioning:

```text
Production-grade multimodal AI operations platform prototype
(single-tenant maturity stage)
```

Goal:
Operational-first AI platform with:
- Telegram assistant
- RAG / knowledge base
- image generation
- future voice/audio support
- PostgreSQL metadata storage
- Chroma vector storage
- operational observability
- admin operational console
- graceful degradation

Current maturity:
- Telegram assistant operational
- Production-style Admin UI operational
- Chroma retrieval operational through Docker HTTP mode
- PostgreSQL operational
- Unified operational observability layer implemented
- Graceful degradation partially implemented
- Healthcheck layer implemented
- Generated assets observability implemented

Core architectural principle:
Operational-first and production-oriented architecture instead of educational MVP shortcuts.

Main project philosophy:

```text
There are only two states:
- prom
- ne prom
```

Educational shortcuts and throwaway MVP patterns are intentionally avoided.

---

## 2. Current Architecture

Current logical architecture:

```text
Telegram Bot
    ↓
interfaces/telegram_bot.py
    ↓
core/orchestrator.py
    ↓
services/
    ├── rag_query_service.py
    ├── rag_chroma_store.py
    ├── healthcheck_service.py
    ├── admin_knowledge_indexer.py
    ├── asset_repository.py
    ├── runtime_lifecycle_service.py
    ├── GigaChatService
    ├── ImageGenerationService
    └── ...
    ↓
providers/
    ├── OpenAI embeddings
    ├── ProxyAPI chat/image
    ├── GigaChat
    ↓
ChromaDB
PostgreSQL
Filesystem asset storage
```

Key architectural decisions:
- Orchestrator is the single business entry point
- Telegram handlers remain thin
- Retrieval uses native Chroma API instead of LangChain retrieval
- Embeddings provider separated from chat provider
- Chroma supports HTTP mode through Docker network
- PostgreSQL is source of truth for metadata
- Chroma stores vectors only
- Files stored on filesystem, metadata stored in PostgreSQL
- Observability-first architecture
- Graceful degradation preferred over hard crashes
- Admin functionality separated from user Telegram bot
- Unified operational UI design system implemented inside Streamlit admin

Important architectural decision:

```text
filesystem/object storage
+
DB metadata
```

NOT PostgreSQL blob storage.

---

## 3. Infrastructure

Current state:
- German VPS server
- Docker-based infrastructure
- Existing Traefik reverse proxy
- Existing PostgreSQL container from previous HR assistant project
- Streamlit admin container
- assistant-flow bot container
- Chroma container

Current containers:
- `assistant-flow`
- `assistant-admin`
- `assistant-chroma`
- `n8n-postgres_hr-1`
- `n8n_traefik_1`
- `n8n_n8n_1`

Current topology:

```text
assistant-flow
    ↓
Docker network
    ↓
PostgreSQL + Chroma
```

without SSH tunnels.

Important infrastructure details:
- Chroma runs in Docker HTTP mode
- Chroma persistence must use Docker named volume
- assistant-flow uses graceful degraded startup when Chroma unavailable
- Streamlit admin exposed on port 8501
- Traefik handles HTTPS reverse proxying

Critical Chroma persistence configuration:

```yaml
assistant-chroma:
  image: chromadb/chroma:1.0.15
  container_name: assistant-chroma
  restart: unless-stopped
  ports:
    - "8000:8000"
  volumes:
    - assistant_chroma_data:/data
```

Important:
Removing this volume resets Chroma index.

---

## 4. Active Services

Implemented services:
- rag_query_service.py
- rag_chroma_store.py
- rag_document_loader.py
- rag_local_indexer.py
- admin_knowledge_indexer.py
- healthcheck_service.py
- runtime_lifecycle_service.py
- asset_repository.py
- asset_repository_factory.py
- GigaChatService
- ImageGenerationService

Implemented repositories:
- user_repository.py
- session_repository.py
- document_repository.py
- logs_repository.py
- runtime_lifecycle_repository.py

Operational services implemented:
- healthchecks
- runtime lifecycle logging
- generated assets persistence
- document indexing
- observability logging
- admin diagnostics

---

## 5. Database

Primary DB:
PostgreSQL on server.

Database:
`assistant_flow`

Schema:
`database/schema.sql`

Implemented DB areas:
- documents
- document_versions
- document_chunks
- indexing_jobs
- request_logs
- processing_logs
- intake_events
- error_logs
- generated_assets
- usage_metrics
- users/sessions skeletons

Important rule:
PostgreSQL is source of truth.
Application logic should not invent tables/fields outside schema.sql.

Important architectural decision:
- Chroma stores vectors only
- PostgreSQL stores metadata, observability and lifecycle data
- Assets stored on filesystem, referenced through metadata

---

## 6. AI Providers

Current provider strategy:

Embeddings:
- OpenAI direct API

Chat:
- ProxyAPI
- GigaChat

Image generation:
- ProxyAPI/OpenAI-compatible provider

Reason:
- ProxyAPI embeddings proved unstable for RAG
- Direct OpenAI embeddings work reliably

Known working embedding model:
- `text-embedding-3-small`

Important:
Providers are abstracted and separated by responsibility.

---

## 7. Telegram Integration

Implemented:
- `/start`
- `/help`
- `/mode`
- `/stats`
- `/reset`

Modes:
- text
- rag
- image generation

Polling:
- infinity_polling
- stabilized after diagnostics

Important implementation detail:
Telegram handlers must remain thin and delegate logic to orchestrator/services.

Graceful degradation implemented:
- if Chroma unavailable:
  - bot still starts
  - text mode works
  - image generation works
  - RAG returns fallback message

---

## 8. RAG / Knowledge Base

Current RAG pipeline:

```text
question
→ embedding
→ Chroma retrieval
→ context assembly
→ LLM answer
→ sources
→ diagnostics
→ observability logs
```

Implemented:
- chunk loading
- indexing
- retrieval
- source attribution
- timeout handling
- fallback handling
- retrieval diagnostics
- regression tests
- document versioning
- operational safeguards for large documents

Important architectural decision:
LangChain retrieval was abandoned in favor of native Chroma retrieval.

Current Chroma mode:
HTTP mode through server-side Chroma container.

Important operational safeguards:
- chunk estimation before upload
- NORMAL/MEDIUM/LARGE document tiers
- warnings before heavy reindex
- lazy rendering for versions
- limited JSON preview rendering
- limited disk sample reading

Known issue:
Heavy RAG queries against newly reindexed large documents may still overload small VPS resources.

Known incident pattern:

```text
new document version
→ reindex
→ RAG query against new version
→ severe slowdown
→ possible server instability
```

Current suspected causes:
- limited VPS RAM (~2 GB)
- no swap configured
- heavy retrieval diagnostics
- large retrieved chunk payloads
- synchronous RAG processing pipeline

---

## 9. Admin UI

Status:
Production-style operational admin console is now based on:

```text
FastAPI Admin API
+
React / Vite frontend
```

Important architecture correction:
Streamlit is no longer the current Admin UI foundation.

Current Admin UI stack:
- `admin_api/` — FastAPI backend/API layer
- `frontend/admin-ui/` — React frontend
- Vite dev/build tooling
- Admin API routes under `/api/...`

Implemented React pages:
- Overview
- Summary
- Text
- RAG
- Images
- Audio
- Documents
- Logs

Implemented / used Admin API endpoints include:
- `GET /api/health`
- `GET /api/overview`
- `GET /api/summary`
- `GET /api/logs/recent`
- `GET /api/assets/preview`
- `GET /api/documents`
- `GET /api/documents/{document_id}/detail`
- `POST /api/documents/upload`
- `POST /api/documents/reindex`

Admin UI philosophy:

```text
operational-first
observability-first
compact operator console
modality-oriented operational UI
```

Current UI design principles:
- dark operational console
- compact operator-oriented layout
- split-view architecture
- independent scroll areas where useful
- sticky/visible controls where needed
- grouped operational telemetry panels
- collapsible diagnostics / technical JSON
- no giant KPI brick dashboards
- no hidden observability gaps
- no duplicating Logs page inside modality pages

Important modality-card architecture:

```text
1. general operational summary
2. user input / system output
3. modality-specific operational entities
4. timeline / raw diagnostics
```

Modality primary objects:
- RAG → retrieved chunks and retrieval quality
- Images → generated image / image prompt / asset metadata
- Audio → transcript, STT/TTS, audio assets
- Text → user text and model answer
- Documents → versions, preview, chunks, lifecycle

Historical note:
The project previously had a Streamlit Admin UI. It remains a useful behavioral/reference point for some UI decisions, but it is no longer the current Admin UI architecture.

## 10. Current Workflow Status

Working:
- Telegram polling
- text mode
- RAG mode
- image generation
- voice/audio ingestion path with STT/TTS support in progress/implemented foundation
- OpenAI embeddings
- Chroma HTTP retrieval
- indexing pipeline
- source retrieval
- generated assets observability
- healthcheck layer
- graceful degradation
- FastAPI Admin API
- React Admin UI operational console
- server-side deployment

Implemented / substantially advanced in current phase:
- React/FastAPI Admin UI migration
- Overview operational dashboard
- Summary operational metrics page
- Logs operational trace viewer
- Documents operational console with upload/reindex/detail/version/chunk/timeline support
- Images operational page with asset preview
- Audio operational page with media preview
- Text operational page
- RAG operational page under active polish
- safe asset preview endpoint for image/audio
- `/api/logs/recent` with `since_hours` / offset support
- `/api/documents` and document detail/action endpoints

Partially implemented / needs follow-up:
- token economy telemetry
- normalized provider/model telemetry across modalities
- advanced RAG retrieval-quality diagnostics
- multi-version document semantics:
  - PostgreSQL historical chunks/versions
  - Chroma active versions only
- idempotent single-document reindexing without Chroma vector duplication
- production deployment mode for React UI beyond dev/Vite workflow

Not implemented / future:
- RBAC/auth
- multi-tenant isolation
- async workers / queue-based processing
- background task queue
- S3/object storage backend
- full telemetry schema migration

## 11. Known Problems

### 1. Heavy RAG instability after reindex

Observed repeatedly:

```text
new document version
→ reindex
→ RAG query against same document
→ severe slowdown
→ possible server instability
```

Potential causes:
- large retrieval diagnostics payloads
- limited VPS RAM
- no swap configured
- synchronous retrieval pipeline
- heavy Streamlit rendering
- Chroma retrieval pressure

Current mitigations:
- safeguards for large documents
- degraded mode
- healthchecks
- Chroma persistence fixes

Not fully solved yet.

---

### 2. Chroma persistence bug (fixed)

Critical incident discovered:
- Chroma container recreated without mounted volume
- collection_count reset to 0 after rebuilds

Cause:
missing:

```yaml
assistant_chroma_data:/data
```

Fix implemented:
stable Docker named volume restored.

---

### 3. Streamlit sticky/autoscroll limitations

Attempted:
- sticky headers
- JS autoscroll
- independent scroll panes

Result:
- unstable behavior
- overlay glitches
- Streamlit sandbox limitations

Decision:
Do NOT use these patterns.

---

### 4. Retrieval quality limitations

Current behavior:
Model may still produce weak relevance selection for glossary-like documents.

Cause:
- simplistic chunking
- basic ranking strategy
- no semantic chunking yet

Future work:
P5.5 Retrieval Quality Engineering.

---

## 12. Decisions Log

### Decision: PostgreSQL is source of truth
Chroma stores vectors only.

### Decision: Retrieval uses native Chroma API
LangChain retrieval removed from main path.

### Decision: Embeddings and chat providers separated
- embeddings → OpenAI
- chat → ProxyAPI/GigaChat

### Decision: Chroma moved to Docker HTTP mode
Due to Windows native crashes and operational stability.

### Decision: Admin functionality separated from user bot
Telegram bot should not become knowledge-base admin interface.

### Decision: Admin UI moved to FastAPI + React
Streamlit is no longer the current Admin UI foundation.
The current admin architecture is:
- FastAPI Admin API
- React/Vite frontend

### Decision: Operational-first architecture
Production-like structure preferred over educational shortcuts.

### Decision: Graceful degradation preferred over crash-loop
If Chroma unavailable:
- assistant-flow still starts
- text/image remain operational
- RAG returns fallback

### Decision: Filesystem storage instead of PostgreSQL blobs
Assets stored on filesystem.
Metadata stored in PostgreSQL.

### Decision: AssetRepository abstraction introduced
Filesystem storage is wrapped through repository abstraction so future filesystem → S3 migration does not require rewriting business logic.

### Decision: Unified operational design system
All admin pages should use unified operational UI primitives and modality-card architecture.

### Decision: Missing telemetry must be visible
Important telemetry fields must not silently disappear from UI.
If token/model/retrieval telemetry is missing, UI should show that it is not collected / missing in logs.

### Decision: RAG page is retrieval console, not duplicated Logs page
RAG UI must prioritize:
- retrieved chunks
- retrieval quality
- full chunk inspection
- answer grounding

Generic pipeline trace belongs primarily to Logs.

### Decision: Git commits mandatory after stable logical steps
Implemented after Cursor/provider instability incidents.

## 13. Operational Rules

Core principles:
- architecture-first
- operational-first
- observability-first
- production-oriented solutions
- no educational shortcuts

Technical rules:
- Thin Telegram handlers
- Business logic in services/orchestrator
- Do not invent DB schema outside schema.sql
- Prefer explicit logging
- Retrieval and LLM calls must have fallback behavior
- One Chroma backend for indexing and retrieval
- Avoid giant payload rendering in Streamlit
- Use graceful degradation instead of crash loops

UI rules:
- unified operational design system
- compact operational cards
- split-layout architecture
- muted metadata
- no sticky/fixed hacks
- no flashy dashboard UI

Git workflow:
- check git status before Cursor work
- commit after stable logical step
- rollback through git when needed

Docker workflow:

```bash
COMPOSE_BAKE=false docker compose -f docker-compose.assistant.yml up -d --build
```

Important:
Do NOT use `docker compose down -v` unless full Chroma reset intended.

---

## 14. Testing Checklist

Verified:
- OpenAI embeddings smoke test
- Chroma HTTP add/count
- Telegram polling
- RAG retrieval
- admin indexing
- source retrieval
- generated assets observability
- degraded startup
- Chroma reconnect behavior
- admin healthchecks

Useful commands:

```bash
python scripts/test_rag_embedding.py
python scripts/admin_index_documents.py --reindex
python scripts/test_rag_regression.py
python run_telegram_bot.py
```

Operational diagnostics:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs --tail=120 assistant-flow
docker logs --tail=120 assistant-chroma
free -h
docker stats --no-stream
```

---

## 15. Security Notes

Current state:
- Chroma exposed only inside server environment
- PostgreSQL exposed through Docker network / localhost
- HTTPS handled through Traefik
- Admin UI isolated from user Telegram bot

Planned:
- RBAC/auth
- API tokens
- multi-user isolation
- quotas
- object storage abstraction

---

## 16. Deployment Commands

Current rebuild:

```bash
COMPOSE_BAKE=false docker compose -f docker-compose.assistant.yml up -d --build
```

Run diagnostics:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Check Chroma persistence:

```bash
docker inspect assistant-chroma --format '{{json .Mounts}}'
```

Check collection count:

```bash
docker exec -it assistant-flow python - <<'PY'
from utils.config import load_config
from services.rag_chroma_store import ChromaRagStore

config = load_config()
store = ChromaRagStore(
    chroma_host=config.chroma_host,
    chroma_port=config.chroma_port,
    collection_name=config.chroma_collection_name,
)
print("collection_count =", store.collection_count())
PY
```

RAG indexing:

```bash
python scripts/admin_index_documents.py --reindex
```

Run bot:

```bash
python run_telegram_bot.py
```

---

## 17. Roadmap

### P5.1 — Healthchecks / graceful degradation / operational stability
Status:
Mostly implemented / near closed.

Implemented:
- PostgreSQL healthcheck
- Chroma healthcheck
- degraded mode
- restart-loop protection
- startup dependency handling
- Overview health section

Remaining:
- verify Chroma persistence stability after rebuild/redeploy cycles

### P5.2 — Storage abstraction
Status:
Partially implemented / substantially advanced.

Implemented:
- AssetRepository abstraction
- AssetRepositoryFactory
- FilesystemAssetRepository
- asset references for generated assets
- image/audio asset preview support in Admin API/UI

Purpose:
filesystem → S3 migration readiness without rewriting business logic.

### P5.3 — Async processing
Status:
Not implemented as full platform architecture.

Planned:
- queues
- workers
- background indexing
- async generation
- async document processing
- operational job tracking

Note:
The project already uses operational/job-oriented thinking, but Assistant Flow remains mostly synchronous.

### P5.4 — Voice / Audio pipeline
Status:
Foundation and UI substantially advanced.

Implemented / advanced:
- audio UI tab/page
- STT/TTS provider foundations
- OpenAI STT/TTS provider routing in prior phase
- audio asset storage through AssetRepository
- audio operational observability
- safe audio preview via Admin API

Remaining:
- final runtime hardening
- telemetry normalization
- cost/token/character accounting
- production-quality audio workflow polish

### P5.5 — Retrieval Quality Engineering
Status:
Entered earlier than originally planned.

Current work areas:
- RAG operational UI
- full chunk inspection
- retrieval metrics visibility
- relevance/fallback diagnostics
- chunk quality observability
- future semantic/glossary-aware chunking

Future:
- semantic chunking
- glossary-aware chunking
- noisy chunk diagnostics
- retrieval quality metrics
- query/retrieval evaluation dashboard

### P6 — Admin UI / operational console maturity
Status:
React/FastAPI migration implemented and actively polished.

Current work:
- modality-card consistency
- RAG page refinement
- Documents/RAG quality for Module 5 and portfolio
- telemetry/economy visibility

### P7 — Security / RBAC / Multi-user

### P8 — Deployment maturity
- production serving for React build
- CI/CD
- monitoring
- automated backups
- infrastructure hardening

## 18. Current Priorities

1. Finish RAG operational UI polish
2. Preserve full chunk inspection in RAG
3. Complete telemetry/economy audit:
   - input tokens
   - output tokens
   - total tokens
   - embedding tokens
   - provider/model normalization
4. Resolve/plan multi-version document architecture:
   - PostgreSQL historical versions/chunks
   - Chroma active retrieval versions only
5. Verify idempotent single-document reindexing without vector duplication
6. Stabilize heavy RAG workloads
7. Verify Chroma persistence after rebuild/redeploy
8. Move React Admin UI toward production deployment mode
9. Add async/background processing layer
10. Add RBAC/auth

## 19. Important Paths

```text
database/schema.sql
services/rag_query_service.py
services/rag_chroma_store.py
services/healthcheck_service.py
services/runtime_lifecycle_service.py
services/asset_repository.py
interfaces/telegram_bot.py
core/orchestrator.py
admin_ui/app.py
scripts/admin_index_documents.py
scripts/test_rag_regression.py
docker-compose.assistant.yml
```

---

## 20. Team Workflow

Team roles:

Alexander:
- product owner
- operator
- tester
- final decision maker

ChatGPT / Optimus:
- architect
- systems analyst
- reviewer
- debugging support
- prompt engineer

Cursor:
- coding agent
- implementation executor
- refactoring executor

Workflow principles:
- architecture-first
- operational-first
- production-oriented solutions
- explicit diagnostics/logging
- avoid MVP hacks
- changes incremental and testable
- commit after stable step

Important workflow:

```text
Alexander describes problem / shows logs or screenshots
→ Optimus analyzes
→ writes structured Cursor prompt
→ Cursor changes code
→ Alexander tests
→ Optimus reviews result
→ commit / patch / rollback decision
```

Git rules:
- git status before Cursor work
- commit after successful stable step
- rollback through git if needed

Important lesson learned:
After Cursor provider instability incident, Git became mandatory safety mechanism.



---

## ADDITIONAL CONTEXT FROM LATEST UI / RAG ITERATIONS

### Admin UI operational redesign (latest iteration)

Current Admin UI evolution moved away from generic dashboard layout toward:

```text
modality-oriented operational console
```

Key architectural UI principle established during latest iterations:

Every modality card should follow unified structure:

```text
1. General operational summary
2. User input / system output
3. Modality-specific operational entities
4. Timeline / raw diagnostics
```

Examples:
- RAG → chunks
- Images → generated image
- Audio → transcript + audio assets
- Text → text response
- Documents → versions/chunks/lifecycle

Important UI architectural decision:
General operational summary and modality-specific telemetry must be visually separated.

General operational summary:
- execution_id
- provider/model
- start time
- duration
- token economy
- latency

Modality-specific telemetry:
- retrieval metrics
- chunk quality
- audio metadata
- image metadata
- etc.

Critical UI lesson learned:
Do NOT duplicate generic Logs-page information inside modality pages.

RAG page specifically should NOT become:
- duplicated execution logs viewer
- duplicated generic trace page

RAG page purpose:
```text
retrieval diagnostics and chunk analysis
```

Therefore:
- chunk visibility is primary
- retrieval quality is primary
- full chunk text access is mandatory
- timeline is secondary/collapsible

### Unified modality-card operational design system

Latest operational UI rules:

- all modality pages must use unified modality-card layout
- execution_id always visible in top section
- status badge in card header
- compact operational telemetry blocks
- modality-specific telemetry grouped into operational panels
- no oversized metric dashboards
- no giant KPI tiles
- compact operator-oriented diagnostics

Important UI rejection:
Individual metric brick/tile layout was rejected as visually noisy and space-inefficient.

Preferred:
compact grouped operational panels.

### RAG UI operational decisions

Accepted RAG operational structure:

```text
HEADER
→ summary + status

TOP PANELS
→ session parameters
→ retrieval metrics
→ quality metrics

QUESTION / ANSWER

FOUND CHUNKS
(primary content)

TIMELINE
(collapsible)

TECHNICAL SESSION SNAPSHOT (JSON)
(collapsible)
```

Important:
Chunks are primary operational object in RAG mode.

Mandatory chunk functionality:
- chunk preview
- full chunk text access
- chunk score/distance
- relevance label
- filename
- chunk index

Important UX rule:
Operator must always be able to inspect FULL chunk text.

Single-line preview or hidden full text is unacceptable.

Preferred implementation:
modal/fullscreen scrollable chunk viewer.

### Telemetry / token economy decision

Major architectural decision introduced:

Token economy observability becomes mandatory platform concern.

Required telemetry targets:
- input tokens
- output tokens
- total tokens
- embedding tokens
- provider/model
- latency

Critical observability rule:
Missing telemetry fields must remain visible in UI as:

```text
not collected
missing in logs
no data
```

and NOT disappear silently.

Reason:
Operational UI must expose observability gaps.

### Retrieval diagnostics telemetry review planned

Planned backend review areas:
- orchestrator payloads
- runtime lifecycle logging
- request_logs
- processing_logs
- retrieval diagnostics schema
- token accounting propagation
- embedding telemetry propagation

Expected future work:
schema migrations may be required for token accounting and provider telemetry normalization.

### Streamlit → React migration pressure

Latest UI iterations revealed significant pressure toward moving beyond Streamlit limitations.

Observed pain points:
- nested scrolling
- sticky layout instability
- modal limitations
- dynamic height handling
- operational split layouts
- heavy rendering behavior

No migration decision finalized yet.

Current state:
Admin UI has migrated to FastAPI + React. Streamlit remains only as historical/reference context where old screens are compared.

### Multi-version document architecture

Decision intentionally postponed for separate design phase.

Future architectural target:

```text
PostgreSQL:
- versions
- chunks
- historical metadata

Chroma:
- active retrieval versions only
```

Important future challenge areas:
- historical chunk preview
- archived version rendering
- active/inactive retrieval versions
- idempotent reindexing
- avoiding vector duplication
- operational visualization of version lineage

Marked as future dedicated architecture phase.

---

## 1.1 Русская narrative-версия (append-only)

Этот state-файл фиксирует текущее инженерное состояние `assistant-flow` как operational-first прототипа. Пользовательский контур построен вокруг Telegram, а отдельный operational contour реализован через Admin API / Admin UI с акцентом на observability, execution tracing и degraded mode.

Ключевая архитектурная идея: retrieval и knowledge lifecycle разделены по ответственности. ChromaDB используется как retrieval/vector слой, PostgreSQL — как контракт metadata/lifecycle/telemetry. Runtime, indexing и monitoring разделены, чтобы pipeline поведение можно было диагностировать отдельно от пользовательского UX.

Документ отражает практический статус компонентов, известные ограничения, принятые engineering decisions и operational roadmap без маркетинговых формулировок.

## 3.1 Portfolio deployment environment

В проекте появился отдельный portfolio deployment contour:

- docker-compose.portfolio.yml
- isolated PostgreSQL
- isolated ChromaDB
- isolated Admin API/UI
- clone-and-up oriented deployment
- GitHub portfolio reproducibility

Portfolio environment стал основной dev/demo средой проекта.

## 6.1 Provider routing maturity

Provider routing стал modality-specific:

- embeddings → OpenAI direct
- text → GigaChat / ProxyAPI
- image → ProxyAPI/OpenAI-compatible
- STT/TTS → OpenAI

Причина:
разные providers показали различную reliability/economics profile в разных modality pipelines.

## 9.1 Current Admin UI maturity

Admin UI достиг operational portfolio-grade maturity:

Реализованы:

- Overview operational dashboard
- modality-specific operational pages
- execution tracing
- chunk inspection
- image preview
- audio preview
- timeline diagnostics
- collapsible technical JSON snapshots
- retrieval quality visibility

Admin UI теперь является полноценным operational contour отдельно от Telegram UX.

## 10.1 Fully verified modality walkthrough

В рамках portfolio verification были полностью протестированы:

- text mode
- RAG mode
- image generation
- STT/TTS audio pipeline
- Admin UI observability
- generated assets lifecycle
- retrieval diagnostics
- document indexing lifecycle

Были созданы synchronized Telegram/Admin UI walkthrough screenshots для всех modality scenarios.

## 13.1 GitHub-first workflow

После подготовки portfolio repository workflow проекта стал GitHub-first:

- все стабильные этапы коммитятся;
- README/documentation поддерживаются как часть engineering process;
- deployment reproducibility проверяется через clean compose startup;
- runtime artifacts не должны попадать в git.

## 18.1 Current strategic direction

Текущий стратегический вектор проекта:

- controlled knowledge base lifecycle
- AI-pipeline observability
- modality-oriented operational console
- retrieval quality engineering
- async architecture preparation
- provider economics visibility
- production-oriented deployment maturity

## 21. Historical Incidents / Postmortems

### 21.1 ProxyAPI image generation budget exhaustion

Во время интенсивной отладки image generation pipeline был полностью исчерпан лимит ProxyAPI (~2000 RUB), что привело к ложным симптомам деградации image pipeline.

Симптомы:

- image generation перестал работать;
- text/RAG/audio продолжали работать;
- provider healthchecks оставались partially healthy;
- UI показывал image failures.

Фактическая причина:
исчерпание баланса ProxyAPI.

Инженерный вывод:
observability provider economics так же важна, как observability инфраструктуры.

Дополнительный вывод:

- token/image economics должны быть видимы;
- provider quotas и usage telemetry должны стать частью observability layer.

### 21.2 Portfolio compose environment mismatch

Portfolio deployment initially failed because docker-compose.portfolio.yml использовал неправильный env-файл.

Симптомы:

- Telegram bot внутри контейнера видел placeholder token;
- container startup переходил в demo mode;
- TELEGRAM_BOT_TOKEN в host env был корректным;
- внутри container env token отсутствовал.

Причина:
docker compose ссылался на неправильный env file.

Исправление:
корректный env-file wiring.

Инженерный вывод:
deployment reproducibility зависит от explicit env isolation.

### 21.3 React Admin UI "Failed to fetch" incident

После React/FastAPI migration frontend intermittently показывал "Failed to fetch", несмотря на working backend API.

Симптомы:

- /api/health отвечал корректно;
- tunnel logs были пустыми;
- browser UI показывал fetch failure;
- backend operational.

Причина:
frontend build содержал hardcoded localhost API target.

Исправление:
пересборка frontend build после исправления API target.

Инженерный вывод:
React/Vite build artifacts могут содержать stale deployment configuration.

### 21.4 Chroma duplication after reindex/redeploy

После rebuild/redeploy и повторной переиндексации документы появились в новой PostgreSQL instance как новые version records.

Симптомы:

- duplicated document entries;
- повторная initial indexing semantics;
- Chroma links logically persisted.

Причина:
PostgreSQL metadata lifecycle и Chroma retrieval lifecycle были partially decoupled.

Инженерный вывод:
multi-version lifecycle architecture требует отдельного explicit design phase.

### 21.5 Streamlit operational UI scalability limitations

Поздние итерации Streamlit Admin UI выявили structural limitations operational-console architecture.

Симптомы:

- nested scroll instability;
- sticky layout glitches;
- weak split-layout support;
- poor modality-oriented UX scaling.

Решение:
миграция на FastAPI + React/Vite.

Инженерный вывод:
Streamlit хорошо подходит для fast MVP/admin prototypes, но плохо масштабируется в modality-oriented operational console.

## 22. Legacy Lesson Integration Strategy

В рамках Module 5 проект продолжает развиваться параллельно с учебными RAG-уроками.

Принято отдельное инженерное решение:

```text
lesson code != production integration
```

Учебные материалы не внедряются напрямую в основной runtime contour проекта.

Вместо этого используется controlled integration workflow.

### Основной подход

Для каждого урока создается отдельный каталог:

```text
/legacy/lesson-XX/
```

Туда помещаются:

- код преподавателя;
- lesson reference implementations;
- demo pipelines;
- вспомогательные материалы урока;
- экспериментальные RAG-примеры.

После этого Cursor выполняет comparative architectural review:

```text
lesson functionality
vs
current assistant-flow architecture
```

Цель:
не копирование lesson-кода,
а выявление:

- отсутствующей функциональности;
- архитектурных gap;
- полезных capability extensions;
- operational improvements;
- observability improvements;
- retrieval-quality improvements;
- multimodal enhancements.

### Planned lesson-driven capability areas

Ожидаемые направления развития в рамках Module 5:

- FAISS support as additional retrieval backend;
- multimodal document ingestion;
- PDF parsing;
- OCR/scanned document ingestion;
- retrieval quality engineering;
- semantic chunking;
- conversational memory;
- short-term Telegram session context;
- improved indexing pipelines;
- metadata-aware retrieval;
- async/background indexing;
- retrieval evaluation tooling.

### Critical architectural rule

Новая функциональность должна:

- адаптироваться под существующую architecture-first структуру;
- интегрироваться через services/providers/repositories;
- сохранять observability;
- сохранять operational diagnostics;
- поддерживать graceful degradation;
- не ломать Admin UI operational model;
- не превращать проект в набор lesson-MVP fragments.

### Integration philosophy

Lesson materials рассматриваются как:

```text
reference capability source
```

а не как production-ready implementation.

Каждая новая возможность проходит:

```text
analysis
→ architectural adaptation
→ controlled implementation
→ observability integration
→ regression verification
```

перед интеграцией в основной проект.

## 23. P6 — Retrieval Foundation Layer (подготовка этапа)

Статус на момент фиксации: **архитектурная подготовка и планирование**. Production-код AF не изменялся в рамках этого блока.

### 23.1 Позиционирование этапа

Проект AF далее рассматривается как **operational-first** платформа с упором на **production-oriented retrieval**, а не как учебный Telegram-бот с прикладным RAG. Этап **P6** объявляется **Foundation Retrieval Layer**: фундамент для abstraction retrieval, сменяемых vector backends, conversational memory, hybrid retrieval, evaluation, caching и security groundwork.

### 23.2 Разделение статусов (явно)

**Уже реализовано в AF (база для P6, не часть P6 как новой разработки):**

- основной RAG-контур на **ChromaDB** (`services/rag_chroma_store.py`, `services/rag_query_service.py`);
- индексация и метаданные в **PostgreSQL** при включённом `DATABASE_URL`;
- operational UI и диагностика retrieval в **Admin UI** / **Admin API**;
- health/degraded для зависимостей;
- таблицы `chat_sessions`, `chat_messages` в схеме (полная сквозная интеграция memory — **не** завершена).

**Запланировано в рамках P6 (ещё не реализовано):**

- каталог `services/retrieval/` с abstraction layer и фабрикой backend;
- вторичный backend **FAISS** (demo/course), переключение через `RAG_BACKEND`;
- document-aware / smart chunking как отдельный слой;
- persistent **conversational memory** (не «последние 10 сообщений»), отдельный retrieval namespace для диалога;
- **hybrid retrieval** (KB + memory), merge контекста перед LLM;
- слой **RAGAS-compatible** evaluation (скрипты + задел под admin diagnostics);
- retrieval-oriented **cache** (query / retrieval / response);
- **security groundwork** для retrieval (namespaces, source filtering, hooks; **не** полноценный RBAC).

**Exploratory (требуют отдельного решения после прототипа):**

- semantic chunking на уровне embeddings-кластеризации;
- Redis как backend кеша вместо SQLite;
- полноценный automated quality monitoring в production.

### 23.3 Подэтапы P6 (целевая декомпозиция)

| ID | Название | Суть |
|----|----------|------|
| P6.1 | Retrieval Abstraction Layer | Единый интерфейс: `add_chunks`, `search`, `reset`, `collection_count`, `healthcheck`; **Chroma** остаётся основным production backend; **FAISS** — secondary; env `RAG_BACKEND`, `FAISS_INDEX_DIR`. |
| P6.2 | Smart Chunking | Paragraph/sentence-aware split, overlap, metadata preservation; цель — precision и меньше noisy context. |
| P6.3 | Conversational Memory Layer | PostgreSQL как хранилище истории; извлечение meaningful memory; embedding записей памяти; отдельный retrieval namespace/index для диалога (использование/расширение `chat_sessions` / `chat_messages`). |
| P6.4 | Hybrid Retrieval | Совместное извлечение KB chunks + memory chunks, merge, затем LLM. |
| P6.5 | RAG Evaluation Layer | Задел под **RAGAS**: faithfulness, answer relevancy, context precision, retrieval diagnostics; internal testing и admin. |
| P6.6 | Retrieval Optimization & Cache | Уровни query / retrieval / response cache; старт с SQLite или in-memory, **Redis** позже. |
| P6.7 | Security Groundwork | Namespaces, source filtering, role-aware retrieval (концепты), masking hooks; без полноценного RBAC. |

### 23.4 Связь с уроками модуля 5 (ожидаемое покрытие)

P6 должен **поддерживать закрытие** курсовых тем не отдельными лабами, а развитием AF:

- урок 1 — FAISS retrieval (через P6.1 + secondary backend);
- уроки 2–3 — chunking / smart chunking (P6.2);
- урок 4 — memory/context (P6.3);
- урок 5 — задел под multimodal RAG (через ingestion/chunking pipeline, без обещания полной реализации в одном релизе);
- урок 6 — RAGAS evaluation (P6.5);
- урок 7 — cache/optimization (P6.6);
- уроки 8–9 — production-grade ассистент и security groundwork (сквозно P6 + существующая архитектура).

### 23.5 Политика legacy (напоминание)

Каталоги `legacy/PEr0X_source/` (фактически `PEr01` … `PEr08`, см. раздел 24) **не** являются production code. Использование: reference, donor algorithms, controlled comparative review. Правила AF сохраняются: **PostgreSQL** — source of truth для метаданных, retrieval через abstraction после P6.1, operational-first.

---

## 24. Инвентаризация legacy (`legacy/PEr0X_source/`)

В репозитории используются имена каталогов **`legacy/PEr01_source/` … `legacy/PEr08_source/`** (курс PE, не `Per0X`). Ниже — привязка к целям P6.

### 24.1 `legacy/PEr01_source/` — FAISS + retriever pipeline

| Путь | Что полезно для P6 | Сложность адаптации | Риски |
|------|-------------------|---------------------|-------|
| `legacy/PEr01_source/bot_proxy/rag/vectorstore.py` | Реализация **FAISS** `IndexFlatL2`, add/search, save/load (`faiss.write_index` / `read_index`), метаданные рядом с индексом — образец для `faiss_backend`. | Средняя: переписать под интерфейс P6.1, убрать привязку к старому `config`, единый embedding dimension. | Расхождение размерности embeddings; нет интеграции с текущим lifecycle PostgreSQL; дублирование логики с Chroma. |
| `legacy/PEr01_source/bot_proxy/rag/retriever.py` | Слой «embedder + vectorstore.search» — идея **retrieval pipeline** до orchestrator. | Низкая–средняя как reference. | Смешение с ProxyAPI embedder курса; не копировать в AF без изоляции. |
| `legacy/PEr01_source/bot_proxy/rag/pipeline.py` | Склейка pipeline end-to-end. | Низкая как чеклист шагов. | Отличается от `RagQueryService` в AF. |

### 24.2 `legacy/PEr02_source/`

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr02_source/test_relevance_only.py` | Упоминание FAISS как опции; идеи relevance-only тестов. | Низкая. | Вспомогательный скрипт, не архитектура. |

### 24.3 `legacy/PEr03_source/` — chunking, ingest, Chroma client

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr03_source/loader/chunker.py` | `chunk_text`, `chunk_text_smart`, `create_chunks_with_metadata` — база для **P6.2** (paragraph-aware, overlap, metadata dict). | Средняя: портировать идеи в сервис с тестами и контрактом AF. | Символьные пороги vs token-based; нет связи с `document_versions` AF. |
| `legacy/PEr03_source/ingest.py` | Поток: файлы → chunks → ids/metadatas — reference для indexing pipeline. | Средняя. | Связан со старым Chroma API и структурой проекта урока. |
| `legacy/PEr03_source/chroma/chroma_client.py` | Тонкая обёртка над Chroma — для сравнения с `ChromaRagStore`. | Низкая. | Дублирование с production AF. |
| `legacy/PEr03_source/loader/*.py` | Загрузчики txt/html — задел под preprocessing (P6.2 / multimodal ingestion позже). | Средняя. | Нет PDF/OCR в этом модуле. |

### 24.4 `legacy/PEr04_source/` — memory, dialog, context retrieval

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr04_source/memory_manager/context_retriever.py` | Паттерн **ContextRetriever** с `filter_metadata` — для P6.3/P6.4 и security groundwork. | Средняя: абстракция, не перенос класса 1:1. | Зависимость от `storage.VectorDatabase` урока, не от AF. |
| `legacy/PEr04_source/memory_manager/prompt_builder.py` | Сборка промпта из контекста — идеи для orchestrator side. | Низкая. | Не смешивать с текущим `PromptOrchestrator` без ревью. |
| `legacy/PEr04_source/dialog_controller/session_manager.py`, `user_context.py` | Модель сессии/пользователя — reference для **conversational memory** схемы. | Средняя. | Не дублировать уже существующие таблицы AF — только сопоставление. |
| `legacy/PEr04_source/tools/ingest_documents.py` | Batch ingest — для планирования indexing jobs. | Низкая. | Устаревший layout. |

### 24.5 `legacy/PEr05_source/` — Pinecone workflows

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr05_source/upload_files_to_pinecone.py`, `workflow*.json` | Идея внешнего vector SaaS и JSON workflow — для сравнения с «self-hosted Chroma/FAISS». | Низкая как reference. | **Не** целевой backend для P6; не тащить Pinecone в AF без отдельного решения. |

### 24.6 `legacy/PEr06_source/` — RAG assistant + RAGAS

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr06_source/evaluate_rag.py` | Вызов **ragas.evaluate**, метрики faithfulness, answer_relevancy, context_precision, сбор Dataset — шаблон для **P6.5**. | Средняя: адаптировать к `RagQueryService` и датасетам AF. | Зависимость от `rag_assistant` и LangChain embeddings курса; версии RAGAS могут отличаться. |
| `legacy/PEr06_source/rag_assistant.py` | End-to-end ask + context — для тестовых harness. | Средняя. | Не production. |

### 24.7 `legacy/PEr07_source/` — embeddings + response cache

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr07_source/embeddings.py` | Обёртка embeddings — для сравнения с `providers/rag_embeddings.py`. | Низкая. | Дублирование. |
| `legacy/PEr07_source/cache.py` | **ResponseCache**: хеш запроса, JSON-файл — прототип для **P6.6** (простейший уровень). | Низкая–средняя. | Нет TTL/инвалидации при смене индекса; нужна политика инвалидации в AF. |

### 24.8 `legacy/PEr08_source/` — Chroma vector_store, RAG pipeline, SQLite cache, RAGAS

| Путь | Что полезно | Сложность | Риски |
|------|-------------|-----------|-------|
| `legacy/PEr08_source/assistant_api/vector_store.py` | Chroma + chunking в одном модуле — сравнить с AF indexer + `ChromaRagStore`. | Низкая как audit. | Дублирование логики chunking с PEr03/AF. |
| `legacy/PEr08_source/assistant_api/rag_pipeline.py` | Склейка query → context → answer — для тестового harness P6.5. | Средняя. | Отдельное приложение. |
| `legacy/PEr08_source/assistant_api/cache.py` | **RAGCache** на **SQLite**: query_hash, answer, context — близко к целевому **retrieval/response cache** P6.6. | Средняя: вынести идеи схемы таблицы и ключей. | Согласовать с multi-tenant / security позже; сейчас single-tenant. |
| `legacy/PEr08_source/assistant_api/evaluate_ragas.py` | Более полный **RAGAS** pipeline (Dataset, метрики, совместимость 0.4.x) — основной donor для P6.5. | Средняя–высокая: зависимости и версии. | Привязка к локальному `RAGPipeline`; ground_truth часто пустой — для production нужна политика датасетов. |
| `legacy/PEr08_source/assistant_giga/*` | Дубли аналогичных модулей под GigaChat — второй reference. | Низкая. | Дублирование PEr08. |

### 24.9 Вывод инвентаризации

Максимальный reuse для ускорения P6: **PEr01** (FAISS), **PEr03** (chunking), **PEr06**/**PEr08** (RAGAS + кеш SQLite), **PEr04** (memory/context patterns), **PEr07** (простой response cache). **PEr05** — скорее контрпример (облачный Pinecone). Всё переносится только через **analysis → adaptation → observability → regression**, без копипаста монолитов.

---

## 25. P6 — поэтапный план реализации (draft)

Ниже — **план работ**, а не выполненные коммиты. Порядок выбран так, чтобы минимизировать регрессии и не ломать текущие workflows до появления abstraction.

### Фаза 0 — Контракты и границы (design-only)

- Зафиксировать интерфейс retrieval backend (методы как в P6.1, имена классов/модулей — отдельным решением).
- Описать mapping: текущий `ChromaRagStore` ↔ будущий `chroma_backend` adapter (**без** удаления старого кода на этой фазе).
- Согласовать env: `RAG_BACKEND`, `FAISS_INDEX_DIR` (и совместимость с существующими `CHROMA_*`).
- **Зависимости:** нет.
- **Риски:** переименование env ломает deploy — документировать migration в OPERATIONS.
- **Тесты:** регрессия текущих smoke-сценариев RAG.
- **Сложность:** низкая (документация + ADR в PROJECT_STATE).

### Фаза 1 — P6.1 Retrieval Abstraction (Chroma-first)

- Ввести `services/retrieval/` с протоколом/ABC и реализацией-адаптером поверх существующего Chroma-кода (**тонкая обёртка**, поведение идентично текущему).
- Подключить фабрику `retrieval_factory` по `RAG_BACKEND=chroma` (default).
- **Зависимости:** фаза 0.
- **Reuse:** сравнение с `PEr03` chroma client и `PEr08` vector_store — только идеи границ методов.
- **Риски:** регресс latency; двойной слой абстракции — профилировать.
- **Тесты:** unit на adapter + интеграционный RAG smoke против compose Chroma.
- **Операционность:** healthcheck в adapter; метрики в `processing_logs` без изменения семантики.
- **Сложность:** средняя.

### Фаза 2 — P6.1b Secondary FAISS backend (demo)

- Реализовать `faiss_backend.py` с опорой на паттерны **PEr01** `FAISSVectorStore`.
- Индекс только для demo/course dataset; **не** подменять production Chroma без явного флага.
- **Зависимости:** фаза 1.
- **Риски:** рассинхрон размерности embeddings; отсутствие metadata parity с PostgreSQL.
- **Тесты:** отдельный минимальный датасет; не смешивать с production `assistant_flow_rag` без миграции.
- **Сложность:** средняя–высокая.

### Фаза 3 — P6.2 Smart Chunking

- Вынести chunking в модуль/сервис с конфигом (размер, overlap, paragraph/sentence rules).
- Подключить к `AdminKnowledgeIndexer` и путям upload без изменения внешнего контракта API (по возможности).
- **Reuse:** логика из **PEr03** `chunker.py` + идеи из **PEr08** `_chunk_text`.
- **Зависимости:** желательно после фазы 1 (единая точка add_chunks).
- **Риски:** изменение chunk count → переиндексация; вспом flashback к heavy RAG — сохранить safeguards.
- **Тесты:** golden tests на фикстурах текста; сравнение chunk boundaries.
- **Сложность:** средняя.

### Фаза 4 — P6.3 Conversational Memory (persistent)

- Проектирование: схема хранения «memory records» (использование/расширение `chat_messages`, отдельная таблица memory chunks при необходимости — **решение на design review**).
- Сервис **Conversation Memory Service**: запись после ответа, извлечение candidates для retrieval.
- Embedding memory records в отдельный namespace/index (логически отдельная коллекция Chroma или префиксы document_id).
- **Reuse:** паттерны **PEr04** context_retriever / session_manager.
- **Зависимости:** фазы 1–3 желательны для единообразного chunking embeddings.
- **Риски:** privacy, рост объёма БД, дублирование с session store в памяти Telegram — явная политика источника истины.
- **Сложность:** высокая.

### Фаза 5 — P6.4 Hybrid Retrieval

- Реализовать merge policy: KB chunks + memory chunks (scores, dedup, max tokens budget).
- Интеграция в `RagQueryService` или отдельный `HybridRetrievalService` за фичефлагом.
- **Зависимости:** фазы 3–4.
- **Риски:** раздувание контекста; latency — нужен budget и observability в Admin UI.
- **Тесты:** сценарии с/без memory; регрессия чистого KB-RAG.
- **Сложность:** высокая.

### Фаза 6 — P6.5 RAG Evaluation Layer

- Вынести evaluation в `scripts/` или `tools/` + опционально endpoint только для admin/internal (не публичный internet).
- Адаптировать **PEr06** / **PEr08** `evaluate_ragas` к вызову AF pipeline и фикстурам ground truth (где применимо).
- **Зависимости:** стабильный retrieval output schema (фазы 1–5).
- **Риски:** стоимость LLM вызовов для метрик; версии ragas.
- **Сложность:** средняя.

### Фаза 7 — P6.6 Cache

- Уровень 1: query hash → retrieval result (SQLite как в **PEr08** `RAGCache`).
- Уровень 2: optional response cache с TTL и инвалидацией при reindex.
- **Зависимости:** фаза 1 минимум; лучше после 3 (инвалидация при смене chunk set).
- **Риски:** stale answers после обновления корпуса — обязательная инвалидация по `document_version` / collection generation id.
- **Сложность:** средняя.

### Фаза 8 — P6.7 Security Groundwork

- Ввести концепции namespace / source filters в retrieval query (пока без RBAC: флаги и hooks).
- Документировать threat model для Admin API.
- **Зависимости:** фазы 1 и 4 (границы данных).
- **Риски:** преждевременная сложность — держать за feature flags.
- **Сложность:** средняя (концепты + ограниченный код).

### Сводка зависимостей (migration order)

`0 (контракты) → 1 (abstraction+Chroma) → 2 (FAISS optional) → 3 (chunking) → 4 (memory) → 5 (hybrid) → 6 (eval) → 7 (cache) → 8 (security groundwork)`.

### Ожидаемые точки касания кода (после старта реализации; сейчас не трогать)

- `services/rag_chroma_store.py`, `services/rag_query_service.py`, `services/admin_knowledge_indexer.py`
- `repositories/*`, `database/migrations/*` (при расширении memory)
- `admin_api/routes/*` (diagnostics/eval endpoints при необходимости)
- `utils/config.py` (новые env)

### Стратегия тестирования

- unit: chunking, adapters, merge policy;
- integration: compose portfolio + RAG smoke;
- regression: существующие сценарии из docs + ручной прогон Admin UI modality pages;
- evaluation: отдельный offline job, не в hot path пользователя.

### Операционная стратегия

- фичефлаги для hybrid и cache;
- явное логирование в `processing_logs` при включении новых путей;
- откат: `RAG_BACKEND=chroma` и отключение флагов без миграции данных (где возможно).

## 26. P6 — архитектурные уточнения и engineering decisions (append-only)

Ниже — фиксация решений и ограничений для этапа **P6** и смежных направлений. Это **не** отчёт о реализации: production-код, миграции, compose и env на момент записи **не** менялись в рамках этого пункта.

### 26.1 FAISS isolation policy

**Политика backend:**

- **FAISS** рассматривается только как **secondary / demo / course** retrieval backend.
- **ChromaDB** остаётся **primary production** retrieval backend для AF.
- **FAISS** не должен становиться production backend «по умолчанию» ни через дефолты в коде, ни через неявные fallback-ветки.
- Переключение на FAISS допускается **только** через **explicit** env/config (явный выбор оператора/сборки), после осознанного решения.
- У FAISS должен быть **отдельный** путь хранения индекса (отдельный каталог/volume/префикс), не пересекающийся с production Chroma persistence.
- Smoke и regression сценарии для FAISS должны быть **отдельными** от production pipeline на Chroma; смешивание в одном «обязательном» CI-контуре без изоляции считается недопустимым риском регресса.
- **Случайное** переключение backend (ошибка env, неверный compose profile, дрейф конфигурации) классифицируется как **operational risk** первого порядка.

#### 26.1.1 Backend isolation

- Изоляция: отдельные индексы, отдельные пути persistence, отдельные тестовые датасеты (по плану реализации), чтобы demo/course не загрязняли production коллекцию и метаданные **PostgreSQL**.

#### 26.1.2 Retrieval backend safety

- Явный выбор backend обязан быть **наблюдаемым**: в health/readiness и в operational diagnostics должно быть видно, какой backend активен (после появления соответствующих механизмов), без «тихого» переключения.

#### 26.1.3 Explicit backend selection

- Любая смена backend трактуется как **изменение operational topology**, а не как внутренняя деталь: требуется явная конфигурация, документация шага и понимание последствий для indexing и cache invalidation (см. §26.3).

### 26.2 Conversational memory budget control

Conversational memory retrieval проектируется **с первого дня** с ограничениями **context budget** (в терминах токенов/эквивалентов для LLM), а не как неограниченный рост контекста.

**Принципы (план архитектуры):**

- **token budget awareness** — верхняя граница памяти + KB + служебных полей в одном запросе к LLM;
- **memory relevance threshold** — отсев слабых кандидатов до merge с KB;
- **recency weighting** — учёт свежести записей памяти при ранжировании;
- **max memory chunks** — жёсткий или мягкий потолок числа фрагментов памяти в retrieval;
- явное **разделение** потоков данных:
  - **dialog history** (сырой или нормализованный след переписки),
  - **semantic memory** (извлечённые/агрегированные «знания» о диалоге/проекте),
  - **KB retrieval context** (корпус базы знаний).

**Фиксация:** подход «**last N messages** как единственная модель памяти» **не** считается полноценной memory architecture; такой приём может использоваться как ограниченный UX-слой, но не как замена persistent memory и retrieval по памяти.

### 26.3 Retrieval cache invalidation strategy

Планируется архитектурный задел под **версионирование знания** для кеша retrieval, например:

- **`retrieval_generation_id`** — монотонный/уникальный идентификатор «поколения» retrieval-пространства после существенных изменений; и/или
- **`knowledge_base_revision`** — ревизия базы знаний, связанная с lifecycle документов и indexing.

**Смысл:**

- после **reindex** retrieval cache должен **инвалидироваться автоматически** (или становиться промахом с безопасным промахом — но предпочтение за явной инвалидацией по ревизии);
- **stale retrieval cache** трактуется как **критичный operational risk** (хуже, чем низкий hit ratio);
- связь invalidation с **lifecycle** `document_versions` / `indexing_jobs` (и при необходимости с поколением коллекции в vector backend) — обязательное направление проектирования.

**Принцип:** **корректность cache** важнее **cache hit ratio**.

### 26.4 Token-aware chunking (уточнение к smart chunking)

К направлению **smart chunking** (P6.2) добавляется стратегическое уточнение: AF должен **поэтапно** двигаться от **character-oriented** chunking к **token-aware** chunking.

**Причины (архитектурные, не статус реализации):**

- embeddings и **token windows** задаются в токенах;
- **retrieval budgets** и лимиты контекста LLM естественно считаются в токенах;
- длина в символах остаётся **лишь приближением** и источником ошибок при многоязычии и специальных символах.

**Важно:** на момент этой фиксации **не** утверждается, что token-aware chunking уже реализован в AF; это **целевое направление эволюции** chunking-слоя.

### 26.5 Retrieval architecture strategic direction

**P6** позиционируется не как «набор lesson-фич», а как:

- **coherent retrieval evolution roadmap** для платформы;
- **foundation retrieval platform layer** — общий слой абстракций, политик и observability вокруг retrieval;
- база для последующего развития: **hybrid retrieval**, **long-term memory**, **multimodal retrieval**, усиление **retrieval observability** и **retrieval security**.

Реализации из курса и каталогов `legacy/PEr0X_source/` остаются **donors / reference**, а не целевой production-архитектурой AF: перенос идей только через adaptation под текущие `services/` / `providers/` / `repositories/` и с сохранением operational-first дисциплины.

### 26.6 PROJECT_STATE positioning

`PROJECT_STATE.md` постепенно выполняет роль **engineering architecture ledger**: фиксация **decisions**, **operational lessons**, **architectural constraints** и **roadmap reasoning**, а не только краткий снимок «что сейчас запущено». Это согласуется с architecture-first подходом: состояние репозитория и принятые ограничения должны быть воспроизводимо читаемы без устной передачи контекста.

## 27. P6 — дополнительные архитектурные контракты (append-only)

Ниже — целевые **архитектурные обязательства и ограничения** для retrieval-платформы. Формулировки относятся к **планируемому** развитию (в т.ч. P6), а не к подтверждению того, что каждый пункт уже реализован в коде.

### 27.1 Retrieval observability contract

**Retrieval observability** считается **обязательной частью** retrieval platform architecture, а не опциональным «украшением» UI.

Retrieval layer должен трактоваться как **отдельный operational subsystem**: с ним должны быть возможны диагностика, сравнение инцидентов и контроль деградации **на уровне retrieval**, а не только «ответ LLM хороший/плохой».

**Целевые направления telemetry** (как архитектурная цель, единый контракт наблюдаемости; реализация и полнота — предмет последующих этапов):

- retrieval latency;
- embedding latency;
- retrieval backend (явная метка активного backend);
- `retrieval_generation_id` / **KB revision** (согласовано с §26.3);
- фактический `top_k` / лимиты выборки;
- `chunks retrieved count`;
- оценка объёма извлечённого контекста в токенах (**retrieved token estimate**), насколько это доступно без чрезмерного overhead;
- retrieval cache **hit/miss** (когда слой кеша появится);
- использование **retrieval fallback** (явные ветки «не полный retrieval»);
- события **retrieval degradation** / **failure** (отдельно от общего «LLM error»).

**Фиксация:** отсутствие retrieval telemetry там, где retrieval выполняется, трактуется как **operational blind zone** — недопустимо для platform-позиционирования AF.

Retrieval observability должна проектироваться **независимо**:

- от конкретного vector backend (**Chroma** / **FAISS** / иные);
- от конкретной **LLM**;
- от конкретной реализации **Admin UI** (смена фронта не должна «терять» смысл retrieval-диагностики на уровне контракта данных).

#### 27.1.1 Retrieval telemetry normalization

Имеется в виду **единый нормализованный слой** полей/имён/единиц измерения для retrieval-событий при смене backend/provider: одни и те же семантические метрики (latency, counts, revision, fallback) должны оставаться сопоставимыми в логах и в operational UI, иначе сравнение инцидентов между средами становится невозможным.

### 27.2 Embedding compatibility policy

**Embedding model** трактуется как часть **retrieval schema** (совместимость измерений и семантики retrieval), а не как «внутренняя implementation detail», которую можно менять без последствий.

**Правила (архитектурные):**

- совместимость **embedding dimensionality** обязательна: индекс и запросы должны быть согласованы по размерности;
- **смешивание** векторов разной **dimensionality** в одном активном retrieval-наборе **запрещено**;
- смена **embedding model** требует **explicit reindex strategy** (план, окно, контроль объёма, инвалидация кеша/ревизий);
- retrieval backend должен иметь возможность **проверять** совместимость (или отказывать явно), а не «молчать»;
- **silent degradation relevance** из-за несовместимости embeddings считается **critical operational risk**.

**Принцип:** **retrieval correctness** важнее **convenience migration** (быстрый «переключатель модели» без цикла reindex и проверки).

#### 27.2.1 Embedding migration safety

- **reindex** может быть дорогим по времени, деньгам и нагрузке — это принимается как нормальная цена смены embedding-контракта;
- миграция должна быть **explicit** (видимый этап, статусы, наблюдаемость прогресса/ошибок);
- **partial mixed-index state** (часть коллекции на старых embeddings, часть на новых) считается **опасным** состоянием и должно проектироваться как либо краткоживущее техническое окно с блокировками, либо как запрет без явного dual-write/dual-read дизайна.

### 27.3 Retrieval lifecycle ownership

Retrieval platform требует **явного ownership** lifecycle для:

- chunk lifecycle;
- embedding lifecycle;
- vector lifecycle;
- retrieval revision lifecycle;
- **active retrieval set** lifecycle;
- cache invalidation lifecycle (связка с §26.3).

**Фиксация:** «multi-version retrieval без explicit lifecycle ownership» считается источником **долгосрочной operational instability** (дубли, рассинхрон, непредсказуемые ответы, невозможность отката наблюдаемости).

**PostgreSQL** остаётся **metadata / lifecycle source of truth** для документов, версий, статусов индексации и связанных контрактов (в рамках существующей платформенной дисциплины AF).

#### 27.3.1 Active vs historical retrieval state

**Планируемое** (целевое) разделение концепций, без утверждения полной реализации:

- **historical metadata / history** — что было проиндексировано, какие версии существовали, аудит;
- **active retrieval corpus** — то, что участвует в retrieval здесь и сейчас;
- **archived retrieval state** — явно выведенные из активного поиска наборы (без «тихого» смешивания с активным).

Границы между ними должны быть операционно объяснимы (в т.ч. для инвалидации кеша и ревизий).

### 27.4 Retrieval platform positioning

Retrieval layer в AF развивается **не** как узкий «RAG helper», а как **retrieval platform subsystem** — фундамент для нескольких видов извлечения и управления ими.

**Целевые capability directions** (roadmap-направления, не чеклист готовности):

- hybrid retrieval;
- memory retrieval;
- multimodal retrieval;
- retrieval evaluation;
- retrieval observability;
- retrieval governance;
- retrieval security;
- retrieval lifecycle management.

Retrieval layer должен проектироваться как **provider-agnostic**, **backend-agnostic**, **observability-aware**, **operational-first**: смена провайдера или vector backend не должна разрушать контракт наблюдаемости и lifecycle.

### 27.5 Legacy integration safety

Правила работы с **legacy** усиливаются:

- legacy code — **только donor / reference**;
- legacy **не** считается доверенной production-реализацией;
- в legacy типичны: учебные shortcuts, слабая observability, упрощённые lifecycle-допущения, non-production security assumptions.

**Copy-paste integration запрещена.**

Разрешено только:

- controlled adaptation;
- interface extraction;
- algorithm reuse;
- comparative review.

#### 27.5.1 Architectural adaptation mandatory

Любой перенос идей из legacy обязан проходить через **architectural adaptation** под контракты AF (ownership, observability, security groundwork, P6-политики), а не через прямое включение файлов «как есть».

### 27.6 Operational scalability warning

Эволюция retrieval почти неизбежно увеличивает нагрузку и объём наблюдаемости:

- давление на **RAM**;
- давление на **CPU**;
- давление на **token** usage (embeddings + context + evaluation);
- давление на **storage** (индексы, артефакты, логи);
- давление на **indexing** (время и конкуренция за ресурсы);
- объём **observability** данных (риск «задушить» оператора шумом без normalization).

**Фиксация:** улучшение retrieval quality **может** ухудшить operational stability, если **не** развиваются параллельно observability, lifecycle ownership и политики деградации.

**Формулировка-риск:** «retrieval sophistication without operational discipline» считается **architectural risk**, а не «техническим долгом на потом».

---

## 28. Первичный operational contour: GitHub / portfolio container (append-only)

### 28.1 Решение

**Основным контуром разработки и runtime для дальнейшего развития Assistant Flow** принимается **GitHub / portfolio container** (compose portfolio: изолированный стек, воспроизводимый с нуля).

**Старый server contour** (немецкий VPS, существующая связка с Traefik, исторический PostgreSQL из предыдущих проектов и т.п.):

- **не удаляется** и не объявляется устаревшим в смысле «выключить и забыть»;
- **не является** primary operational baseline и **не** считается единственным source of truth для проверки архитектуры;
- используется **только** как: **fallback**, **reference**, **historical environment**, **контур сравнения при миграциях** и постмортемах.

### 28.2 Обязательная операционная дисциплина

- Дальнейшие этапы **P6+** (в т.ч. regression / integration smoke, проверка retrieval foundation и смежных изменений) **по умолчанию выполнять и принимать** в **portfolio / GitHub container contour**, где окружение **чистое, воспроизводимое** и ближе к **clone-and-up** модели.
- Архитектурные свойства платформы (контракты retrieval, lifecycle, observability) **проверять** в первую очередь в **clean reproducible deployment**, а не опираться на долгоживущее состояние одного production-like сервера как на неявный эталон.

### 28.3 Rationale (кратко)

- **Воспроизводимость** развёртывания и тестов без «скрытого» дрейфа конфигурации и данных.
- **Чистая модель деплоя** (полный подъём стека с нуля, предсказуемые volumes и сервисы).
- **Свежий bootstrap PostgreSQL** в составе portfolio stack — меньше исторического состояния и перекрёстных зависимостей с чужими контейнерами.
- **Меньше hidden state** и accidental coupling к уникальной топологии одного хоста.
- **Лучшее соответствие** стратегии portfolio / distribution и последующим этапам **P6–P11** на одной эталонной оси.

### 28.4 Важно: не путать с задачей миграции данных

Это решение — **смена первичного рабочего и проверочного контура** (engineering / operational direction), **а не** задача «перенести данные с сервера в portfolio» в рамках данной фиксации. Миграции БД, переписывание compose, массовая смена env и перенос данных **здесь не подразумеваются** и остаются отдельными задачами, если будут запрошены явно.

---

## 29. P6.2b — Стабилизация retrieval перед hybrid (append-only)

### 29.1 Контракт scores (backend-local)

- Текущие значения **score** в результатах retrieval **локальны для выбранного backend** (например, семантика расстояния Chroma vs L2 FAISS).
- Эти scores **не** считаются **глобально сравнимыми** между разными backend без отдельного слоя **normalization / reranking**.
- **Hybrid retrieval** (объединение выдачи нескольких backend) потребует явного проектирования этого слоя; до его появления **запрещено** смешивать сырые результаты разных backend в **одном ranking pipeline** как взаимозаменяемые по score.
- В коде на этапе P6.2b **не** вводится численная нормализация score — только инженерная фиксация контракта и комментарии/TODO в DTO/слое retrieval.

### 29.2 Минимальный контракт metadata для retrieval chunks

Для дальнейших этапов (hybrid, memory) зафиксирован **минимальный инвариант** полей в `metadata` у chunk после query mapping (с **safe defaults** для старых документов без массового reindex):

**Обязательные (после нормализации на read path):**

- `source` — строка источника (неизвестно → `"unknown"`);
- `chunk_id` — идентификатор фрагмента (если в индексе отсутствует — допускается **синтетический** id ранга в ответе, до полноценной индексации);
- `backend` — строка активного retrieval backend (`chroma`, `faiss`, …).

**Опционально (проброс, если уже есть в данных индекса):**

- `retrieval_timestamp` — время формирования ответа retrieval (UTC ISO), может выставляться runtime, если ключа не было;
- `document_id`, `version_id`, `tags` — без обязательного наличия на этом этапе.

**Эволюция схемы:** только **backward-compatible** расширения (новые опциональные поля, не ломающие читателей); изменения смысла обязательных полей — через явную версию контракта / design review.

### 29.3 Интерпретация RetrievalHealth (Chroma vs FAISS)

Единая семантика полей `RetrievalHealth`: `backend`, `ok`, `detail`, `collection_count` (см. docstring в коде `RetrievalHealth`).

**Chroma:** пустая коллекция (`collection_count == 0`) **не** считается «crash» инфраструктуры: `ok=True`, приложение может работать в режиме пустого корпуса (как и ранее по продуктовой семантике).

**FAISS (secondary):** пустой индекс (`ntotal == 0`) — `ok=False` (демо-backend без векторов трактуется как неготовность к полезному retrieval). Отсутствие файлов индекса при явном `RAG_BACKEND=faiss` — **ошибка на этапе сборки backend** (исключение), **без** молчаливого fallback на Chroma (политика P6.2a сохраняется).

### 29.4 Legacy PEr0X и FAISS в AF

- Каталоги `legacy/PEr0X_source/` остаются **donor-only**; их retrieval-семантика **не** является source of truth для AF.
- Реализация FAISS в AF **адаптирована** под контракты AF (`RetrievalBackend`, изоляция хранилища, metadata contract), а не копипаста урока.
- Любая ссылка на legacy для поведения scores/ranking допустима только как **сравнение**, не как эталон продукта.

---

## 30. P6.3 — Chunking как retrieval-quality subsystem (append-only)

### 30.1 Философия chunking

**Chunking** в AF трактуется как **отдельный engineering subsystem**, влияющий на **retrieval quality** и шум контекста, а не как «вспомогательная нарезка текста» перед записью в векторное хранилище. Решения по границам chunk’ов должны согласовываться с operational наблюдаемостью RAG (размеры, число chunk’ов, деградация при больших документах).

### 30.2 Текущий слой и token-aware будущее

- На этапе **P6.3** размеры и overlap задаются как **character-oriented approximation** (параметры `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` и внутренние лимиты `SmartChunker`).
- **Будущее направление:** **token-aware** chunking и бюджеты в токенах поверх этого слоя (без отмены детерминированного foundation); миграция должна сохранять **backward-compatible** metadata и не ломать существующие индексы без явного reindex-цикла.

### 30.3 Риски chunking (связь с retrieval)

- **Retrieval noise** — слишком крупные или слишком мелкие chunk’ы ухудшают попадание в top-k.
- **Context explosion** — чрезмерное число chunk’ов увеличивает стоимость embeddings/index и нагрузку на retrieval.
- **Chunk fragmentation** — избыточное дробление одной темы на множество обрывков снижает семантическую целостность контекста.
- **Semantic dilution** — смешение несвязанных абзацев в одном chunk (до semantic chunking) ограничивается **paragraph-first** эвристиками, но не устраняется полностью без последующих этапов.

### 30.4 Deterministic-first policy

Сначала закрепляются **детерминированные** правила (абзацы, лимиты, overlap, safeguard от giant chunks и explosion по числу chunk’ов через предупреждения), затем — отдельные эксперименты с **semantic / LLM chunking** и кластеризацией. **Semantic AI chunking** в P6.3 **не** внедряется.

### 30.5 Legacy (PEr03 / PEr08)

Идеи paragraph / sentence splitting из **legacy PEr03 / PEr08** используются только как **reference** при адаптации; реализация **SmartChunker** в `services/chunking/` — контракт AF, **не** копипаста монолита и **не** source of truth для семантики продукта.

### 30.6 Интеграция в индексацию (P6.3)

- Основной путь нарезки для локальных документов переведён на **`services/chunking/SmartChunker`** вместо `RecursiveCharacterTextSplitter` в **`services/rag_document_loader.py`** и при разбиении `.txt`/`.md` в **`services/admin_knowledge_indexer.py`**.
- Продуктовые семантики API/UI **не** менялись: на выходе по-прежнему список `Document` с `page_content` и `metadata` для Chroma/индексаторов.

---

## 31. Conversational Memory Foundation (P6.3, append-only)

### 31.1 Назначение

Реализуется **persistent dialog memory foundation**: явный access layer к истории диалога в PostgreSQL (`chat_sessions`, `chat_messages`). Это **не** semantic memory, **не** hybrid retrieval с KB и **не** смешение с RAG read path в production.

### 31.2 Инварианты

- В историю попадают только **чистые** user query и **чистый** assistant answer (после `format_for_telegram` там, где применимо).
- **RAG / KB retrieval context** (чанки, промежуточный контекст) в dialog history **не** сохраняются.
- **PostgreSQL** остаётся source of truth для персистентной истории.
- **Будущая semantic memory** — отдельный retrieval namespace и отдельный этап; на этом шаге только структурные записи и read API с **memory budget** (character approximation; token-aware — позже).
- **Memory budget** обязателен как защита от context explosion **до** любого hybrid retrieval.

### 31.3 Кодовая поверхность

- Каталог `services/memory/`: `base.py` (record/query/policy/protocol), `conversation_memory_service.py`, `__init__.py`.
- Репозитории и сервисы сессий: `repositories/session_repository.py`, `services/chat_session_service.py`; пользователь Telegram → `app_users` через `services/app_user_service.py` + `repositories/user_repository.py`.
- Telegram: best-effort `persist_telegram_dialog_turn_best_effort` после успешной отправки ответа (RAG, text orchestrator, voice→text), без изменения текста для пользователя.
- Smoke: `scripts/test_conversation_memory_smoke.py`.

### 31.4 Архитектурные уточнения (P6.3)

- **Conversational memory** — отдельный subsystem (`services/memory/`) с собственным budget discipline и operational logs; **не** helper внутри orchestrator и **не** ad-hoc «последние N» вне этого слоя.
- **PostgreSQL** остаётся **единственным SoT** для персистентной dialog history; **нет** memory embedding runtime path, **нет** индексации истории в Chroma/FAISS на этом этапе.
- **Semantic memory retrieval** и **hybrid retrieval** с KB — **намеренно отложены** (отдельные этапы / namespaces).
- **Memory budgeting сейчас char-based** (детерминированный trim, conservative defaults, стабильный порядок: сначала cap по `limit`/`max_recent_messages`, затем обход от новых к старым с cap по `total_memory_chars_budget` без превышения суммарной длины выдачи). **Token-aware memory budgeting** — отложен.
- **Memory subsystem** спроектирован с заделом на **future namespace separation** (dialog vs semantic vs KB); runtime-path на этом этапе — **operational-safe foundation only**.
- **Correlation:** `execution_id` пробрасывается опционально; обязательным не делается; миграции ради одного поля не вводились.

### 31.5 History hygiene (инвариант)

В персистентную историю попадают только **clean user query** и **clean assistant answer**. Запрещено сохранять: retrieved chunks, retrieval diagnostics, prompt assembly, system prompts, скрытые metadata dumps, raw RAG context.

### 31.6 Observability

Компактные строки `memory:`: `session_id`, `messages_loaded` / `messages_saved`, `budget_applied`, `limit` (на read), `latency_ms`; без текста сообщений и без dump истории / ПДн.

---

## 32. Operational testing rule — DB / RAG / runtime (append-only)

```text
Все DB/RAG/runtime smoke tests после изменений кода выполняются только внутри
portfolio-test-assistant-flow-1 после rebuild portfolio-test stack.

Host-level python tests допустимы только для pure unit/syntax checks без
DB/Chroma/env/runtime зависимостей.

Перед DB/RAG/runtime тестами обязательно:
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build

Затем тесты выполнять через:
docker exec portfolio-test-assistant-flow-1 python <script>
```

**Причина:** код на хосте и образ `/app` в контейнере расходятся без rebuild; primary contour — `portfolio-test-*` с согласованным `DATABASE_URL`, Chroma и env.

---

## 33. P6.4 Hybrid Retrieval Foundation (append-only)

### 33.1 Назначение

Foundation для **hybrid context assembly**: `KB retrieval context` + `dialog memory context` через отдельный слой `services/hybrid_retrieval/`. Это **не** новый retriever backend и **не** включение hybrid в production path по умолчанию.

### 33.2 Feature flag и поведение

- `ENABLE_HYBRID_RETRIEVAL` в env / `AppConfig.enable_hybrid_retrieval` — **по умолчанию false**.
- При **false** путь `RagQueryService.answer` совпадает с прежним KB-only (без изменения retrieval semantics).
- При **true** и переданных `hybrid_session_id` / `hybrid_user_id` в `answer(...)` контекст для LLM может собираться через `HybridContextService` (опциональная интеграция; Telegram по умолчанию не передаёт session id — hybrid не активируется).

### 33.3 Инварианты

- **KB priority > memory**: сначала KB-блок в пределах `max_kb_chars` / `max_kb_chunks`, затем memory только из остатка `max_context_chars` и в пределах `max_memory_chars` / `max_memory_messages`. Memory **не вытесняет** KB.
- **No score mixing**: детерминированный порядок элементов — **сначала kb, затем memory**; общий ranking KB + memory **запрещён** до semantic memory / rerank (см. комментарии в коде).
- **Нет** semantic memory retrieval, **нет** vectorized memory, **нет** RAGAS, **нет** cache на этом этапе.
- Dialog history hygiene (P6.3) сохраняется: в PG по-прежнему только clean user/assistant, без сохранения RAG chunks в историю.

### 33.4 Кодовая поверхность

- `services/hybrid_retrieval/base.py` — `HybridContextItem`, `HybridContextResult`, `HybridRetrievalPolicy`, `HybridSourceType`.
- `services/hybrid_retrieval/hybrid_context_service.py` — `HybridContextService.build(...)`.
- `utils/config.py` — `enable_hybrid_retrieval`; `.env.example` — `ENABLE_HYBRID_RETRIEVAL=false`.
- `services/rag_query_service.py` — условная сборка контекста при flag + `hybrid_session_id`.
- Smoke: `scripts/test_hybrid_retrieval_smoke.py`.

### 33.5 Observability

Строка `[assistant-flow] hybrid:`: `hybrid_enabled`, `kb_items_count`, `memory_items_count`, `total_context_chars`, `budget_applied`, `memory_truncated`, `kb_truncated`, `latency_ms` — без текста контента.

### 33.6 Future (намеренно не в P6.4)

- Semantic memory namespace, reranking, score normalization между KB и memory, security filtering, token-aware hybrid budgets — отдельные этапы после foundation.

---

## 34. P6.5 RAG Evaluation Foundation (append-only)

### 34.1 Назначение

**Evaluation layer** для качества RAG (retrieval/answer/faithfulness readiness) — **offline / diagnostic**, не production monitoring и не Admin UI. Вызывает существующий `RagQueryService` **read-only** и анализирует результат; **не** меняет retrieval, prompt, top_k по умолчанию и **не** подключается к Telegram runtime.

### 34.2 RAGAS и baseline

- **RAGAS** — **опционален** (`ENABLE_RAGAS_EVALUATION`, default false); при отсутствии пакета или отложенном full pipeline — статус **skipped**, не failed.
- **Internal deterministic checks** — baseline smoke: `answer_non_empty`, `contexts_non_empty` (для `should_have_answer=true`), `no_context_when_should_not_have_answer`, `answer_mentions_no_info` / эвристика для no-answer кейсов, `source_count`, `context_count`, `max_context_chars`, `total_context_chars`.

### 34.3 Dataset и артефакты

- Smoke dataset: `evaluation/datasets/rag_smoke_dataset.json` (7 generic вопросов) — **не** production benchmark; при непредсказуемом KB в portfolio допускаются мягкие эвристики и warnings.
- Скрипт: `scripts/evaluate_rag_smoke.py`; отчёт JSON: `outputs/evaluation/rag_smoke_report.json` (путь через `RAG_EVAL_OUTPUT_DIR`).
- Конфиг/env: `RAG_EVAL_DATASET_PATH`, `RAG_EVAL_OUTPUT_DIR`, `ENABLE_RAGAS_EVALUATION`.

### 34.4 Кодовая поверхность

- `services/evaluation/base.py`, `rag_evaluation_service.py`, `ragas_adapter.py`, `__init__.py`.
- Идеи legacy (`legacy/PEr06_source/evaluate_rag.py`, `legacy/PEr08_source/assistant_api/evaluate_ragas.py`) — только reference, без копипаста монолита.

### 34.5 Future

- Curated benchmarks, scheduled evaluation jobs, Admin UI metrics, полноценный RAGAS (judge LLM, datasets), кэш и оптимизации — после P6.5 (см. также §32 operational testing rule).

---

## 35. P6.6 Retrieval Optimization & Cache Foundation (append-only)

### 35.1 Назначение

**Локальный** слой оптимизации: SQLite cache (`storage/cache/assistant_cache.sqlite3` по умолчанию), **не** source of truth и **не** PostgreSQL. Redis / distributed cache / async workers — **намеренно отложены**.

### 35.2 Поведение по умолчанию

- `ENABLE_RETRIEVAL_CACHE=false`, `ENABLE_ANSWER_CACHE=false` — runtime Telegram/RAG **без** обёртки кэша retrieval и **без** answer-cache в LLM path.
- При `ENABLE_RETRIEVAL_CACHE=true`: `CachingRetrievalBackend` в `build_retrieval_backend` — lookup перед `search`, set после **успешного непустого** результата; **не** кэшируются ошибки, **не** кэшируется пустой retrieval, **не** кэшируется hybrid memory context (обёртка только вокруг vector retrieval).

### 35.3 Namespaces и ключи

- Контрактные namespace: `query`, `retrieval`, `answer`, `evaluation` (`CacheNamespaces`).
- Fingerprint retrieval: нормализованный query, `rag_backend`, `top_k`, `openai_embedding_model`, `RAG_RETRIEVAL_GENERATION` (default `unset`), флаг hybrid. **Риск:** без bump `RAG_RETRIEVAL_GENERATION` / knowledge_base_revision после reindex возможен **stale cache** — после успешного `admin_index_documents` вызывается `invalidate_retrieval_cache` (hook).

### 35.4 Invalidation / TTL

- `invalidate_retrieval_cache(reason)` — очистка namespace `retrieval`.
- TTL: `RETRIEVAL_CACHE_TTL_SECONDS` / `ANSWER_CACHE_TTL_SECONDS` (default 86400); `0` или отсутствие — без истечения (expires_at NULL) при реализации set.

### 35.5 Answer cache foundation

- `AnswerCacheService` — контракт get/set в namespace `answer`; **не** интегрирован в `RagQueryService` на этом этапе (избежание смены семантики ответов).

### 35.6 Observability

- Логи retrieval cache: `[assistant-flow] cache:` с `cache_enabled`, `namespace`, `outcome` (hit / miss_set / miss), `key_hash_prefix` (16 hex), `latency_ms`, `reason_skip` при пропуске.

### 35.7 Скрипты

- `scripts/test_cache_foundation_smoke.py` — unit-level SQLite + fingerprint (host OK).
- `scripts/test_retrieval_cache_smoke.py` — portfolio container, временный `CACHE_DB_PATH`, принудительно `ENABLE_RETRIEVAL_CACHE=true`.

### 35.8 Future (P6.7+)

- Redis, Admin UI cache stats, политика answer cache с security review, document version в fingerprint, production-grade invalidation.

