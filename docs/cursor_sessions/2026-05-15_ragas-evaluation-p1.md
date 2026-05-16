# Session: RAGAS evaluation P1 (Evaluation Layer extension)

**Date:** 2026-05-15 (`date +%F`)

**Commit:** not performed (per request).

---

## Full prompt (verbatim)

```
Cursor, начинаем урок PEr06 / RAGAS integration для Assistant Flow.

Цель:
встроить RAGAS в существующий Evaluation Layer AF, а не делать отдельную учебную демку.

Контекст:
в AF уже есть Evaluation P1-lite:

* evaluation_dataset
* evaluation_dataset_item
* evaluation_run
* evaluation_item
* evaluation_metric_fact
* scripts/evaluation_run.py
* scripts/evaluation_compare_runs.py

Нужно расширить этот слой под RAGAS.

Важно:

* НЕ копировать учебный код напрямую;
* сначала изучить `legacy/PEr06_source`;
* переиспользовать только полезные идеи;
* адаптировать под текущую архитектуру AF;
* не ломать existing evaluation runs;
* не писать RAGAS в hot path Telegram/RAG runtime.

Задачи:

1. Audit legacy
2. Dataset для RAGAS (отдельный корпус)
3. Evaluation dataset `ragas_baseline_ru_v1`
4. Script `scripts/evaluation_ragas.py`
5. Storage in `evaluation_metric_fact`
6. Operator commands (portfolio-test-assistant-flow-1)
7. Не реализовывать: Admin UI, scheduled jobs, hot path, BI dashboard
8. Engineering log
9. Operator commands section + git status; no commit
```

(Full task list preserved in session transcript; abbreviated header above for navigation.)

---

## Legacy audit (`legacy/PEr06_source`)

### `evaluate_rag.py`

| Aspect | Finding |
|--------|---------|
| Dataset shape | HuggingFace `Dataset` with columns: `question`, `answer`, `contexts` (list of chunk texts), `ground_truth` |
| Data collection | Loop over fixed questions → `ask_assistant()` → append answer + context chunk `document` fields |
| Metrics | `faithfulness`, `answer_relevancy`, `context_precision` via `ragas.evaluate()` |
| LLM/embeddings | `LangchainEmbeddingsWrapper` + `LangchainLLMWrapper` around `langchain_openai` (fallback to built-in metric objects) |
| Ground truth | Left empty in demo (`""`) — limits `context_precision` usefulness |
| Dependencies | `ragas`, `datasets`, `langchain-openai`, `openai` |

### `rag_assistant.py`

| Aspect | Finding |
|--------|---------|
| Retrieval | Chroma `query` with OpenAI embeddings, `top_k` from config |
| Return shape | `{"answer": str, "context": [{document, metadata, distance}]}` |
| Generation | OpenAI chat with strict context-only system prompt |

### Adapted to AF (not copied)

- Rows built from **`evaluation_item`** (answer + `retrieval_diag.retrieved_chunks`) after **`evaluation_run.py execute`**, not live `ask_assistant`.
- Ground truth from **`evaluation_dataset_item.metadata.ground_truth`** (no schema migration).
- Scores persisted to **`evaluation_metric_fact`** with keys `ragas.*`.
- Separate knowledge file **`ragas_facts_baseline.txt`** + dataset slug **`ragas_baseline_ru_v1`** to avoid AF/IT-glossary corpus bias.

---

## Changed / added files

| Path | Role |
|------|------|
| `data/documents/ragas_facts_baseline.txt` | Isolated factual KB (NovaTech fiction: dates, names, SLA, license limits) |
| `scripts/evaluation_seed_ragas_dataset.py` | Seed `ragas_baseline_ru_v1` (5 questions + metadata) |
| `services/evaluation/ragas_adapter.py` | `check_ragas_dependencies`, `run_ragas_evaluation` (full `evaluate()` when installed) |
| `services/evaluation_ragas_service.py` | Rows from completed run, persist metrics + `run_summary.ragas` |
| `scripts/evaluation_ragas.py` | CLI: `check-deps`, `run`, `show-metrics` |
| `requirements-ragas.txt` | Optional deps (`ragas`, `datasets`) |
| `.env.example` | Comment for `RAGAS_CHAT_MODEL` |

**Unchanged:** P1-lite tables/migrations, `evaluation_run.py`, Telegram/RAG hot path.

---

## Dependencies added

**Optional** (`requirements-ragas.txt`, not in main `requirements.txt`):

- `ragas>=0.1.9,<0.3`
- `datasets>=2.14.0`
- Uses existing `langchain-openai` from main requirements for judge LLM/embeddings.

Install in container:

```bash
pip install -r requirements-ragas.txt
```

Env: `OPENAI_API_KEY` (required for RAGAS judge); optional `RAGAS_CHAT_MODEL` (default `gpt-4o-mini`).

---

## Dataset summary

### Knowledge document

- **File:** `data/documents/ragas_facts_baseline.txt`
- **Content:** ООО «НоваТех» — registration date, CEO, SLA tiers, license cap (50 users), cloud migration date, etc.
- **Explicit exclusion:** no stock ticker / NASDAQ data (supports `no_answer` question).

### Evaluation dataset

| Slug | `ragas_baseline_ru_v1` |
| Version | 1 |
| Items | 5 |

| Ord | Type | Question (short) |
|-----|------|------------------|
| 1 | `exact_fact` | Registration date of NovaTech |
| 2 | `exact_fact` | CEO since Jan 2022 |
| 3 | `paraphrase` | Premium support response time (hours) |
| 4 | `paraphrase` | Max users per corporate license |
| 5 | `no_answer` | NASDAQ ticker / quote (not in KB) |

**Metadata per item:** `question_type`, `ground_truth` (empty for no_answer), optional `expects_no_answer`.

---

## RAGAS metrics implemented

| `metric_key` | RAGAS metric | Notes |
|--------------|--------------|-------|
| `ragas.faithfulness` | Faithfulness | LLM-as-judge |
| `ragas.answer_relevancy` | AnswerRelevancy | Requires embeddings wrapper when possible |
| `ragas.context_precision` | ContextPrecision | Skipped if **all** rows lack `ground_truth`; needs reference for meaningful scores |

**Storage:**

- `metric_value_numeric`: float 0..1 when computed
- `metric_value_json`: `{source, errors, question_type, contexts_count}` or `{status: not_collected, reason}`

**Run summary:** `evaluation_run.run_summary.ragas` — `status`, `detail`, `run_means`, `unavailable_metrics`.

---

## Limitations

- RAGAS not in default image; operator must `pip install -r requirements-ragas.txt`.
- RAGAS version API drift: adapter tries class-based metrics + Langchain wrappers, then falls back to module-level metrics.
- **Cost/latency:** each item triggers multiple judge LLM calls; no batching/async worker.
- **Indexing:** operator must reindex so `ragas_facts_baseline.txt` is in active backend (ideally `--reindex` on isolated corpus or dedicated test stack).
- **Context extraction:** uses `retrieved_chunks` with `passed_filter=True` from stored diagnostics; empty contexts → weak/unstable RAGAS scores.
- `no_answer` item still gets faithfulness/relevancy scores (may be low); not a separate RAGAS metric.
- Does not modify `evaluation_compare_runs.py` for RAGAS columns (use `show-metrics` or SQL).

---

## Next steps

- Add RAGAS columns to `evaluation_compare_runs.py` for A/B runs.
- Scheduled post-run RAGAS worker (async_jobs) after run completion.
- Curated multi-document RAGAS corpus + versioning in `evaluation_dataset.metadata`.
- Calibrate thresholds per `question_type`; optional `context_recall` when ground-truth contexts are labeled.
- Mount `requirements-ragas.txt` install in Dockerfile optional profile.

---

## Operator commands / next verification commands

Replace `-p portfolio-test` if your compose project name differs.

### Rebuild / recreate (after code pull)

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml build assistant-flow
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d assistant-flow
```

### Dependency check / install

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py check-deps
docker exec portfolio-test-assistant-flow-1 pip install -r requirements-ragas.txt
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py check-deps
```

### Seed RAGAS evaluation dataset

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_seed_ragas_dataset.py
```

### Index isolated facts document (reindex when testing clean retrieval)

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/admin_index_documents.py --reindex
```

### Run RAG pipeline evaluation (prerequisite for RAGAS)

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py run \
  --dataset ragas_baseline_ru_v1 --top-k 5 --name ragas-top5
```

Save printed `run_id`.

### Run RAGAS on completed run

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py run --run-id <RUN_UUID>
```

### Show metrics (CLI)

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py show-metrics --run-id <RUN_UUID>
```

### SQL: metric facts for a run

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml exec -T postgres \
  psql -U assistant -d assistant_flow -c "
SELECT ei.ordinal, emf.metric_key, emf.metric_value_numeric, emf.metric_value_json
FROM evaluation_metric_fact emf
JOIN evaluation_item ei ON ei.id = emf.item_id
WHERE emf.run_id = '<RUN_UUID>' AND emf.metric_key LIKE 'ragas.%'
ORDER BY ei.ordinal, emf.metric_key;
"
```

### Git status (no commit in this session)

```bash
cd /opt/assistant-flow && git status
```

---

## P1.1 append: Interactive conversational evaluation (architectural correction)

### Full prompt (P1.1)

```
Cursor, важное архитектурное уточнение по RAGAS integration.

Dataset-first evaluation технически корректна, НО UX/architecture direction для AF неверна.
AF — conversational operational platform → evaluation должен интегрироваться в normal runtime flow.

P1.1: interactive conversational evaluation.
Использовать реальные conversational interactions как источник evaluation data.

Сохранить P1 (tables, ragas adapter, evaluation_ragas.py, dataset mode).
Добавить CLI import: execution_id или recent limit.
Источник: chat_messages, processing_logs, request_logs, retrieval diagnostics.
Pipeline: interactive usage → import → evaluation_run (completed) → evaluation_ragas.py (unchanged).
Не делать: UI, auto-import, realtime RAGAS, jobs, dashboard.
```

### Why dataset-only evaluation was insufficient

- AF operators improve quality from **real Telegram/dialog traffic**, not only from frozen benchmark JSON.
- Scripted `evaluation_run.py` re-executes RAG offline — useful for **reproducibility** (`top_k` A/B), but it **does not capture** production routing, memory assembly, or operator phrasing.
- A separate “lab” workflow (seed → run → RAGAS) drifts from the product truth: **the platform is conversational first**.

### Why AF requires conversational evaluation flow

- Every RAG turn already emits **`rag_answer_done`** in `processing_logs` with `user_input`, `answer_text`, `retrieved_chunks`, backends, tokens.
- **`chat_messages`** stores the same turn for memory/history — no new event bus required.
- Evaluation should be a **read-only import** from operational storage → same `evaluation_item` / `evaluation_metric_fact` model → same `evaluation_ragas.py`.

### Architectural distinction

| Layer | Role | When to use |
|-------|------|-------------|
| **Benchmark dataset** (`ragas_baseline_ru_v1`, `p1_lite_*`) | Controlled corpus, reproducible regressions, `top_k` experiments | CI, isolated KB, engineering reports |
| **Conversational import** (`interactive_eval_tmp`, `execution_id`) | Real operator/user traces from production-like usage | Quality review, RAGAS on live phrasing, incident follow-up |

Both share tables and RAGAS CLI; neither writes to Telegram hot path.

### P1.1 changed / added files

| Path | Role |
|------|------|
| `services/evaluation_import_service.py` | Trace → `evaluation_run` + `evaluation_item` (completed) |
| `services/evaluation_service.py` | `split_log_details_to_blobs()` for `processing_logs.details` |
| `scripts/evaluation_import_session.py` | `--execution-id` import |
| `scripts/evaluation_import_recent.py` | `--limit N` recent `rag_answer_done` |

**Unchanged:** `evaluation_ragas.py`, RAGAS adapter, DB schema, dataset seed scripts.

### P1.1 operator commands

```bash
# After a real RAG interaction in Telegram, note execution_id from Admin/processing_logs

docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_import_session.py \
  --execution-id <EXECUTION_UUID> --dataset interactive_eval_tmp

# Or batch recent RAG turns
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_import_recent.py \
  --limit 5 --dataset interactive_eval_tmp

# RAGAS (unchanged)
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py run --run-id <RUN_UUID>
docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py show-metrics --run-id <RUN_UUID>
```

Find recent execution IDs:

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml exec -T postgres \
  psql -U assistant -d assistant_flow -c "
SELECT execution_id, created_at, details->>'query_preview' AS q
FROM processing_logs
WHERE stage = 'rag_answer_done'
ORDER BY created_at DESC
LIMIT 10;
"
```
