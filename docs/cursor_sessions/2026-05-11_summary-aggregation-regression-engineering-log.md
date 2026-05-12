# Summary aggregation regression (2026-05-11)

## Symptom

Admin Summary (`/api/summary`, React `SummaryPage`) showed **route / reconciliation metrics that did not match** `processing_logs` (e.g. document-related traffic under-counted; `routes.documents` stuck at 0; `other_unknown` inflated). Raw logs in PostgreSQL remained correct.

## Root cause

1. **`count_routes_since` (PostgreSQL `LIKE`)**  
   The document branch used `stage LIKE 'admin_document%'`. In SQL `LIKE`, underscore (`_`) is a **single-character wildcard**, not a literal underscore. The pattern therefore does **not** reliably match real stage names such as `admin_document_uploaded_raw`, `admin_document_reindex_started`, etc. Those rows fell through to `ELSE NULL`, so many document/admin executions never received the `document` route bucket. With `DISTINCT ON (execution_id) … WHERE route_bucket IS NOT NULL`, those sessions disappeared from per-route counts and inflated **`other_unknown`** vs **`sessions_total`**.

2. **`SummaryRoutes` (Pydantic) vs payload**  
   `get_summary_payload` already returned `routes.documents`, but `admin_api/schemas/summary.SummaryRoutes` had no `documents` field. Serialized `/api/summary` responses omitted `documents` from the `routes` object (extra field dropped on validation), so the UI could not show the document bucket from the wire format even when the DB aggregation was correct.

## Exact broken condition

- Any `processing_logs` row whose classification depended on **`stage LIKE 'admin_document%'`** (admin document / reindex stages) **failed** to match the intended literal prefix, so `route_bucket` stayed `NULL` unless another row in the same `execution_id` window matched `document_*` regex or non-document branches.

## Payload before / after (illustrative)

**Before (example):** `routes.documents` missing from JSON; document sessions counted only in `other_unknown`.

```json
{
  "routes": {
    "text": 0,
    "rag": 0,
    "images": 0,
    "audio_voice": 0,
    "other_unknown": 5
  }
}
```

**After:** `routes.documents` present; admin/document stages contribute to `document` bucket; `other_unknown` reconciles.

```json
{
  "routes": {
    "text": 0,
    "rag": 0,
    "images": 0,
    "audio_voice": 0,
    "documents": 3,
    "other_unknown": 2
  }
}
```

(Numbers depend on the rolling window and data.)

## Changed files

- `repositories/processing_logs_repository.py` — `count_routes_since`: replace broken `LIKE` with `stage ~ '^admin_document'`; align document bucket with `details.route` / `downstream_route` / `mode` when they signal document (same intent as `infer_modality_route` in `admin_api/deps.py`).
- `admin_api/schemas/summary.py` — `SummaryRoutes.documents: int = 0` so OpenAPI and JSON responses include the field.

## Verification checklist

1. Insert or pick rows with `stage` in `admin_document_uploaded_raw`, `admin_document_reindex_started`, etc., inside the window; run `count_routes_since` / open Summary — **`documents`** (or reconciled totals) should reflect distinct `execution_id`s.
2. Confirm `GET /api/summary` JSON includes **`routes.documents`** (number, not omitted).
3. `other_unknown` = `sessions.unique_execution_ids` − (text + rag + images + audio_voice + documents) for the same window.
4. Logs page modality filter for document still matches writers (no change to preprocessing/retrieval/DB schema).
5. Non-document traffic (text/RAG/image/voice) unchanged vs previous behavior.

## Out of scope (per request)

- No changes to preprocessing, retrieval, or DB schema.
- No redesign of summary semantics beyond fixing classification and response shape.
