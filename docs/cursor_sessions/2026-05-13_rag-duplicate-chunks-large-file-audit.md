# Engineering log: RAG duplicate chunks (large file) — audit & retrieval dedupe (2026-05-13)

## 1. Root cause

**Primary (runtime):** the vector index can contain **multiple objects with the same normalized `page_content`** (e.g. repeated reindex without a clean wipe, or overlapping writes). Chroma / Weaviate / FAISS then return **top_k near-duplicate rows** with **different internal IDs**.  

Additionally, `apply_retrieval_metadata_contract` assigns **`chunk_id = "{backend}-synthetic-rank-{n}"`** when the backend does not supply a stable id — those synthetic ids are **unique per hit**, so any dedupe keyed only on `chunk_id` would **not** collapse true duplicate bodies.

**Secondary (operator workflow):** `scripts/rag_smoke_test.py` documents that indexing **without** `--reindex` **adds** vectors on top of an existing collection → duplicate vectors / inflated counts.

**PostgreSQL `document_chunks`:** schema defines `UNIQUE (document_version_id, chunk_index)` and `UNIQUE (chroma_collection, chroma_id)` — **duplicate rows for the same active version are not expected** if migrations are applied. Duplicates in **UI** were therefore attributed mainly to **retrieval result shape**, not to `extractChunks` doubling rows.

## 2. Where duplicates appeared

| Layer | Finding |
|-------|---------|
| **Chunking** (`SmartChunker`) | Overlap creates *similar* adjacent chunks, not five *identical* full bodies; not the main driver for «5 одинаковых». |
| **Indexer** (`admin_knowledge_indexer`) | Calls `delete_vectors_for_document_before_reindex` before `add_documents`; idempotent when delete matches stored metadata. Legacy/orphan vectors remain possible if metadata mismatched historical rows. |
| **Vector backends** | Can hold multiple objects with same text and different ids. |
| **RAG path** | `_retrieve_raw` returned backend hits **as-is** → diagnostics / LLM context saw duplicates. |
| **Admin UI** | Rendered one card per `retrieved_chunks[]` entry — correct; problem was upstream payload. |

## 3. What was fixed (minimal)

1. **`services/rag_query_service.py`**  
   - After `similarity_search`, apply **`_dedupe_retrieval_raw_results`** before distance filter, diagnostics, and LLM context.  
   - Dedupe key: real **`chunk_id`** / **`chroma_id`** / **`vector_id`** / **`uuid`** when not synthetic; else **`(source, chunk_index)`**; else **`texthash:{source}:{sha256(norm(text))[:16]}`**.  
   - Telemetry merged into the same `cache_probe` dict consumed by `_routing_identity_for_logs`.

2. **`services/rag_types.py`**  
   - `RagRetrievedChunkDiagnostics`: optional short **`text_fp`** (normalized text fingerprint) in `to_log_dict` for audits.  
   - `RagRequestDiagnostics`: **`retrieved_duplicate_count`**, **`retrieval_dedupe_applied`**, **`retrieval_vector_hits_raw`** (+ `to_log_details` + stdout diagnostics).

3. **`admin_api/deps.py`**  
   - Preserve new diagnostic keys in `_PRESERVED_DETAIL_KEYS`; pass **`text_fp`** through slim `retrieved_chunks` rows.

4. **`frontend/admin-ui/src/pages/RagPage.tsx`**  
   - Compact note under «Найденные чанки» when **`retrieval_dedupe_applied === true`** (duplicate hits removed before context).

**Not done (by design / scope):** semantic chunking, reranking, hybrid changes, global data migration, automatic destructive Weaviate/Chroma cleanup. If operators still see high collection counts after historical double-indexing, they may run a **manual** full reindex / targeted delete (see operator section).

## 4. Diagnostics / scripts added

| Artifact | Role |
|----------|------|
| `scripts/test_rag_duplicate_chunks_audit.py` | Optional **PostgreSQL** checks (duplicate `(version, chunk_index)`, duplicate `chroma_id`, identical previews on active versions), **last `rag_answer_done`** chunk fingerprint scan, **live vector search** duplicate normalized text (uses active `RAG_BACKEND` via `build_retrieval_backend`). Exit **1** if any check reports duplicates. |
| `text_fp` on `retrieved_chunks[]` | Short hash for log/script comparison without logging full text. |

## 5. Manual cleanup / reindex (if needed)

If duplicates were caused by **historical additive indexing** (no targeted delete):

- Full clean rebuild: use existing admin / smoke flows that call **`reset_for_full_reindex`** for the active backend, then reindex documents (see `scripts/rag_smoke_test.py --reindex` pattern for local Chroma).  
- **Do not** run destructive resets automatically from this patch.

## 6. Smoke tests run (this workspace)

```text
python3 -m py_compile services/rag_query_service.py services/rag_types.py admin_api/deps.py scripts/test_rag_duplicate_chunks_audit.py
cd frontend/admin-ui && npm run build
python3 scripts/test_rag_duplicate_chunks_audit.py   # (skips PG/vector without env; exit 0)
```

Live portfolio compose + Telegram query **not** run here.

## Operator commands / next verification commands

Canonical stack:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

**Audit script (inside app container):**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_rag_duplicate_chunks_audit.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_rag_duplicate_chunks_audit.py --query "Что можете сказать про LLM?"
docker exec portfolio-test-assistant-flow-1 python scripts/test_rag_duplicate_chunks_audit.py --source-substr it_ai_glossary_large
```

**Regression (optional):**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_rag_regression.py
```

**UI:** run the same RAG question as before; expect **at most one card per unique normalized chunk text** (or fewer than 5 if only one unique hit), and optional dedupe note when duplicates were removed at retrieval.
