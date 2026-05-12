# Session: multi-backend UI visual + diagnostics polish (2026-05-12)

## Goal

Visual consistency and diagnostics correctness only — no architecture or API contract changes beyond what is required for correct backend labels in logs/UI.

## Changed files

| Area | Path |
|------|------|
| Chunk diagnostics (always emit when set) | `services/rag_types.py` |
| Log slimming: parent `active_backend` on chunks | `admin_api/deps.py` (already present; verified) |
| Status badge tokens | `frontend/admin-ui/src/components/StatusBadge.tsx` |
| Readiness → badge helper | `frontend/admin-ui/src/utils/operationalLabels.ts` |
| Overview Retrieval platform | `frontend/admin-ui/src/pages/OverviewPage.tsx` |
| Documents strip + chunk labels | `frontend/admin-ui/src/pages/DocumentsPage.tsx` |
| RAG strip, chunk fallback, modal | `frontend/admin-ui/src/pages/RagPage.tsx` |
| Styles | `frontend/admin-ui/src/styles/globals.css` |

**Note:** `PROJECT_STATE.md` was not modified (polish-only).

## Visual improvements

- **Documents:** `docs-retrieval-context` — uppercase backend name, `StatusBadge` for readiness (`ready` / `empty` / `down`), secondary chunk count, tinted panel + left accent.
- **RAG:** `rag-retrieval-context` — same pattern, green accent line for “live” subsystem feel.
- **Overview Retrieval platform:** replaced pale monospace blob with **matrix**: dominant **Active backend** block + per-backend rows (name | badge | count), active row highlighted (`overview-retrieval-matrix__row--active`).
- **RAG chunk cards:** backend name in accent color (`rag-chunk-card__backend-name`).

## Diagnostics / fallback logic

1. **`RagRetrievedChunkDiagnostics.to_log_dict`:** emits `retrieval_backend` / `source_backend` only when at least one is set (avoids polluting legacy rows with `"unknown"`).
2. **`_slim_details_for_payload`:** injects `retrieval_backend` / `source_backend` on slim chunks from parent `active_backend` or `retrieval_backend` when the chunk object omits them.
3. **`extractChunks` (RagPage):** resolves `diagBackend` from each diagnostics dict (`active_backend`, `retrieval_backend`) before session fallback.
4. **`displayChunkBackendTitle` / `resolvedChunkBackendId`:** order = chunk → session `activeBackend` → `retrievalPlatform.effective_backend` — **no `Backend: —`** when platform snapshot has the backend.
5. **Chunk modal:** precomputed `backendTitle` at open time using the same resolver.

## Backend consistency (Documents)

- Chunk list header: **vector store label** from `retrieval_operational.effective_backend` ?? `global_index_sync.active_retrieval_backend`, plus generic **id** (still from `chroma_id` / metadata `id` field — API field names unchanged); removed **“Chroma: …”** wording.

## Manual verification checklist

- [ ] Active backend immediately visible on **Overview** (matrix + active block), **Documents** (context strip), **RAG** (top strip).
- [ ] Readiness badges: **READY** green, **EMPTY** warn, **DOWN** error.
- [ ] RAG chunk **Backend** matches active retrieval (Weaviate/FAISS/Chroma) — not `—` when overview loaded or session has `active_backend`.
- [ ] **Documents** chunk lines never imply Chroma-only when Weaviate is active.
- [ ] Retrieval platform matrix aligned and readable.
- [ ] No **Failed to fetch** on Overview / Documents / RAG.

## Git

No commit (awaiting operator sign-off).
