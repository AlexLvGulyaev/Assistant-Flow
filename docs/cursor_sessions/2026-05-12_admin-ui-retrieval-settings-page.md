# Session: P6.11 — Admin UI Retrieval Settings page

**Date:** 2026-05-12  
**Goal:** React Admin UI page for retrieval backend control (DB-backed active backend), health matrix, read-only tuning/paths/cache; API client for existing `GET/PUT /api/retrieval/*`.

---

## Changed files

| Area | Path |
|------|------|
| Admin API data | `services/admin_service.py` — `get_retrieval_overview()` adds `database_configured`, `runtime_tuning`, `indexing_tuning`, `cache`, `paths` snapshots from `AppConfig` + `RAG_RETRIEVAL_GENERATION` env |
| API client | `frontend/admin-ui/src/api/client.ts` — `fetchRetrievalOverview`, `setActiveRetrievalBackend`, TS interfaces |
| Page | `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx` (new) |
| Routing | `frontend/admin-ui/src/App.tsx`, `frontend/admin-ui/src/navigation/routes.ts` — `/retrieval`, sidebar label **Retrieval Settings** |
| Styles | `frontend/admin-ui/src/styles/globals.css` — `.retrieval-settings__*` compact console block |

---

## UI structure

1. **Header** — title, lead, `OperationalRefreshButton` (reload overview).
2. **Alerts** — degraded (Postgres read failure), inline API error, post-switch **warnings** from PUT response, **reindex recommended** when active health not ok or `collection_count === 0` (link to `/documents`).
3. **Active backend** — effective / env default / DB active / `DATABASE_URL` configured; `<select>` + **Apply switch** (disabled if no DB URL, while switching, or target equals current effective); overview-level warnings list.
4. **Health matrix** — table: backend, OK, collection count, readiness badge (`ready` / `empty index` / `not ready`), detail column; active row highlight.
5. **Runtime tuning** — read-only inputs for RAG_TOP_K, RAG_MAX_DISTANCE, RAG_ANSWER_MAX_TOKENS, timeouts + `planned_note` from API.
6. **Indexing tuning** — chunk size/overlap + yellow reindex warning callout.
7. **Cache** — booleans, TTLs, `RAG_RETRIEVAL_GENERATION` + hint text.
8. **Paths** — Chroma / RAG dirs / FAISS / Weaviate / cache DB (no secrets).

**UX:** No confirmation modal; warnings visible; no silent fallback messaging in copy; compact sections via `SectionCard` + table, not KPI tiles.

---

## API usage

- `GET ${VITE_ADMIN_API_BASE_URL}/api/retrieval/overview` — extended payload includes tuning/path blocks for one round-trip.
- `PUT /api/retrieval/active-backend` — `{ "backend": "chroma"|"faiss"|"weaviate" }`; FastAPI `detail` parsed on error.

---

## Manual test checklist

1. `npm run build` in `frontend/admin-ui` (passes).
2. Rebuild admin-ui container / static serve with API `VITE_ADMIN_API_BASE_URL` pointing at admin-api.
3. Open **Retrieval Settings** in sidebar — overview loads.
4. Switch backends with Postgres configured — effective updates; warnings if target unhealthy.
5. Documents page full reindex after switch as needed; Telegram RAG smoke (separate process).

---

## Limitations

- Tuning/chunk/cache fields are **read-only** (no `PUT` yet); next step: DB-backed `platform_settings` keys + API.
- Health matrix depends on Admin API process env (embeddings for non-Chroma probes).
- `replace_all` in `globals.css` normalized `var(--muted)` → `var(--text-muted)` where used in new block (project uses `--text-muted` in `:root`).

---

## Next step

Editable retrieval tuning via `platform_settings` + dedicated `PUT` routes; invalidate `RetrievalBackendManager` / caches on change.
