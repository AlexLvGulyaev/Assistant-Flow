# Full original task prompt

```text
# RAGAS admin-api dependency fix prompt

Используй Codex 5.3.

Проведи targeted operational fix для проблемы RAGAS skipped.

Контекст:
Диагностика показала, что Evaluation / RAGAS workflow operationally исправен:
- ground_truth сохранены;
- retrieval chunks присутствуют;
- evaluation_item / dataset_item linkage корректен;
- contexts path работает.

Root cause:
`portfolio-test-admin-api-1` runtime environment не содержит importable dependencies:
- ragas
- datasets

Из-за этого:
- `check_ragas_dependencies().ready == false`
- run получает status=`skipped`
- metrics persist как `not_collected`.

Цель:
исправить admin-api runtime/install path так, чтобы RAGAS evaluation реально выполнялся внутри admin-api container.

Необходимо:
1. определить, почему `requirements-ragas.txt` не попадает в admin-api runtime;
2. исправить build/runtime dependency path;
3. убедиться, что внутри `portfolio-test-admin-api-1` успешно импортируются:
   - ragas
   - datasets
   - langchain_openai
4. rebuild/redeploy admin-api;
5. повторно выполнить RAGAS для run:
   `7fb2fea5-e3cc-448e-a502-2dadd203482d`
6. убедиться, что run больше не получает status=`skipped`;
7. убедиться, что metrics реально вычисляются.

Constraints:
- minimal targeted fix only;
- no broad refactor;
- no schema changes;
- preserve current evaluation architecture;
- preserve existing operational workflow;
- no unrelated cleanup.

Session logging:
создай session log:
`docs/cursor_sessions/2026-05-15_ragas_admin_api_dependency_fix.md`

В начало session log полностью помести этот prompt.

В конец добавить:
1. changed files;
2. root cause;
3. exact dependency/runtime fix;
4. rebuild commands;
5. verification commands;
6. RAGAS rerun result;
7. metric verification;
8. git status.

Commit НЕ выполнять.

В ответе предоставить только:
1. root cause;
2. changed files;
3. rebuild commands;
4. rerun result;
5. git status.
```

## Changed files

- `Dockerfile`
- `docker-compose.portfolio.yml`
- `docs/cursor_sessions/2026-05-15_ragas_admin_api_dependency_fix.md`

## Root cause

`admin-api` container image was built from `Dockerfile` that installed only `requirements.txt`; optional `requirements-ragas.txt` was never copied/installed in runtime.

As a result:

- `ragas` and `datasets` were not importable in `portfolio-test-admin-api-1`
- `check_ragas_dependencies().ready` returned `false`
- `run_ragas_evaluation()` returned `status="skipped"`
- persistence layer wrote `not_collected` metrics.

## Exact dependency/runtime fix

Targeted build-path fix only:

1. Added `ARG INSTALL_RAGAS=false` in root `Dockerfile`.
2. Added `COPY requirements-ragas.txt .` to image build context.
3. Updated install step to conditionally install RAGAS stack:
   - always `pip install -r requirements.txt`
   - if `INSTALL_RAGAS=true` then `pip install -r requirements-ragas.txt`
4. Enabled the arg for `admin-api` service in `docker-compose.portfolio.yml`:
   - `build.args.INSTALL_RAGAS: "true"`

No schema/API/architecture changes.

## Rebuild commands

```bash
docker compose -p portfolio-test -f /opt/assistant-flow/docker-compose.portfolio.yml build admin-api
docker compose -p portfolio-test -f /opt/assistant-flow/docker-compose.portfolio.yml up -d admin-api
```

## Verification commands

```bash
docker exec portfolio-test-admin-api-1 python -c "import importlib; mods=['ragas','datasets','langchain_openai']; \
for m in mods: \
    importlib.import_module(m); print(m,'OK')"

curl -sS http://localhost:8600/api/health

curl -sS -X POST http://localhost:8600/api/evaluation/ragas/run \
  -H "Content-Type: application/json" \
  -d '{"run_id":"7fb2fea5-e3cc-448e-a502-2dadd203482d"}'

docker exec portfolio-test-postgres-1 psql -U assistant -d assistant_flow -c "SELECT ... run_summary ragas ..."
docker exec portfolio-test-postgres-1 psql -U assistant -d assistant_flow -c "SELECT ... metric_value_numeric/not_collected ..."
```

## RAGAS rerun result

Rerun request:

- `POST /api/evaluation/ragas/run` with `run_id=7fb2fea5-e3cc-448e-a502-2dadd203482d`

Result:

- `status: ok`
- `unavailable_metrics: []`
- `run_means`:
  - `ragas.faithfulness: 0.7`
  - `ragas.answer_relevancy: 0.755168`
  - `ragas.context_precision: 0.64`

## Metric verification

SQL verification (`evaluation_metric_fact`, run_id `7fb2fea5-e3cc-448e-a502-2dadd203482d`):

- `ragas.answer_relevancy`: `rows_total=10`, `numeric_rows=10`, `not_collected_rows=0`
- `ragas.context_precision`: `rows_total=10`, `numeric_rows=10`, `not_collected_rows=0`
- `ragas.faithfulness`: `rows_total=10`, `numeric_rows=10`, `not_collected_rows=0`

Run summary verification:

- `run_summary.ragas.status = "ok"`
- `run_summary.ragas.unavailable_metrics = []`

## Git status

```bash
 M .env.example
 M Dockerfile
 M admin_api/app.py
 M docker-compose.portfolio.yml
 M frontend/admin-ui/src/App.tsx
 M frontend/admin-ui/src/api/client.ts
 M frontend/admin-ui/src/navigation/routes.ts
 M frontend/admin-ui/src/pages/RagPage.tsx
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
 M repositories/evaluation_repository.py
 M services/evaluation/ragas_adapter.py
 M services/evaluation_service.py
?? admin_api/routes/evaluation.py
?? admin_api/schemas/evaluation.py
?? cursor_tasks_local/
?? docker-compose.portfolio.yml.bak
?? docs/architecture/cursor_operational_workflow_regulation.md
?? docs/cursor_sessions/2026-05-15_eval-rag-list-item-alignment.md
?? docs/cursor_sessions/2026-05-15_eval-ui-compact-density-pass.md
?? docs/cursor_sessions/2026-05-15_evaluation_layout_analysis.md
?? docs/cursor_sessions/2026-05-15_evaluation_layout_specification.md
?? docs/cursor_sessions/2026-05-15_evaluation_master_detail_implementation.md
?? docs/cursor_sessions/2026-05-15_evaluation_ragas_operational_verification.md
?? docs/cursor_sessions/2026-05-15_ragas-evaluation-p1.md
?? docs/cursor_sessions/2026-05-15_ragas-evaluation-ui-p2-lite.md
?? docs/cursor_sessions/2026-05-15_ragas_admin_api_dependency_fix.md
?? docs/cursor_sessions/2026-05-15_ragas_skipped_diagnostic.md
?? frontend/admin-ui/src/components/OperationalListPagination.tsx
?? frontend/admin-ui/src/components/OperationalRetrievalChunksSection.tsx
?? frontend/admin-ui/src/pages/EvaluationPage.tsx
?? frontend/admin-ui/src/utils/retrievalChunks.ts
?? requirements-ragas.txt
?? scripts/evaluation_import_recent.py
?? scripts/evaluation_import_session.py
?? scripts/evaluation_ragas.py
?? scripts/evaluation_seed_ragas_dataset.py
?? services/evaluation_admin_service.py
?? services/evaluation_import_service.py
?? services/evaluation_ragas_service.py
```
