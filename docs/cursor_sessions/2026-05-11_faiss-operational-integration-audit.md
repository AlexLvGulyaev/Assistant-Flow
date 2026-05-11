# FAISS operational integration audit (2026-05-11)

Append-only session log. No code refactor in this step; audit + documentation only.

## Verdict

**Operational Documents → upload/reindex → indexing → active retrieval is Chroma-only.** FAISS is **not** wired into that pipeline.

With **`RAG_BACKEND=faiss`** and a pre-built index under **`FAISS_INDEX_DIR`**, **RAG retrieval queries** can run via **`RetrievalBackend`** / **`FaissBackend`** (`RagQueryService` uses `_retrieval.search`). That path is **query-only** and **not** fed by the same indexer that Documents UI uses.

**Readiness level:** FAISS = **smoke / demo / partial (retrieval-only)**; **not** fully operational as a second vector store behind Documents workflow.

## Active trace (indexing)

1. **React Admin UI** → FastAPI **`admin_api/routes/documents.py`** (`POST /documents/reindex`, upload, etc.)
2. **`services/admin_service.py`** — `run_reindex`, `upload_txt_and_index`, `reindex_document_file`
3. **`services/admin_knowledge_indexer.py`** — `AdminKnowledgeIndexer.run` / `index_single_file`
4. **Chunking:** `SmartChunker`, `rag_document_loader.load_and_split_*`
5. **Embeddings:** `build_openai_embeddings`
6. **Vector write:** **`ChromaRagStore`** only (`add_documents`); on full reindex **`reset_chroma_for_reindex`**
7. **PostgreSQL (when enabled):** `DocumentRepository` / versioning inside indexer — tied to this Chroma upsert flow

**No step** invokes `FaissBackend`, `faiss.write_index`, or `build_faiss_demo_index` from this chain.

## Active trace (retrieval query)

1. **`interfaces/telegram_bot.build_rag_query_service`** (and eval/smoke scripts)
2. Constructs **`ChromaRagStore`** + **`build_retrieval_backend(config, chroma_store=store, embeddings=embeddings)`**
3. **`services/retrieval/factory.py`** — if `RAG_BACKEND=faiss` → **`FaissBackend`** (requires index files + embeddings); if `chroma` → **`ChromaBackend(store)`**
4. **`services/rag_query_service.RagQueryService`** — `_similarity_search_with_timeout` → **`_retrieval.search`**

## FAISS persistence semantics

- **On disk:** `vectors.faiss`, `chunks.json`, `manifest.json` under `FAISS_INDEX_DIR` (`services/retrieval/faiss_backend.py`).
- **Reload:** process restart loads from disk when `FaissBackend` is constructed.
- **Writer for operational corpus:** only **`scripts/build_faiss_demo_index.py`** (fixed demo chunks; script states it does not touch PostgreSQL or production Chroma indexers).
- **Not in-memory synthetic** for production: format is real FAISS + JSON; **operational indexing** into that format **is missing**.

## PostgreSQL lifecycle vs FAISS

- Indexing jobs / document_versions / document_chunks updates occur in **`AdminKnowledgeIndexer`** paths that **always** write vectors to **Chroma**.
- Switching **`RAG_BACKEND=faiss`** does **not** repoint those writes to FAISS. Risk: **lifecycle says indexed**, **queries read FAISS demo index** — inconsistent unless operators manually maintain parity.

## Reindex / backend switch risks

- **Full reindex:** clears/recreates **Chroma** only; **FAISS directory unchanged** → stale vectors relative to new Chroma state.
- **chroma → faiss:** queries change source; **PG + UI** still describe Chroma-oriented indexing unless operators align data manually.
- **Duplication:** possible if both backends populated independently without single source of truth.

## Hardcoded Chroma (non-exhaustive list)

| Location | Role |
|----------|------|
| `services/admin_knowledge_indexer.py` | Indexer |
| `services/rag_local_indexer.py` | CLI/local indexer |
| `services/admin_service.py` | Reindex orchestration, Chroma counts |
| `services/rag_chroma_store.py` | Vector client |
| `interfaces/telegram_bot.py` | Always builds `ChromaRagStore` for `build_rag_query_service` |

## Tests (host sandbox)

- `python scripts/test_retrieval_backend_factory.py` → **OK** (exit 0).
- `python scripts/test_retrieval_stabilization_smoke.py` → **failed** here: missing `faiss`/`numpy` in environment (`faiss_synthetic` block); optional Chroma/real_faiss skipped (`langchain_openai`). **In Docker portfolio image** expect full deps — re-run there for green.

## Optional minimal fix (deferred)

No one-line fix makes Documents pipeline write FAISS; that requires indexer design. **Optional future hygiene:** lazy-create `ChromaRagStore` in `build_rag_query_service` only when `RAG_BACKEND=chroma` — reduces confusion and startup cost for faiss-only; not done in this audit step.

## Checklist if pursuing operational FAISS

1. Define single chunk pipeline output consumable by both Chroma and FAISS writers.
2. Branch `AdminKnowledgeIndexer` (or successor) on `rag_backend` **or** add export job Chroma→FAISS with explicit versioning.
3. Extend reindex to invalidate/rebuild FAISS artifact in lockstep with PG lifecycle.
4. Add integration tests: upload → query with `RAG_BACKEND=faiss` and assert chunk content matches uploaded doc.
