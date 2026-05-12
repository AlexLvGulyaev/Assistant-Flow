# Session: multi-backend Admin UI consistency + project state (2026-05-12)

## Scope

High-level operational consistency for multi-backend retrieval in Admin UI (no new heavy dashboards, no duplication of Retrieval Settings matrix).

## Changed files

| Area | Path |
|------|------|
| RAG diagnostics types | `services/rag_types.py` |
| RAG diagnostics emission | `services/rag_query_service.py` |
| Admin service compact snapshot | `services/admin_service.py` |
| Overview API | `admin_api/routes/overview.py`, `admin_api/schemas/common.py` |
| Documents API | `admin_api/routes/documents.py` |
| Log slimming (chunk backend fields) | `admin_api/deps.py` |
| Admin UI API types | `frontend/admin-ui/src/api/client.ts` |
| Overview page | `frontend/admin-ui/src/pages/OverviewPage.tsx` |
| Documents page | `frontend/admin-ui/src/pages/DocumentsPage.tsx` |
| RAG page | `frontend/admin-ui/src/pages/RagPage.tsx` |
| Shared label util | `frontend/admin-ui/src/utils/operationalLabels.ts` |
| Project narrative | `PROJECT_STATE.md` (append-only §46) |

## Overview redesign

- Runtime column **Chroma** replaced with **Retrieval (&lt;active backend&gt;)** driven by `GET /api/overview` → `retrieval` (from `get_retrieval_platform_compact()`), not a hardcoded Chroma row.
- **Latency summary** omits Chroma latency when `retrieval` is present (uses PostgreSQL + RAG).
- **База знаний** card replaced with **Retrieval platform**: active backend + readiness line, compact monospace line for all probed backends, then documents count, **chunks = active vector index** (`collection_chunk_count`), sync, last indexing, largest doc.
- Removed **«Чанков Chroma»** row; warnings use retrieval health when available (fallback to legacy Chroma health warning if `retrieval` absent).

## Retrieval platform panel (Overview)

- Data: `OverviewResponse.retrieval` — `effective_backend`, `active_readiness`, `active_ok`, `active_collection_count`, `backends_compact`, `reindex_recommended`.

## Documents / RAG updates

- **Documents**: `retrieval_operational` on `GET /api/documents` — compact strip under header (active backend, readiness, chunk count, copy that upload/reindex target active backend, compact reindex hint).
- **RAG**: parallel `fetchOverview()` for live platform strip; session **Retrieval** panel shows logged `active_backend`, `retrieval_readiness`, `active_collection_count`; chunks show **Backend / Источник / Score**; modal includes Backend.

## Diagnostics contract (backward compatible)

- `RagRequestDiagnostics.to_log_details` may include: `active_backend`, `retrieval_backend`, `active_collection_count`, `retrieval_readiness` (plus existing `chroma_collection`).
- Each `retrieved_chunks[]` item may include `retrieval_backend`, `source_backend` (UI falls back to session-level `active_backend` when missing).
- `_slim_details_for_payload` preserves these keys on chunks when present.

## PROJECT_STATE

- See **§46** (append-only) for architecture evolution, operational rules, P6.9–P6.12 maturity note.

## Manual verification checklist

- [ ] Overview no longer reads as Chroma-only; Runtime shows **Retrieval (…)**.
- [ ] Retrieval platform card: active backend line, compact backend line, active-index chunk count, warnings when empty/unhealthy.
- [ ] Documents: operational strip matches active backend; updates after **Refresh** post backend switch in Retrieval Settings.
- [ ] RAG: top strip matches current overview retrieval; session panel shows backend readiness + collection count when logged.
- [ ] Retrieved chunks show **Backend**; old logs without per-chunk backend still display via session `active_backend`.
- [ ] Switching Chroma / FAISS / Weaviate reflects in Overview + Documents + RAG strip after refresh.
- [ ] Retrieval Settings page unchanged functionally.
- [ ] No **Failed to fetch** on Overview, Documents, RAG, Retrieval overview.

## Git

No commit in this session (per operator request until manual sign-off).
