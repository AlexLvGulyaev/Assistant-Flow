# Evaluation Layer — architectural design (Assistant Flow)

**Path:** `docs/architecture/evaluation_layer_design.md`  
**Status:** design stage · **Audience:** engineering / operations · **Scope:** foundation for retrieval evaluation, quality metrics, controlled experiments, future RAGAS integration, and operational AI diagnostics — **not** a general-purpose analytics platform.

---

## 1. Goals

1. **Unified Evaluation Layer** — one conceptual subsystem for recording *what* was evaluated, *under which conditions*, and *with what outcomes*, across manual review, scripted retrieval experiments, and (later) automated scoring.
2. **Retrieval-first** — primary stress on vector retrieval configuration (backend, `top_k`, chunking policy fingerprints) and on measurable signals already partially present in AF (latency, distances, dedupe, fallback reasons, token usage).
3. **Backend-agnostic contract** — experiments and runs reference retrieval by **stable identifiers** (`backend_id`, `collection` / index fingerprint, `retrieval_generation` / cache generation where applicable), not by concrete LangChain/Chroma classes in the schema.
4. **Non-invasive runtime** — production Telegram / API paths **must not** block on evaluation writes; evaluation **ingests** telemetry and optional replay jobs rather than wrapping every live request.
5. **Path to RAGAS** — data model and metric slots allow attaching RAGAS (or equivalent) scores per item without redesigning core tables.
6. **Operational truth** — operators can answer: “Which configuration produced these chunks, distances, and answers for this fixed query set?”

---

## 2. Non-goals

- Full **BI / warehouse** product, ad-hoc SQL exploration UI, or “dashboard for dashboards.”
- Replacing **existing** `processing_logs` / lifecycle events — the Evaluation Layer **complements** them with *curated run* and *dataset item* semantics.
- **Real-time** scoring of every production message (too costly and tightly coupled); optional *sampling* is a later phase.
- **Authoring** of large golden corpora inside Admin UI in v1 — predefined datasets may be file-backed or migration-seeded initially.
- Tight **coupling** to a single vector DB vendor API in persistence — only opaque config snapshots and result blobs.

---

## 3. Architecture (high level)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Production runtime (unchanged)               │
│  Telegram / API → RAG / retrieval → processing_logs + diagnostics│
└───────────────────────────────┬─────────────────────────────────┘
                                │ async / batch / optional hook
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Evaluation ingestion / jobs                     │
│  - Replay queries against configured retrieval                    │
│  - Or: import frozen snapshots from logs (execution_id)         │
│  - Write: evaluation_runs, evaluation_items, metric rows          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Evaluation store (PostgreSQL recommended)           │
│  datasets · evaluation_runs · evaluation_items · metric_facts     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│     Admin UI — Evaluation / Quality (phased; wireframe-level)    │
│  experiments · run compare · item drill-down · metrics summary     │
└─────────────────────────────────────────────────────────────────┘
```

**Principles**

- **Write path** for evaluation is **off the hot path**: worker process, cron, or explicit “Run experiment” API that enqueues work.
- **Read path** for UI is **read-only** against evaluation tables + optional join to `processing_logs` by `execution_id` / correlation id for deep links.
- **Versioning** — every `evaluation_run` stores an **immutable config snapshot** (JSON) and optional **links** to corpus/index generation (e.g. `RAG_RETRIEVAL_GENERATION`, manifest hash) so runs remain interpretable after reindex.

---

## 4. Entities (data model)

### 4.1 `evaluation_dataset`

Represents a **named, versioned** set of evaluation inputs (not individual questions at top level if the set is large).

| Field (conceptual) | Purpose |
|--------------------|---------|
| `dataset_id` (UUID) | PK |
| `slug` | Stable operator-facing id (`baseline_ru_v1`) |
| `version` | Integer or semver string |
| `locale` / `tags` | Filtering |
| `source` | `file` \| `seed` \| `imported_from_logs` |
| `metadata` (JSONB) | Provenance, license, owner team |

**Child:** `evaluation_dataset_item` (optional normalized table) or **embedded JSON** in v0 for small sets.

- `item_id`, `dataset_id`, `ordinal`, `query_text`, `expected_answer` (optional), `metadata` (e.g. topic tags).

**Rationale:** Separating **dataset** from **run** allows re-running the same queries under many configs (top_k, backend, chunk policy).

### 4.2 `evaluation_run`

One **experiment execution** — comparable to a CI build for retrieval.

| Field | Purpose |
|-------|---------|
| `run_id` (UUID) | PK |
| `dataset_id` + `dataset_version` | What was evaluated |
| `status` | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `started_at` / `finished_at` | Wall clock |
| `trigger` | `manual` \| `api` \| `ci` \| `scheduled` |
| `config_snapshot` (JSONB) | **Immutable**: `backend`, `top_k`, `rag_max_distance`, chunking fingerprint (`chunk_size`, `overlap`, splitter id), embedding model id, optional `retrieval_generation`, security scope |
| `correlation_notes` | Free text for operators |

**Versioning:** `config_snapshot` is the source of truth for “what this run means”; no retroactive edit. If a parameter was wrong, create a **new** run.

### 4.3 `evaluation_item`

One **(run × dataset row)** result — atomic unit for metrics and manual scores.

| Field | Purpose |
|-------|---------|
| `item_id` (UUID) | PK |
| `run_id` (FK) | Parent run |
| `dataset_item_ref` | Pointer to dataset row (id or ordinal + hash of query text) |
| `query_text` | **Denormalized copy** at run time (protects against dataset edits) |
| `status` | `ok` \| `error` \| `skipped` |
| `error` | Short machine message |

**Result payloads (JSONB, structured but flexible):**

- `retrieval_snapshot` — ordered list of chunk ids / sources / distances / `passed_filter` / duplicate flags (subset of today’s `RagRequestDiagnostics.retrieved_chunks` shape).
- `generation_snapshot` — answer text, model id, **token usage** (input/output/total), `fallback_reason` if any.
- `latency_ms` — retrieval vs LLM vs total if available.
- `execution_id` (optional) — if this item was produced by **replaying** through the live pipeline and a log row exists — deep link to `processing_logs`.

**Rationale:** Keeps the relational core small; large text and chunk bodies in JSONB (with size caps and optional external object storage later).

### 4.4 `evaluation_metric` (or wide columns on `evaluation_item`)

**Option A (normalized):** `evaluation_metric_fact(run_id, item_id, metric_key, metric_value_numeric, metric_value_json, source)` — best for sparse RAGAS dimensions later.

**Option B (denormalized on item):** fixed columns for v1 — simpler queries, harder schema migration.

**Recommendation:** **Option A** from the start for `metric_key` namespace (`avg_latency` can be run-level aggregation in materialized view or computed in API).

**Manual score:** `metric_key = manual.overall`, value in `{0, 0.5, 1}` or small JSON `{"score": 0.5, "rubric": "default_v1"}`. Alternative: **Likert 1–5** stored as 0.2 steps if operators need granularity; default rubric documented in `evaluation_dataset.metadata`.

---

## 5. Metrics model

### 5.1 Run-level aggregates (computed post-hoc or on run completion)

| Metric | Definition (initial) |
|--------|----------------------|
| `avg_tokens` | Mean total tokens per item (from generation snapshot). |
| `avg_latency_ms` | Mean wall time per item (or p50/p95 if stored as histogram later). |
| `fallback_rate` | Share of items with `fallback_reason != none`. |
| `duplicate_chunk_rate` | From retrieval snapshots: duplicates removed / raw hits (align with existing dedupe diagnostics). |
| `irrelevant_chunk_rate` | **Requires signal:** manual label per chunk or per item, or heuristic (e.g. distance > threshold); initially **manual-only** or **null** if not labeled. |
| `retrieval_count` | Mean or sum of retrieved chunks before filter. |
| `retrieved_context_size` | Mean character count of context passed to LLM. |

Store as **materialized columns** on `evaluation_run` for fast list UI, or as **run_summary JSONB** updated once at end of run — trade-off: SQL simplicity vs flexible schema. Prefer **JSONB `run_summary`** in v1 + optional generated columns later.

### 5.2 Item-level metrics

- All run-level metrics can be derived; additionally **per-item**: `manual.overall`, `manual.chunk_notes` (JSON), optional **distance stats** (min/max/mean of top-k distances).

### 5.3 Future RAGAS (namespaced keys)

Prefix: `ragas.*`

| Key | Role |
|-----|------|
| `ragas.faithfulness` | Answer grounded in context |
| `ragas.answer_relevancy` | Answer vs query |
| `ragas.context_precision` | Useful context vs noise |
| `ragas.context_recall` | Coverage of ground truth (needs labels) |

Values stored as floats 0–1 plus optional `raw` JSON for debug. **Invocation:** batch job calling RAGAS library with frozen prompts; **never** inline in user request path.

---

## 6. UI architecture (wireframe level — not implemented)

**Route:** `/evaluation` or `/quality` under Admin shell (exact path TBD with navigation team).

**Layout (reuse operational console patterns):**

- **Left:** filterable **Runs** list (dataset, backend, date, status, trigger).
- **Right (split):** **Run header** (config snapshot chips: backend, top_k, chunk fingerprint) + **Metrics summary** card (run_summary).
- **Tabs below header:**
  1. **Items** — table: query preview, manual score, latency, fallback, link “inspect”.
  2. **Compare** — select second `run_id` (same dataset version); diff columns for summary metrics and optional side-by-side item rows.
  3. **Inspect item** — drawer or sub-route: query, **retrieval-ready query** (if captured), chunk cards (reuse RAG chunk card metaphor), generation, timeline link if `execution_id` present.

**Components to reuse:** `OperationalModalityBadge`-style density, `StatusBadge`, `SessionJsonSnapshot` / JSON fold for raw `config_snapshot`, timeline patterns from Logs/Memory pages.

**Non-goal for v1:** pixel-perfect charts; start with **tables + badges + JSON**.

---

## 7. Experiment workflow

1. **Define dataset** (seed or import N queries).
2. **Create run** — operator picks:
   - `backend` (weaviate / chroma / faiss — from effective env or explicit override for eval worker only),
   - `top_k`, thresholds,
   - **chunk policy fingerprint** (must match an indexed corpus state — if mismatch, run fails fast with clear error).
3. **Execute** — job runner:
   - For each query: call internal **RagQueryService.retrieve** or **answer** in “eval mode” (no Telegram side effects) OR replay from captured `execution_id` if doing log-replay studies.
   - Persist `evaluation_item` + snapshots.
4. **Aggregate** — compute `run_summary`.
5. **Manual pass** — operator scores items (batch keyboard shortcuts later).
6. **Compare** — two runs on same `dataset_id`+version; highlight metric deltas.

**Failure modes:** index empty, backend unreachable, timeout — item `status=error`, run can still `completed` with partial success flag in `run_summary`.

---

## 8. Integration points (where data is sourced)

| Signal | Source today | Evaluation ingestion |
|--------|--------------|------------------------|
| Token usage | `RagRequestDiagnostics` / log details | Copy into `generation_snapshot` on eval replay |
| Retrieval diagnostics | `to_log_details()`, chunks, distances | `retrieval_snapshot` |
| Chunks | Same as diagnostics / Documents | Store ids + previews; optional link to `document_chunks` |
| Latency | `retrieval_latency_ms`, `llm_latency_ms`, wall | Per-item JSON |
| `fallback_reason` | diagnostics | Item + run aggregate |
| Memory routing | `memory_meta` stages / intent in logs | Optional `routing_snapshot` on item if run includes orchestration replay |
| `retrieval_ready_query` | diagnostics | Persist for drift analysis between runs |

**Ingestion modes:**

- **A. Live tap (optional, sampled):** async queue from `rag_answer_done` — high care for PII and volume.
- **B. Offline replay (preferred v1):** dedicated worker + service credentials.

---

## 9. Operational implications

- **Runbook:** failed or partial runs (empty index, backend fingerprint mismatch, timeout) must return **actionable** errors; operators correlate with `run_id` without ad-hoc SQL on production traffic tables only.
- **Ownership & retention:** datasets and runs are **versioned artifacts**; TTL / archive policy should be explicit (align with `processing_logs` retention philosophy).
- **Alerting (later phase):** optional regression signals when a scheduled run exceeds baseline `fallback_rate` or distance drift vs previous run on the same `dataset_version`.
- **Access control:** evaluation write APIs must eventually sit behind the same **Admin API** protection model as the rest of the operational shell (see `PROJECT_STATE` §47.1).
- **Cost visibility:** `run_summary` should carry **embedding / LLM usage totals** per run for capacity planning.

---

## 10. Coupling, safety, and performance

- **No** synchronous DB writes from production RAG answer path in v1.
- Eval worker uses **same** `RagQueryService` / retrieval factory as prod but may override config via **ephemeral** `AppConfig` clone or env-isolated process.
- **Rate limits** on experiment API to protect embedding quotas.
- **Large JSONB** — cap chunk text in snapshots (reuse preview limits from diagnostics); full text via link to existing document/chunk APIs if needed.

---

## 11. Foundation: current observability → Evaluation Layer

| Existing capability | Role for Evaluation |
|---------------------|---------------------|
| Chunk diagnostics (per-chunk distance, filter pass, backend) | **Ground truth** for `retrieval_snapshot`; train irrelevant-rate heuristics; compare runs. |
| Duplicate diagnostics (`retrieval_dedupe_applied`, counts) | Direct input to `duplicate_chunk_rate`. |
| `retrieval_ready_query` | Detect silent drift between “user bubble” and vector string across runs. |
| Lifecycle / `processing_logs` timeline | **Correlation** for disputes: “this item’s run matches execution X.” |
| Memory observability | When evaluating **routing**, attach which path was taken (RAG vs memory_meta). |
| Token metrics | Token vs quality scatter plots in later UI phases. |

---

## 12. Scaling considerations

- **Partitioning** — `evaluation_item` grows with `runs × queries`; partition by `started_at` month or by `run_id` hash if volume explodes.
- **Retention policy** — TTL or archive to cold storage for old runs (configurable).
- **Concurrency** — job queue (existing async job patterns in AF if present; else simple DB-backed queue table).
- **Multi-tenant** — if AF ever splits tenants, `dataset_id` and runs must carry `tenant_id`; single-tenant v1 can omit.

---

## 13. Phased implementation plan

| Phase | Deliverable |
|-------|-------------|
| **P0 — Design lock-in** | This document + `PROJECT_STATE` pointer (§47.x backlog cross-link optional). |
| **P1 — Schema + migration** | Tables `evaluation_dataset`, `evaluation_run`, `evaluation_item`, `evaluation_metric_fact` (or merged variant); minimal seed dataset. |
| **P2 — Worker API** | Internal endpoint or CLI: `POST /api/evaluation/runs` → enqueue job; worker writes rows; idempotent run slug. |
| **P3 — Read API** | `GET` runs, items, summaries for Admin UI. |
| **P4 — Admin UI skeleton** | Route + list/detail pages read-only; no charts. |
| **P5 — Compare + manual score** | UI for scoring + two-run diff. |
| **P6 — RAGAS worker** | Optional dependency; batch post-process items; write `ragas.*` metrics. |

---

## 14. Open questions

1. **Single DB** — confirm all AF deployments that will run eval have PostgreSQL; else SQLite fallback only for dev risks split-brain.
2. **Golden answers** — who owns curation and refresh cycle for `expected_answer`?
3. **Cross-backend score comparability** — document that run-level comparisons across backends are **indicative** unless scores are normalized (already an AF invariant elsewhere).
4. **Legal / PII** — whether imported production queries need redaction pipeline before dataset storage.

---

## 15. Risks

| Risk | Mitigation |
|------|------------|
| Eval jobs exhaust OpenAI quota | Hard caps, concurrency limits, dry-run mode. |
| Schema churn | Version `config_snapshot` + migration discipline; avoid breaking item JSON contract without bumping `schema_version` inside JSON. |
| Operators confuse prod logs vs eval runs | Clear UI labels + never mix rows in one table without a `source` column. |
| Premature RAGAS trust | Keep RAGAS scores secondary to manual + distance diagnostics until calibrated. |

---

## 16. Document control

- **Owner:** engineering (AF core).
- **Next review:** after P1 schema draft or first pilot run.

**Related backlog:** `PROJECT_STATE.md` §47.2–47.4 (retrieval quality, metrics, experiments).
