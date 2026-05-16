# Session: Evaluation / RAGAS Console — Admin UI P2-lite

**Date:** 2026-05-15 (`date +%F`)

**Commit:** not performed (per request).

---

## Full prompt (verbatim summary)

Operator UX for RAGAS must move from CLI-only to **FastAPI + React operational console**. Implement P2-lite Evaluation / RAGAS page: list recent RAG turns from `processing_logs`, multi-select import into `evaluation_run`, run RAGAS from UI, view per-item metrics, lightweight ground_truth edit. Do not remove CLI; no hot-path RAGAS; no scheduled jobs / BI dashboard.

---

## Why dataset-only / CLI was insufficient

- AF is a **conversational operational platform**; quality work happens on **real Telegram/dialog traces**, not only benchmark JSON.
- Copying `execution_id` + SQL + `docker exec` scripts is a **UX regression** vs Memory/RAG/Logs consoles.
- P1/P1.1 remain as **reproducibility layer**; P2-lite adds the **primary operator workflow** in Admin UI.

## Architectural distinction

| Layer | Role |
|-------|------|
| Benchmark datasets (`ragas_baseline_ru_v1`, scripted `evaluation_run.py`) | Regressions, isolated corpus, CI |
| **Conversational import + UI** (`interactive_eval_ui`, `/evaluation`) | Real runtime traces → RAGAS without UUID hunting |

Pipeline unchanged: **usage → import → completed run → RAGAS → `evaluation_metric_fact`**.

---

## Changed files

### Backend

| Path | Role |
|------|------|
| `services/evaluation_admin_service.py` | List turns/runs, import, RAGAS, patch item |
| `admin_api/routes/evaluation.py` | Thin REST routes |
| `admin_api/schemas/evaluation.py` | Request bodies |
| `admin_api/app.py` | Register evaluation router |
| `repositories/evaluation_repository.py` | `list_runs`, `get_item`, `patch_dataset_item_metadata` |
| `services/evaluation_service.py` | `split_log_details_to_blobs()` shared with import |

### Frontend

| Path | Role |
|------|------|
| `frontend/admin-ui/src/pages/EvaluationPage.tsx` | Two-tab console (turns / runs) |
| `frontend/admin-ui/src/api/client.ts` | Evaluation API client |
| `frontend/admin-ui/src/App.tsx` | Route `/evaluation` |
| `frontend/admin-ui/src/navigation/routes.ts` | Sidebar «Evaluation» |
| `frontend/admin-ui/src/styles/globals.css` | `.evaluation-page` / `.eval-*` styles |

**Preserved:** CLI scripts (`evaluation_import_*`, `evaluation_ragas.py`), Telegram/RAG hot path.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/evaluation/rag-turns` | Recent `rag_answer_done` rows + `has_ragas_metrics` |
| GET | `/api/evaluation/rag-turns/{execution_id}` | Turn detail (query, answer, chunks, diagnostics) |
| POST | `/api/evaluation/import` | `{ execution_ids[], dataset?, run_name? }` → `run_id` |
| POST | `/api/evaluation/ragas/run` | `{ run_id }` → RAGAS summary |
| GET | `/api/evaluation/runs` | List runs |
| GET | `/api/evaluation/runs/{run_id}` | Run + items + metrics |
| GET | `/api/evaluation/runs/{run_id}/metrics` | Metrics grouped by ordinal |
| PATCH | `/api/evaluation/items/{item_id}` | `{ ground_truth?, notes?, manual_score? }` |

Default import dataset slug: **`interactive_eval_ui`**.

---

## Frontend

**Route:** `/evaluation` (sidebar: Evaluation)

**Tab A — Recent RAG turns:** filters (24h/48h/7d, fallback, RAGAS scored, search), multi-select, Import selected / Import last 5, detail card (query, answer, chunks, JSON).

**Tab B — Evaluation runs:** list runs, detail with **Run RAGAS**, run means, per-item metrics table, per-item ground_truth / manual_score editor.

Layout: `logs-console` split (420px list + detail), same pattern as Memory/RAG/Logs.

---

## Limitations (P2-lite)

- RAGAS run is **synchronous** in API request — long runs block until complete; UI shows loading on button.
- RAGAS package still **optional** in container (`pip install -r requirements-ragas.txt`).
- `context_precision` needs **ground_truth** — UI shows explicit gaps; operator can PATCH item.
- No auto-import, no realtime scoring, no cross-run compare UI.
- Turn list capped (~80–200); not full analytics warehouse.

---

## Known gaps / next phase

- Async RAGAS job + poll status (async_jobs).
- Compare two runs in UI (reuse `evaluation_compare_runs` logic).
- Link from RAG page → Evaluation with pre-selected `execution_id`.
- Auth/RBAC on evaluation endpoints.
- Streamlit admin parity (optional).

---

## Operator commands / next verification commands

### Rebuild portfolio stack

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-api admin-ui assistant-flow
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-api admin-ui assistant-flow
```

### Frontend build (host / CI)

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
```

### RAGAS deps in app container

```bash
docker exec portfolio-test-assistant-flow-1 pip install -r requirements-ragas.txt
```

### API smoke (curl)

```bash
BASE=http://localhost:8600

curl -s "$BASE/api/evaluation/rag-turns?limit=5&since_hours=24" | head -c 800
echo

# After you have execution_ids from the response:
curl -s -X POST "$BASE/api/evaluation/import" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids":["<EXECUTION_UUID>"],"dataset":"interactive_eval_ui"}'

curl -s "$BASE/api/evaluation/runs?limit=10"

curl -s -X POST "$BASE/api/evaluation/ragas/run" \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_UUID>"}'
```

### UI test steps (no SQL / no manual UUID copy for primary flow)

1. Send several RAG questions via Telegram.
2. Open Admin UI → **http://localhost:8080/evaluation** (or your host/port).
3. Tab **Recent RAG turns** — verify list, filters, select rows, **Import selected**.
4. Tab **Evaluation runs** — open created run → **Run RAGAS** (requires RAGAS installed + `OPENAI_API_KEY`).
5. Review metrics table; edit **ground_truth** on a wrong-answer item; re-run RAGAS if needed.
6. Confirm hallucination case: low faithfulness, high answer_relevancy when answer invents facts.

---

## UI standard alignment pass

**Goal:** Evaluation page matches Memory/RAG/Logs operational console (no white browser controls, no floating form layout).

### Changed frontend files (UI only)

| File | Changes |
|------|---------|
| `frontend/admin-ui/src/pages/EvaluationPage.tsx` | Left column order (filters → search → actions → meta → list); `logs-select` / `logs-search` / `logs-page-btn`; RAG turn detail: header + `modality-ops-panels` + QA blocks + full-width `rag-chunk-card` stack; runs detail: header actions + summary panels + compact collapsible ground_truth editors; auto-select first list item; right panel never empty when data exists |
| `frontend/admin-ui/src/styles/globals.css` | `.evaluation-page` scoped styles: dark inputs, detail scroll, chunk stack, compact item edit, metrics table |

**Not changed:** backend routes, import/RAGAS services, DB.

### Build verification

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
```

Expected: `tsc -b && vite build` exit 0.

### UI verification checklist

1. `/evaluation` — left column: 3 dark selects (window / fallback / RAGAS), search below, Import + Refresh row, `rows: N · selected: M`.
2. With RAG turns in list — first item auto-selected; right shows Session / Retrieval / RAGAS panels + user/assistant blocks + chunk cards.
3. Chunk cards full width of detail column; expand «Полный текст» works.
4. Evaluation runs tab — run list + detail with Run RAGAS in header; metrics table scrolls; ground_truth editors collapsed by default.
5. No white native `<select>` / `<input>` chrome.

### Git status

```bash
cd /opt/assistant-flow && git status
```

---

## UI refinement / AF console alignment pass #2

**Goal:** Shared chunk UX with `/rag`, list pagination like Logs/RAG, equal-height Session/Retrieval/RAGAS panels, subtle import checkboxes, runs tab via `logs-chip`, diagnostics JSON via `SessionJsonSnapshot`.

**Scope:** frontend only — no backend changes.

### Changed frontend files

| Path | Changes |
|------|---------|
| `frontend/admin-ui/src/components/OperationalRetrievalChunksSection.tsx` | Shared `rag-chunk-card` list + full-text modal (RAG + Evaluation) |
| `frontend/admin-ui/src/components/OperationalListPagination.tsx` | Prev/Next + «Страница X из Y» (PAGE_SIZE 10) |
| `frontend/admin-ui/src/utils/retrievalChunks.ts` | `SharedRetrievalChunk`, adapters from RAG session / eval diagnostics |
| `frontend/admin-ui/src/pages/RagPage.tsx` | Uses shared chunks section; removed duplicate modal/cards |
| `frontend/admin-ui/src/pages/EvaluationPage.tsx` | Pagination (turns + runs), shared chunks, `SessionJsonSnapshot`, `logs-chip` tabs, eval-top panels |
| `frontend/admin-ui/src/styles/globals.css` | Equal-height `.modality-ops-panels--eval-top`, subtle checkboxes, `eval-console-tabs` |

### Build verification

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
```

Expected: `tsc -b && vite build` exit 0.

### UI verification checklist

1. `/rag` — chunk cards match prior UX; «показать полный текст» opens modal; dedupe note still shows when logged.
2. `/evaluation` — tabs use dark `logs-chip` style (not separate mini-app buttons).
3. Left list — «Страница X из Y», Prev/Next, ~10 rows per page (turns and runs tabs).
4. Turn detail — Session / Retrieval / RAGAS top row similar height; chunks identical to RAG cards/modal.
5. Turn detail — collapsible «Технический снимок сессии (JSON)» (not raw «Diagnostics JSON»).
6. Import checkboxes — small, low-contrast until row hover.
7. Runs tab — Run RAGAS, metrics table, ground_truth editors unchanged functionally; layout matches AF console.
