# Session: Retrieval Settings layout + Weaviate schema fix (P6.11)

**Date:** 2026-05-12  
**Scope:** Admin UI Retrieval Settings compact two-column layout; Weaviate collection creation compatible with `weaviate-client` 4.x; API cache snapshot includes `CACHE_DB_PATH`.  
**Commit:** none (manual verification pending).

## Changed files

| File | Change |
|------|--------|
| `services/retrieval/weaviate_backend.py` | Replace invalid `Configure.VectorIndex.distance(...)` with `Configure.VectorIndex.hnsw()` (no explicit metric): `VectorIndex.distance` removed in 4.x; `VectorDistances.L2` removed in **4.15.x** (use `L2_SQUARED` / `COSINE` if a metric must be pinned). |
| `services/admin_service.py` | Add `cache_db_path` to `cache` object in `_retrieval_settings_public_snapshot()`. |
| `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx` | Two-column rows (active + health; runtime + indexing); cache row with notes + `CACHE_DB_PATH`; collapsible `<details>` for paths. |
| `frontend/admin-ui/src/styles/globals.css` | Grid/panel stretch, compact typography, details block, responsive single column, tighter table cells. |

## Layout changes

- **Row 1:** CSS grid `retrieval-settings__grid2` — left **Active backend**, right **Backend health matrix**; panels stretch to equal row height where content allows.
- **Row 2:** Same grid — **Runtime tuning / RAG query** | **Indexing tuning / chunking**; shorter card descriptions.
- **Row 3:** Full-width **Cache** `SectionCard`: fields `ENABLE_RETRIEVAL_CACHE`, `ENABLE_ANSWER_CACHE`, TTLs, `RAG_RETRIEVAL_GENERATION`, `CACHE_DB_PATH`; bullet copy for planned editable caches, infra-only `CACHE_DB_PATH`, generation bump hint.
- **Row 4:** Native `<details>` **System paths & connectivity**, **collapsed by default**; ordered list: Chroma, RAG dirs, FAISS, Weaviate host / **WEAVIATE_HTTP_PORT** (app uses `WEAVIATE_HTTP_PORT`, not a separate `WEAVIATE_PORT` env), `WEAVIATE_URL`, `CACHE_DB_PATH`. `WEAVIATE_GRPC_PORT` omitted from this list to match the requested env set (still available in API `paths` if needed later).

## Root cause: Weaviate health `AttributeError`

Health matrix showed:

`AttributeError: type object '_VectorIndex' has no attribute 'distance'`

**Cause (two layers):**

1. `Configure.VectorIndex.distance(...)` does not exist — v4 uses `hnsw()`, `flat()`, `dynamic()`, `none()`.
2. After switching to `hnsw(distance_metric=VectorDistances.L2)`, **4.15.4** raised `VectorDistances` has no attribute `L2` (enum now includes e.g. `COSINE`, `L2_SQUARED`, `DOT`, … — no plain `L2`).

## Detected weaviate-client version

- **portfolio-test stack (this session):** `4.15.4` in both `portfolio-test-admin-api-1` and `portfolio-test-assistant-flow-1`.
- **Declared in repo:** `requirements.txt` → `weaviate-client>=4.11.0,<4.16.0`.

## Fix strategy

- Keep **BYOV**: `vectorizer_config=Configure.Vectorizer.none()`.
- Use **HNSW** without explicit distance: `vector_index_config=Configure.VectorIndex.hnsw()` so Weaviate / client defaults apply and enum churn (`L2` removal) is avoided.
- **Idempotency:** unchanged — `collections.exists` short-circuit before `create`.
- **No** `weaviate-client` pin change unless a different incompatibility appears after smoke.

## Tests / verification (recommended)

1. **Version:**  
   `docker exec portfolio-test-admin-api-1 python -c "import weaviate; print(weaviate.__version__)"`  
   `docker exec portfolio-test-assistant-flow-1 python -c "import weaviate; print(weaviate.__version__)"`

2. **Rebuild & overview:**  
   `docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --force-recreate admin-api assistant-flow`  
   `curl -sS http://localhost:8600/api/retrieval/overview | jq .`  
   Expect: `weaviate` row no `AttributeError` on schema; empty index → `ok` may be true with `collection_count` 0 and readiness “empty index”, not a stack trace in `detail`.

3. **Smoke:**  
   `docker exec portfolio-test-assistant-flow-1 python scripts/test_weaviate_operational_indexing_smoke.py`  
   **This session:** `OK: test_weaviate_operational_indexing_smoke` after rebuild.

4. **Overview snippet (this session):**  
   `weaviate` row: `"ok": true`, `"collection_count": 0`, `"detail": "class=AssistantFlowChunk; ready count=0"` (empty index, no exception).

## Remaining limitations

- Collapsible paths omit `WEAVIATE_GRPC_PORT` (not in the user’s row-4 env list); gRPC remains in backend config for clients that connect via gRPC.
- Env name **WEAVIATE_PORT** is not used in `AppConfig`; UI labels **WEAVIATE_HTTP_PORT** to match `.env.example`.
- `CACHE_DB_PATH` appears both in Cache (row 3) and under System paths (row 4) intentionally: operational vs full connectivity dump.
