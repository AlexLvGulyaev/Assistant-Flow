# Session log: Evaluation Layer — architecture design stage

**Date:** 2026-05-14 (`date +%F`)

---

## Full prompt (verbatim)

Cursor, начинаем проектирование Evaluation Layer для Assistant Flow.

Важно:
это НЕ “раздел отчётов” и НЕ “учебная фича”.

Речь идёт о foundation для:

* retrieval evaluation,
* quality metrics,
* experiments,
* future RAGAS integration,
* operational AI diagnostics.

Нужно выполнить architectural design stage.
Пока БЕЗ полноценной реализации production UI.

---

## КОНТЕКСТ

AF уже содержит:

* RAG observability;
* retrieval diagnostics;
* chunk inspection;
* lifecycle timeline;
* memory observability;
* token metrics;
* retrieval query visibility;
* duplicate diagnostics.

Следующий слой зрелости:
Evaluation / Quality subsystem.

---

## ЦЕЛЬ

Спроектировать unified Evaluation Layer,
который будет поддерживать:

1. Manual evaluation
2. Retrieval experiments
3. top_k comparison
4. chunk_size / overlap comparison
5. token vs quality analysis
6. retrieval quality metrics
7. future RAGAS integration

---

## ВАЖНО

НЕ делать:

* “дашбордик ради дашбордика”;
* giant BI system;
* premature analytics platform.

Нужен:
production-grade operational evaluation foundation.

---

## ЧТО НУЖНО СДЕЛАТЬ

1. Спроектировать data model

Предварительно:

evaluation_runs
evaluation_items

Но:

* проверить соответствие архитектуре AF;
* подумать о versioning;
* подумать о retrieval backend abstraction;
* подумать о future RAGAS metrics.

---

2. Спроектировать metrics model

На первом этапе:

* avg_tokens
* avg_latency
* fallback_rate
* duplicate_chunk_rate
* irrelevant_chunk_rate
* retrieval_count
* retrieved_context_size

Manual:

* score 0 / 0.5 / 1
  или предложить лучший lightweight вариант.

Future:

* RAGAS:

  * faithfulness
  * answer_relevancy
  * context_precision
  * context_recall

---

3. Спроектировать UI architecture

НЕ реализовывать fully.

Нужно:

* wireframe-level architecture;
* routing;
* console structure;
* reuse existing operational console patterns.

Предлагаемый раздел:

Admin UI
└── Evaluation / Quality

Внутри:

* experiments list;
* run compare;
* item inspection;
* metrics summary.

---

4. Продумать experiment workflow

Например:

Run:

* backend=weaviate
* top_k=3
* chunk_size=700
* overlap=120

Dataset:

* predefined queries

Result:

* metrics
* retrieval diagnostics
* manual score
* future ragas scores.

---

5. Продумать integration points

Где брать:

* token usage;
* retrieval diagnostics;
* chunks;
* latency;
* fallback reason;
* memory routing diagnostics.

---

6. Особо важно

Evaluation Layer НЕ должен:

* ломать existing runtime;
* тормозить pipeline;
* быть tightly coupled к конкретному retrieval backend.

---

7. Нужно отдельно описать

Как текущие retrieval observability features:

* chunk diagnostics;
* duplicate diagnostics;
* retrieval-ready query;
* timeline;
* memory observability;

могут использоваться как foundation для Evaluation Layer.

---

8. OUTPUT

---

Нужен НЕ код.

Нужен architectural design document.

Формат:
Markdown.

Пример файла:

docs/architecture/evaluation_layer_design.md

---

9. В документе обязательно

* goals
* non-goals
* architecture
* entities
* metrics
* UI concept
* operational implications
* scaling considerations
* future RAGAS integration
* phased implementation plan

---

10. Session log

Создать:
docs/cursor_sessions/YYYY-MM-DD_evaluation-layer-architecture-design.md

Дата:
date +%F

Включить:

* полный prompt;
* design decisions;
* open questions;
* risks;
* proposed next implementation phase.

Commit НЕ выполнять.

---

## Deliverable

**Primary design document:** [`docs/architecture/evaluation_layer_design.md`](../architecture/evaluation_layer_design.md)

---

## Design decisions (summary)

- **Complement, not replace** `processing_logs`: curated `evaluation_run` / `evaluation_item` with immutable `config_snapshot` and denormalized query text per item.
- **Dataset** as first-class versioned entity so the same query set can be replayed under many configs (top_k, backend, chunk fingerprint).
- **Metrics:** run-level aggregates in `run_summary` JSONB for v1 simplicity; extensible **`evaluation_metric_fact`** (or equivalent) keyed namespace for manual scores and future `ragas.*` dimensions.
- **Ingestion:** offline replay / batch worker on the hot-path boundary — no synchronous evaluation writes from production RAG answer flow in phase 1.
- **Backend abstraction** in persistence: opaque identifiers + JSON snapshot, not vendor-specific columns.
- **Manual score:** default rubric `0 / 0.5 / 1` with optional migration to Likert later; stored as metric facts for uniformity.
- **UI:** wireframe only — `/evaluation` (or `/quality`) with runs list, run header + metrics, items table, compare tab, item drawer reusing operational console components (badges, JSON fold, chunk metaphors).

---

## Open questions

1. PostgreSQL as mandatory store for eval in all environments, or dev SQLite fallback semantics.
2. Ownership and refresh cycle for golden / expected answers.
3. Declared policy for cross-backend numeric comparison (indicative vs normalized only).
4. PII / redaction for queries imported from production logs into datasets.

---

## Risks

- Embedding / LLM quota exhaustion from unconstrained experiment concurrency → caps and job queues.
- Schema churn on item JSON payloads → embed `schema_version` inside snapshots.
- Operator confusion between prod traces and eval runs → strict UI copy and `source` / `trigger` fields.

---

## Proposed next implementation phase

**Phase P1 (after design sign-off):** DDL migrations for `evaluation_dataset` (+ items), `evaluation_run`, `evaluation_item`, `evaluation_metric_fact`; seed one tiny dataset; no Admin UI beyond optional read-only JSON API for verification.

---

## Operator commands / next verification commands

```bash
date +%F
ls -la docs/architecture/evaluation_layer_design.md
wc -l docs/architecture/evaluation_layer_design.md docs/cursor_sessions/2026-05-14_evaluation-layer-architecture-design.md
rg -n "^## [0-9]" docs/architecture/evaluation_layer_design.md
```

Review the design doc sections **1–15** for completeness against the prompt checklist (goals, non-goals, architecture, entities, metrics, UI, operational & scaling, RAGAS, phases).

---

## Commit

Not performed (per request).
