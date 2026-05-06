# Architecture — Assistant Flow / Career Knowledge Assistant

This document describes how the system is split between user-facing flows, admin flows, and data stores. Runtime code lives under `core/`, `services/`, `providers/`, `interfaces/`, `utils/`; it does **not** import from `legacy/pem09_source/` (that tree is reference-only).

## User contour (Telegram)

- **Entry:** `interfaces/telegram_bot.py` (polling, `pyTelegramBotAPI`).
- **Modes:** `text` (default) and `rag`, stored in memory per Telegram `user_id` (`utils/telegram_user_state.py`). A future step is to persist mode and history in PostgreSQL (`chat_sessions`, `chat_messages`) per `database/db_contract.md`.
- **Text mode:** `core/orchestrator.PromptOrchestrator` — GigaChat for answers, keyword routing for image generation, `services/image_generation_service.py` for images.
- **RAG mode:** `services/rag_query_service.py` — read-only retrieval from Chroma + OpenAI-compatible chat for grounded answers; sources are appended in the reply.
- **Read-only knowledge:** Users **cannot** upload documents via Telegram. They only **query** what was already indexed by an administrator.

## Admin contour (CLI)

- **Indexing:** `scripts/admin_index_documents.py` with `services/admin_knowledge_indexer.py` — scans `RAG_DOCUMENTS_DIR` (recursive `.pdf` / `.txt` / `.md`), chunks documents, writes vectors to Chroma.
- **Optional metadata:** If `DATABASE_URL` is set and `--no-postgres` is not passed, each file run updates `documents`, `document_versions`, and `indexing_jobs` via `repositories/document_repository.py`.
- **Smoke test (dev):** `scripts/rag_smoke_test.py` — one-shot index + question for local checks (see `docs/RAG_SMOKE_TEST.md`).

## PostgreSQL as source of truth

- **Schema:** `database/schema.sql`; rules: `database/db_contract.md`.
- **Role:** Canonical records for users (future full wiring), documents, versions, indexing jobs, chat/session/message contracts, request/error logs (tables exist; not all are fully used by runtime yet).
- **Access:** Application code should use repositories/services, not raw SQL from Telegram handlers. Repositories use `DATABASE_URL` (`repositories/connection.py`).

## ChromaDB as vector index

- **Persistence:** Directory `CHROMA_PERSIST_DIR` (default `data/chroma_db`), collection `assistant_flow_rag` (`services/rag_chroma_store.py`).
- **Embeddings:** OpenAI-compatible API (`providers/rag_embeddings.py`); same credential pattern as RAG chat (`OPENAI_API_KEY` or `PROXY_API_KEY`, optional `OPENAI_BASE_URL` / proxy base URL).
- **Separation:** Vector payloads live in Chroma; PostgreSQL holds document metadata and job status when admin indexing is enabled.

## Request flow (simplified)

```text
Telegram (user)
  → handlers (interfaces/telegram_bot.py)
  → text mode: orchestrator → services/providers → GigaChat / image APIs
  → rag mode: RagQueryService → Chroma + OpenAI-compatible LLM

Admin
  → admin_index_documents.py → AdminKnowledgeIndexer → Chroma (+ optional PostgreSQL)
```

## Logging and analytics (separate from Postgres contract)

- **SQLite `logs.db`:** Technical provider logs (`utils/request_logger.py`) for orchestrator and image flows; `dashboard.py` reads this file.
- **PostgreSQL `request_logs` / `error_logs`:** Defined in `schema.sql` for product-level auditing; integration can be extended without changing the high-level split above.

## Legacy reference (PEm09)

- **`legacy/pem09_source/`** — donor educational project (async bot, LangChain RAG patterns). **Not imported at runtime.** Ideas were manually adapted into this codebase; keep the folder for comparison and coursework reporting only.
