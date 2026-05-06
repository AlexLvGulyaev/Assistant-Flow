# Assistant Flow / Career Knowledge Assistant

**Portfolio-ready MVP:** a multi-user Telegram assistant for career-oriented Q&A, grounded answers over an admin-curated knowledge base (RAG), and optional image generation. The bot speaks Russian in default prompts; the repo and docs are English-friendly for GitHub.

---

## Problem

Career coaching and internal HR/L&D knowledge are often scattered across documents. Generic chatbots hallucinate or ignore org-specific material. Teams need a **controlled** knowledge base: only admins ingest documents, while users query through a single Telegram interface with clear **text** vs **RAG** behavior.

---

## Solution

- **Telegram** as the user channel: `/mode text` for GigaChat-driven dialogue and image generation; `/mode rag` for **read-only** retrieval over **ChromaDB** plus an OpenAI-compatible LLM for answers with **cited sources**.
- **PostgreSQL** holds the **contract** for users, documents, indexing jobs, sessions/messages, and audit tables (`database/schema.sql`, `database/db_contract.md`).
- **ChromaDB** holds **vectors**; metadata sync on index runs is optional via the admin CLI when `DATABASE_URL` is set.
- **Admin CLI** indexes files from disk (`scripts/admin_index_documents.py`); users **cannot** upload documents in Telegram.

Detailed layering: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Features

| Area | What you get |
|------|----------------|
| **Text mode** | GigaChat orchestration, prompt enhancement, image generation (OpenAI/Proxy providers) |
| **RAG mode** | Chunked docs → Chroma; similarity search; grounded answers + source list in Telegram |
| **Admin** | CLI indexing, optional PostgreSQL rows for `documents` / `document_versions` / `indexing_jobs` |
| **Ops** | SQLite `logs.db` for provider telemetry; Streamlit `dashboard.py`; PostgreSQL schema ready for full audit |
| **Modes / UX** | `/mode`, `/stats`, `/reset`; in-memory session until DB wiring is completed |

---

## Architecture

High-level data and control flow:

```text
User (Telegram) → interfaces/telegram_bot.py
                  ├─ text → core/orchestrator.py → services/providers → GigaChat, images
                  └─ rag  → services/rag_query_service.py → Chroma + LLM

Admin (CLI)     → scripts/admin_index_documents.py → Chroma (+ optional PostgreSQL)
```

| Directory | Role |
|-----------|------|
| `core/` | Orchestration (text/image pipeline) |
| `services/` | API clients, RAG, admin indexer, image service |
| `providers/` | GigaChat, embeddings, image backends, OpenAI-compatible chat |
| `interfaces/` | Telegram entrypoint |
| `repositories/` | PostgreSQL data access |
| `utils/` | Config, logging, Telegram formatting, in-memory user mode |
| `database/` | SQL schema, contract, setup notes |
| `docs/` | Architecture, admin indexing, RAG smoke test, **demo scenarios** |
| `legacy/pem09_source/` | **Reference only** (PEm09 course project). **Not imported at runtime.** Kept for comparison and coursework reporting. |

Full narrative: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Quick start

1. **Clone** and create a virtualenv (Python 3.10+ recommended).

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate  # Linux/macOS
   ```

2. **Install**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure** — copy `.env.example` → `.env` and set at least:

   - `TELEGRAM_BOT_TOKEN`
   - `GIGACHAT_*` (see `.env.example` groups)
   - OpenAI **or** Proxy keys for RAG + images as you use them
   - Optional: `DATABASE_URL` after applying `database/schema.sql` ([database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md))

4. **Index knowledge (admin)** — place `.pdf` / `.txt` / `.md` under `data/documents/`, then:

   ```bash
   python scripts/admin_index_documents.py --reindex
   ```

5. **Run the bot**

   ```bash
   python run_telegram_bot.py
   ```

6. **Optional:** `python main.py` (CLI prompt), `streamlit run dashboard.py` (SQLite analytics).

---

## Admin knowledge base indexing

Indexing is **CLI-only** (no Telegram uploads for end users).

```bash
python scripts/admin_index_documents.py --reindex
```

- **`--reindex`** — wipe `CHROMA_PERSIST_DIR` and rebuild vectors.
- **`--no-postgres`** — Chroma only (skip metadata tables).
- **`--documents-dir PATH`** — override `RAG_DOCUMENTS_DIR`.

Details: **[docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md)**.  
Dev one-shot check: **[docs/RAG_SMOKE_TEST.md](docs/RAG_SMOKE_TEST.md)** (`scripts/rag_smoke_test.py`).

---

## Telegram commands

| Command | Description |
|---------|-------------|
| `/start`, `/help` | Intro and capability summary |
| `/mode` | Show current mode; `/mode text` or `/mode rag` |
| `/stats` | Chroma chunk count + paths to index and document folders |
| `/reset` | Force `text` mode and clear in-memory RAG history for the user |

**Note:** Mode and short RAG history are **in-memory** today; PostgreSQL `chat_sessions` / `chat_messages` are planned (see `utils/telegram_user_state.py` TODO).

---

## Demo scenarios

Step-by-step checks (text, RAG, `/stats`, admin CLI, images): **[docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md)**.

---

## Limitations

- **LLM risk:** Answers may be wrong or oversimplified; not a substitute for professional advice where regulated.
- **Images:** Slow and provider-dependent; content policies apply.
- **RAG:** Quality depends on chunking, embeddings, and corpus; empty or stale Chroma yields fallback answers.
- **Scale:** Single-process bot and in-memory mode store; horizontal scaling and full DB-backed sessions are not implemented yet.
- **Logging:** Product `request_logs` / `error_logs` in Postgres are defined but not fully wired to all code paths; SQLite `logs.db` covers much of the orchestrator/image telemetry today.

---

## Roadmap

- Persist Telegram mode and RAG history in **PostgreSQL** (`chat_sessions`, `chat_messages`).
- Wire **request_logs** / **error_logs** for unified audit.
- Optional **voice / vision** modalities (post-RAG stabilization).
- **Migrations** under `database/migrations/` for schema evolution.
- RAG uses **native `chromadb`** (`HttpClient` or `PersistentClient`); see `CHROMA_USE_HTTP` in `.env.example`.

---

## Environment variables

Grouped template with comments: **`.env.example`**.  
PostgreSQL apply guide: **[database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md)**.  
Contract rules: **[database/db_contract.md](database/db_contract.md)**.

---

## Documentation index

| Doc | Topic |
|-----|--------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | User vs admin contours, Postgres, Chroma, Telegram read-only |
| [docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md) | Admin CLI indexing |
| [docs/RAG_SMOKE_TEST.md](docs/RAG_SMOKE_TEST.md) | Local RAG smoke test |
| [docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md) | Demo / portfolio checks |

---

## PEm09 / legacy note

The folder **`legacy/pem09_source/`** is the **donor reference** from an educational PEm09 project (patterns for RAG, Chroma, async handlers). **Assistant Flow does not import it at runtime.** It is retained only for comparison and reporting on how ideas were reimplemented in this repository’s architecture.
