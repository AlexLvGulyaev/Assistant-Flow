# Session: Evaluation Layer P1-lite (operational MVP)

**Date:** 2026-05-11 (`date +%F`)

**Reference:** initiating user message in session transcript [Evaluation P1-lite spec](145c6aba-1cbb-46e6-8186-a787c6212422).

**Commit:** not performed (per request).

---

## Full prompt (verbatim)

```
Cursor, начинаем реализацию Evaluation Layer P1-lite для Assistant Flow.

Цель:
сделать минимальный operational evaluation MVP, который позволит оператору:

1. создать evaluation run;
2. прогнать один и тот же набор вопросов при разных параметрах, прежде всего `top_k`;
3. сохранить результаты;
4. вручную оценить качество ответа;
5. сравнить runs по базовым метрикам;
6. использовать результаты для инженерного отчёта.

Это НЕ полный Evaluation Platform.
Это НЕ RAGAS.
Это P1-lite.

==================================================
Scope P1-lite
=============

Реализовать минимально:

1. DB schema / migration:

* evaluation_dataset
* evaluation_dataset_item
* evaluation_run
* evaluation_item
* evaluation_metric_fact

Если возможно — в максимально простом виде, но без тупиков для будущего RAGAS.

2. Seed dataset:
   создать один маленький dataset для проверки:

* 5–8 вопросов;
* русскоязычные RAG / conversational RAG вопросы;
* dataset должен быть пригоден для сравнения top_k=3 vs top_k=5.

3. Run creation:
   добавить способ создать run:

* CLI script предпочтительно для P1-lite;
* API можно только если не раздувает объём.

Параметры run:

* dataset_slug
* top_k
* retrieval_backend/effective backend
* notes/name

4. Execution:
   run должен прогонять вопросы через существующий RAG pipeline в eval mode:

* без Telegram side effects;
* без отправки сообщений пользователю;
* с сохранением retrieval diagnostics;
* с сохранением answer;
* с сохранением token usage, если есть;
* с сохранением latency;
* с fallback_reason;
* с duplicate diagnostics, если есть.

5. Manual scoring:
   минимально:

* score 0 / 0.5 / 1;
* можно через простой CLI update script или API endpoint;
* UI не обязателен на этом этапе.

6. Compare:
   добавить простой report script:

compare two runs:

* avg_manual_score
* avg_tokens
* avg_latency_ms
* fallback_rate
* duplicate_chunk_rate
* retrieved_count_avg
* item table

Output:

* markdown table;
* JSON file optional.

Цель:
получить таблицу, которую можно вставить в отчёт.

==================================================
Important constraints
=====================

* Не ломать production RAG.
* Не писать eval в hot path Telegram.
* Не менять обычный runtime.
* Не завязываться на конкретный backend.
* Не делать большой UI сейчас.
* Не внедрять RAGAS сейчас, но оставить место для `ragas.*` metric keys.

==================================================
Expected commands
=================

Нужны команды вида:

1. run migration
2. seed dataset
3. create/run top_k=3
4. create/run top_k=5
5. compare runs
6. optional manual scoring

Команды должны работать внутри canonical portfolio container:

```bash
docker exec portfolio-test-assistant-flow-1 ...
```

==================================================
Files / architecture expectations
=================================

Предпочтительно:

* database migration file
* repositories/evaluation_repository.py
* services/evaluation_service.py
* scripts/evaluation_seed_dataset.py
* scripts/evaluation_run.py
* scripts/evaluation_score_item.py
* scripts/evaluation_compare_runs.py

Но проверь существующую структуру проекта и выбери минимально согласованный вариант.

==================================================
Metrics
=======

Минимум:

* avg_manual_score
* avg_tokens
* avg_latency_ms
* fallback_rate
* duplicate_chunk_rate
* retrieved_count_avg

Если поле отсутствует:

* не падать;
* писать `null` / `not collected`;
* явно показывать observability gap.

==================================================
Engineering log
===============

Создать:

docs/cursor_sessions/YYYY-MM-DD_evaluation-p1-lite.md

Дата:

date +%F

Включить:

* полный prompt;
* changed files;
* schema summary;
* commands;
* limitations;
* what is intentionally not implemented;
* next phase toward RAGAS.

В конце обязательно:

## Operator commands / next verification commands

Commit НЕ выполнять.
```

---

## Changed files

| Path | Role |
|------|------|
| `database/migrations/006_evaluation_p1_lite.sql` | Incremental DDL for existing Postgres volumes |
| `database/schema.sql` | Canonical snapshot includes same evaluation tables (header notes migration 006) |
| `repositories/evaluation_repository.py` | CRUD + `list_metrics_for_run` + `update_run_summary` |
| `services/evaluation_service.py` | `build_rag_query_service_for_eval`, `execute_run`, diagnostics split, `compute_run_summary` |
| `scripts/evaluation_seed_dataset.py` | Seed slug `p1_lite_ru_baseline_v1`, 7 RU queries |
| `scripts/evaluation_run.py` | Subcommands `create`, `execute`, `run` |
| `scripts/evaluation_score_item.py` | `manual.overall` + refresh `run_summary` |
| `scripts/evaluation_compare_runs.py` | Markdown (+ optional `--json-out`) for two run UUIDs |

---

## Schema summary

- **`evaluation_dataset`**: `slug`, `version` (unique pair), `title`, `metadata` JSONB.
- **`evaluation_dataset_item`**: `dataset_id`, `ordinal`, `query_text`, `metadata`.
- **`evaluation_run`**: links dataset, `config_snapshot` JSONB (`top_k`, optional `retrieval_backend_note`), `status`, `run_summary` JSONB, timestamps.
- **`evaluation_item`**: per-question execution: `answer_text`, `retrieval_diag` / `generation_diag` JSONB, `latency_ms_total`, `status`, `error_text`.
- **`evaluation_metric_fact`**: sparse facts; `metric_key` is an open namespace (e.g. `manual.overall`, future `ragas.*`); partial unique index on `(item_id, metric_key)` when `item_id` is set.

---

## Commands (conceptual)

1. Apply migration on **existing** DB volumes (compose initdb only mounts `schema.sql` + `004_async_jobs`; it does **not** mount `006` — operators with old volumes run SQL once).
2. Seed dataset (idempotent upsert on slug/version and ordinals).
3. `evaluation_run.py run` with `--top-k 3` then `--top-k 5`.
4. Optional manual scores via `evaluation_score_item.py`.
5. `evaluation_compare_runs.py --run-a … --run-b … [--json-out …]`.

---

## Limitations

- **Backend switching** is not implemented in P1-lite CLI: only an opaque `--backend-note` string in `config_snapshot`; effective backend remains whatever `RetrievalBackendManager` resolves from env/config.
- **`run_summary` after execute** includes aggregates without manual scores until scored; compare script recomputes from DB rows, so it stays correct after scoring.
- **Observability gaps**: compare and `compute_run_summary` use `null` in JSON and the string `null` in markdown when a metric cannot be derived (no tokens in diagnostics, no duplicates fields, etc.).
- **No deduplication of runs**: re-`execute` on a completed run is rejected; create a new run.
- **Portfolio compose**: project name in examples is often `portfolio-test`; adjust `-p` to match your stack.

---

## Intentionally not implemented (P1-lite)

- REST API for runs/scores/compare, Admin UI, scheduled jobs.
- RAGAS library, automated LLM-judge metrics, golden answers per dataset item.
- Telegram hooks, `processing_logs` writes on eval path.
- Cross-backend A/B in one process without rebuild/env change.

---

## Next phase toward RAGAS

- Store **contexts** and **ground_truth** (optional columns or `metric_value_json` / dataset item metadata) for RAGAS row format.
- Add metric keys `ragas.faithfulness`, etc., populated by an offline worker.
- Versioned **dataset** contracts and regression baselines on `dataset_version`.
- Optional: append `006_evaluation_p1_lite.sql` to `docker-compose.portfolio.yml` `postgres` `docker-entrypoint-initdb.d` for greenfield parity (redundant if `schema.sql` already defines the same tables).

---

## Operator commands / next verification commands

Replace compose project `-p` if yours differs (`portfolio-test` is common in repo docs).

**1. Rebuild / recreate app container after pulling code**

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml build assistant-flow
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d assistant-flow
```

**2. Apply migration 006 on existing Postgres data** (skip if fresh volume was created from current `database/schema.sql` that already contains evaluation tables)

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml exec -T postgres \
  psql -U assistant -d assistant_flow -v ON_ERROR_STOP=1 \
  -f /dev/stdin < database/migrations/006_evaluation_p1_lite.sql
```

If `psql` stdin from host file is awkward, copy the file into the container or run from host against port `5433` with `psql` and the same SQL.

**3. Seed dataset**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_seed_dataset.py
```

**4. Run evaluation top_k=3 and top_k=5**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py run \
  --dataset p1_lite_ru_baseline_v1 --top-k 3 --name top3

docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py run \
  --dataset p1_lite_ru_baseline_v1 --top-k 5 --name top5
```

Note printed `run_id` values (or query `evaluation_run`).

**5. Optional manual scoring** (per `evaluation_item.id`)

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_score_item.py \
  --item-id <uuid> --score 1
```

**6. Compare two runs**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_compare_runs.py \
  --run-a <uuid-a> --run-b <uuid-b> --json-out /app/outputs/eval_compare.json
```

**7. Syntax smoke (host or container)**

```bash
docker exec portfolio-test-assistant-flow-1 python -m py_compile \
  services/evaluation_service.py repositories/evaluation_repository.py \
  scripts/evaluation_run.py scripts/evaluation_seed_dataset.py \
  scripts/evaluation_score_item.py scripts/evaluation_compare_runs.py
```
