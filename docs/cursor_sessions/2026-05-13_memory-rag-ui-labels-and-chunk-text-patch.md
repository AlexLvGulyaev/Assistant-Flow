# Engineering log: Memory/RAG UI labels, route/summary classification, RAG chunk full text (2026-05-13)

Targeted patch after Memory v1.2: operator-facing labels, session route bucketing for Summary, RAG admin UI chunk full-text regression when `RAG_TOP_K=5` and responses hit JSON slimming.

---

## 1. Root causes (by problem area)

### A. `/clear` / `/reset` and other `memory_*` stages → «Нестандартный этап»

- **Cause:** `stageToActionRu` falls back to «Нестандартный этап» when the normalized stage is absent from `EVENT_TYPE_RU`. **`memory_session_cleared`** and **`memory_append_done`** were not in that map (unlike `memory_load_*` / `memory_meta_*`, which were already present).
- **Secondary:** RAG session grouping on **RagPage** used `isRagEvent`, which only matched core `rag_*` routes/modes. Rows such as **`memory_meta_*`** or **`memory_*` with `details.mode === "rag"`** were excluded from the RAG timeline even when labels existed.

### B. Summary `routes.other_unknown` vs memory / `memory_meta`

- **Cause:** `count_routes_since` in `repositories/processing_logs_repository.py` mapped `rag` when `details.route` was `rag` / `rag_response` or `details.mode = rag`, but **did not treat `details.route = memory_meta` as RAG**. Meta-only sessions therefore had **no `route_bucket` on terminal rows**, fell into `ELSE NULL`, and inflated **`other_unknown`** vs `sessions_total`.

### C. RAG chunk preview and full-text modal both truncated (`RAG_TOP_K=5`)

- **Cause (data):** `RagRetrievedChunkDiagnostics` only stored **`text_preview`** (capped in `_text_preview_for_logs`). The admin UI modal used the same field as the preview source.
- **Cause (API):** `truncate_details` (default **4000** JSON chars) forced **`_slim_details_for_payload`**, which reduced each chunk’s `text_preview` to **96** characters — so even a «full text» control could not recover the original chunk body from the API payload.

---

## 2. What was fixed

| Area | Change |
|------|--------|
| **Labels** | `EVENT_TYPE_RU`: `memory_session_cleared`, `memory_append_done`; `ROUTE_ALIASES`: `memory_meta` → `rag`. |
| **RAG timeline inclusion** | `isRagEvent` extended for `memory_meta` routes/stages, `memory_*` coupled to `mode===rag`, and **`memory_load_started` / `memory_load_done`** (emitted only from the Telegram RAG history loader). |
| **Processing log details** | `_memory_details` now optionally records **`route`** / **`mode`** so `infer_modality_route` and SQL routing see the same modality as the chat path (`rag` vs `text` for rotate/persist). |
| **Summary SQL** | RAG bucket includes **`details.route IN (..., 'memory_meta')`**. |
| **Chunk telemetry** | `RagRetrievedChunkDiagnostics`: short **`text_preview`** (~card) + bounded **`chunk_text_full`** in `to_log_dict`; slimming keeps **`chunk_text_full`** (capped per chunk); **`log_row_to_entry`** uses **64KiB** truncation budget for **`rag_answer_done`** so slim payloads usually fit without dropping chunk arrays. |
| **Admin UI** | `extractChunks` uses **`chunk_text_full` / `text_full` / `page_content`** for modal **`fullText`**, and **`text_preview`** only for short preview when present. |
| **Memory observability API** | `_ALLOWED_MEMORY_DETAIL_KEYS` extended with **`route`**, **`mode`** so slim responses match new fields. |
| **Evaluation** | `_contexts_from_result` prefers **`chunk_text_full`** over preview when building contexts. |

---

## 3. Stage labels / classification added

**`frontend/admin-ui/src/utils/operationalLabels.ts`**

- `memory_append_done` → «Реплики диалога сохранены в память»
- `memory_session_cleared` → «Сессия диалога сброшена (память очищена / ротация)»
- `ROUTE_ALIASES.memory_meta` → `rag` (Summary / route chips that use `normalizeRouteKey`)

**Already present (unchanged):** `memory_load_started`, `memory_load_done`, `memory_error`, `memory_meta_*`, etc.

**Backend `details` (not labels, but classification):** `services/memory/conversation_memory_service.py` — `route` + `mode` on memory lifecycle rows (`load` → `rag`; rotate → `new_session_mode`; persist → `rag`/`text` from session mode).

**`repositories/processing_logs_repository.py`:** `memory_meta` counted under the **rag** session bucket.

---

## 4. Full chunk text contract

- **Persisted in DB (`processing_logs.details.retrieved_chunks[]`):** `text_preview` (short), optional **`chunk_text_full`** (bounded, same redaction rules as preview).
- **API list/slim row:** `text_preview` (≤96 chars in slim), **`chunk_text_full`** (≤10 000 chars per chunk in slim).
- **UI:** Preview from `text_preview`; modal from **`chunk_text_full`** first, then fallbacks (`text_full`, `page_content`, then preview).

---

## 5. Verification performed in this workspace

| Check | Result |
|-------|--------|
| `cd frontend/admin-ui && npm run build` | **Passed** (`tsc -b && vite build`). |
| `python3 -m py_compile` on touched Python modules | **Passed**. |
| Live Telegram / Docker portfolio contour | **Not run** in this environment (see operator commands below). |

**Note:** `git status` may show **large unrelated local edits** under `interfaces/telegram_bot.py` (Memory v1.2 meta path, etc.). Those edits are **not part of this patch’s file list**; this log only documents the paths listed in section 2.

---

## 6. Files touched (this patch)

- `admin_api/deps.py`
- `frontend/admin-ui/src/pages/RagPage.tsx`
- `frontend/admin-ui/src/utils/operationalLabels.ts`
- `repositories/processing_logs_repository.py`
- `services/evaluation/rag_evaluation_service.py`
- `services/memory/conversation_memory_service.py`
- `services/memory_observability_service.py`
- `services/rag_query_service.py`
- `services/rag_types.py`

---

## Operator commands / next verification commands

Stack (canonical contour):

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

**1. Telegram `/clear`**

- In Admin **Logs**, find `memory_session_cleared`: expect RU label, not «Нестандартный этап»; `modality_route` should follow `details.mode` (`rag` vs `text` for `/reset`).

**2. RAG multi-turn + indexing question**

- Send the two-line RAG probe from the task brief; on **RAG** page, timeline should list **`memory_load_*` / `memory_append_done`** with labels and without treating rows as unknown stages.

**3. Memory meta**

- «О чем был мой предыдущий вопрос?» — `memory_meta_*` labels; route bucket **rag** in Summary after SQL change.

**4. Summary**

- Open Summary: **`routes.other_unknown`** should not grow solely due to **`memory_meta`**-only sessions.

**5. `RAG_TOP_K=5`**

- After a RAG answer, open chunk **full text** modal: body should match **full** logged chunk text (scroll inside modal if long), not the 96-char slim preview.

**6. Frontend build (host)**

```bash
cd frontend/admin-ui && npm run build
```

**7. Backend compile (inside container)**

```bash
docker exec portfolio-test-assistant-flow-1 python -m py_compile services/rag_query_service.py
```

Optional one-off script inside the same container pattern:

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_memory_v1_2_meta_intent_routing_smoke.py
```
