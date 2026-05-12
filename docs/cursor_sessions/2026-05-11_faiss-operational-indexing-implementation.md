# Session: FAISS operational indexing (append-only)

## Prompt (summary)

Сделать FAISS полноценным secondary operational backend для Documents → indexing → retrieval при `RAG_BACKEND=faiss` + `FAISS_INDEX_DIR`, без поломки Chroma default; расширить `RetrievalBackend` write contract; manifest/embedding checks; admin stats/API/UI нейтральные поля; lifecycle observability; smoke `scripts/test_faiss_operational_indexing_smoke.py`; PROJECT_STATE append; без коммита.

## Audit root cause (before)

- Индексация была **Chroma-only** (`AdminKnowledgeIndexer` → `ChromaRagStore`).
- FAISS был **query-only** при готовом индексе; operational path не писал в FAISS.

## Indexing path (after)

1. **Before:** `reset_chroma_for_reindex` → `ChromaRagStore` → `_index_one_file` → `store.delete` / `store.add` → `count_chroma_chunks`.
2. **After:** `build_openai_embeddings` → по `rag_backend`: **chroma** — `ChromaRagStore` + `ChromaBackend`, при `reindex` — `reset_for_full_reindex` на backend; **faiss** — `FaissBackend(..., allow_empty=True)`, при `reindex` — `reset_for_full_reindex` → цикл `_index_one_file` → `vector_backend.delete_vectors_for_document_before_reindex` / `add_documents` → `collection_count` / manifest на диске.

## Changed files (high level)

- `services/retrieval/base.py` — write methods на `RetrievalBackend`.
- `services/retrieval/chroma_backend.py` — делегирование reset/add/delete; lazy import `reset_chroma_for_reindex`.
- `services/retrieval/faiss_backend.py` — operational read/write/persist/manifest/contract checks.
- `services/retrieval/factory.py` — FAISS без файлов → пустой operational индекс.
- `services/cache/caching_retrieval_backend.py` — делегирование мутаций + invalidation cache.
- `services/rag_chroma_store.py` — `app_config` property.
- `services/admin_knowledge_indexer.py` — backend-aware indexer, PG collection label `faiss`, `AdminIndexReport.vector_index_chunk_count`.
- `services/admin_service.py` — counts / KB status / reindex lifecycle для FAISS.
- `services/rag_local_indexer.py` — `RetrievalBackend` вместо прямого store.
- `scripts/rag_smoke_test.py`, `scripts/test_rag_regression.py`, `scripts/admin_index_documents.py`, `scripts/test_retrieval_backend_factory.py`.
- `scripts/test_faiss_operational_indexing_smoke.py` — новый.
- `admin_api/routes/documents.py`, `frontend/admin-ui/src/api/client.ts`, `frontend/admin-ui/src/pages/DocumentsPage.tsx`.
- `PROJECT_STATE.md` — §45.

## Chroma compatibility

- Поведение **Chroma** при `RAG_BACKEND=chroma` сохранено: тот же `ChromaRagStore`, reset через `reset_chroma_for_reindex` внутри `ChromaBackend.reset_for_full_reindex`, затем `refresh_client_and_collection`.

## FAISS operational smoke

- Запуск в контейнере `portfolio-test-assistant-flow-1` (после rebuild) с `OPENAI_API_KEY`:
  - `python scripts/test_retrieval_backend_factory.py`
  - `python scripts/test_retrieval_stabilization_smoke.py`
  - `python scripts/test_faiss_operational_indexing_smoke.py`
- В текущей dev-среде агента без `faiss`/`langchain` в host Python полный прогон не выполнялся.

## Limitations / deferred

- Single-doc FAISS → full corpus rebuild (согласовано).
- Нет dual-write; нет UI switch backend; демо `build_faiss_demo_index.py` остаётся отдельным инструментом.
