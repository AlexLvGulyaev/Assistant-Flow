# Session: P6.9 — Weaviate operational backend + runtime retrieval manager

**Date:** 2026-05-12  
**Scope:** Operational Weaviate (`WeaviateBackend`), `RetrievalBackendManager` (env-effective backend, FAISS stale reload), factory + Telegram/RAG wiring, admin collection count + indexer parity, smoke tests, `.env.example` / compose alignment with audit `2026-05-11_weaviate-operational-backend-and-runtime-switch-audit.md`.

---

## Changed / added files

| Area | Path |
|------|------|
| Compose | `docker-compose.portfolio.yml` — Weaviate service, volume, healthcheck, host port 8089 |
| Deps | `requirements.txt` — `weaviate-client` pin |
| Config | `utils/config.py` — `WEAVIATE_*` fields |
| Env template | `.env.example` — `RAG_BACKEND`, `FAISS_INDEX_DIR`, `WEAVIATE_*`, header ports |
| Weaviate backend | `services/retrieval/weaviate_backend.py` (new) |
| Runtime manager | `services/retrieval/runtime_manager.py` (new); lazy imports for embeddings + Chroma store |
| FAISS | `services/retrieval/faiss_backend.py` — `faiss_disk_fingerprint()` |
| Factory | `services/retrieval/factory.py` — `weaviate` branch, explicit errors |
| RAG | `services/rag_query_service.py` — `RetrievalBackend \| RetrievalBackendManager`, single `get_retrieval()` per similarity batch |
| Telegram | `interfaces/telegram_bot.py` — `RetrievalBackendManager` + `RagQueryService(manager, …)` |
| Admin | `services/admin_service.py` — `get_collection_count` for `weaviate` |
| Indexer | `services/admin_knowledge_indexer.py` — Weaviate full-corpus single-file path, `idx_path` logging |
| Tests | `scripts/test_weaviate_operational_indexing_smoke.py` (new), `scripts/test_retrieval_backend_factory.py`, `scripts/test_retrieval_stabilization_smoke.py` |

---

## Runtime architecture

- **Before:** `build_rag_query_service` built `ChromaRagStore` + `build_retrieval_backend` once; `RagQueryService` held a fixed `RetrievalBackend` instance for process lifetime → FAISS on-disk updates invisible until container restart.
- **After:** `RetrievalBackendManager` lazy-builds via `build_retrieval_backend`, tracks `effective_backend_name()` = `normalize_rag_backend(config.rag_backend)` (placeholder for future DB-backed override). On each `get_retrieval()`, for **FAISS only**, compares `faiss_disk_fingerprint(index_dir)` to the fingerprint captured at last build; if changed, rebuilds backend and logs `faiss_reload_done` (stale message throttled ~30s). **Chroma / Weaviate:** no per-request full reload; only rebuild when effective backend name changes.
- **`RagQueryService`:** accepts `RetrievalBackendManager` or plain `RetrievalBackend`; resolves active backend through `get_retrieval()` (scripts unchanged can still pass a concrete backend).
- **Imports:** `runtime_manager` avoids top-level `ChromaRagStore` and `build_openai_embeddings` so importing the manager does not require `chromadb` / `langchain_openai` until a code path needs them.

---

## Stale FAISS fix

- **Fingerprint:** `(mtime_ns manifest, mtime_ns chunks.json, mtime_ns vectors.faiss)` via `faiss_disk_fingerprint`.
- **Reload:** Only when `effective_backend_name() == "faiss"` and fingerprint differs from `_faiss_fp` after initial build.
- **Logging:** Throttled `faiss_disk_stale_detected` + one line `faiss_reload_done` to avoid log spam.

---

## Weaviate schema strategy

- **Class name:** `AppConfig.weaviate_class_name` (default `AssistantFlowChunk`).
- **Vectorizer:** `Configure.Vectorizer.none()` — BYOV, same OpenAI embeddings as Chroma/FAISS.
- **Properties:** `text`, `chunk_id`, `document_id`, `document_version_id`, `source`, `chunk_index`, `total_chunks`; L2 vector index.
- **Operational ops:** `reset_for_full_reindex`, `delete_vectors_for_document_before_reindex` (Weaviate `Filter.any_of` when both PG id and source filename), `add_documents` via batch API, `search` with `near_vector` + security filter path consistent with other backends.
- **Smoke class:** `scripts/test_weaviate_operational_indexing_smoke.py` uses `WEAVIATE_SMOKE_CLASS_NAME` (default `AssistantFlowWeaviateSmoke`) so production class is not wiped during tests.

---

## Testing

- `python scripts/test_retrieval_backend_factory.py` — normalize, chroma/faiss/weaviate `ValueError` paths, unknown backend message lists weaviate; optional FAISS empty index + manager reload when `faiss`, `numpy`, `langchain_openai` available; `RAG_BACKEND` assertion uses `os.environ["RAG_BACKEND"]=""` so workspace `.env` does not override.
- `python scripts/test_weaviate_operational_indexing_smoke.py` — full flow when `OPENAI_API_KEY` and Weaviate reachable; otherwise **SKIP exit 0**.
- `python scripts/test_retrieval_stabilization_smoke.py` — when `RAG_BACKEND=weaviate` and deps OK, seeds stabilization class with one `Document` then validates metadata contract.

**Note:** Local run without `faiss-cpu` / `langchain_openai` skips subsets; Docker image with `requirements.txt` is the reference environment.

---

## Limitations (explicit non-goals this phase)

- No Admin UI backend switch; no `platform_settings` migration; effective backend remains **env-only**.
- No distributed locking, async reindex queues, HA Weaviate cluster, auto-migration between backends.
- `RagQueryService` diagnostics field name remains `chroma_collection` for API compatibility; value reflects active backend label via `_diagnostics_collection_label()`.

---

## Next steps toward Admin UI backend switch

1. Persist desired backend (and optional per-tenant override) in PostgreSQL; `RetrievalBackendManager.effective_backend_name()` reads DB with env fallback.
2. Admin API + UI to write that setting; post-change `manager.refresh(reason="admin_backend_switch")`.
3. Optional: expose `snapshot_health_active()` on a diagnostics endpoint for UI badges.

---

## Git

Per request: **no commit** in this session. Review `git status` before committing (ignore unrelated untracked `storage/` if local only).
