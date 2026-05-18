# Промпт для Cursor: Cache Observability Console / PEr07 — design pass

Используй Codex 5.3.

Прочитай и выполни. Общаемся, комментарии и отчёты пишем строго на русском языке.

Продолжаем subsystem-scoped sprint:
PEr07 / Cache Layer / Retrieval Optimization для Assistant Flow.

ВАЖНО:
после предыдущего pass retrieval cache foundation уже operationalized на backend/diagnostics уровне.
Теперь задача НЕ закрыть урок smoke-тестами, а спроектировать видимый operator-facing контур в Admin UI.

По линии проекта Assistant Flow каждый урок модуля должен давать новую operational capability:
- консоль;
- режим в существующей консоли;
- диагностический контур;
- наблюдаемый пользовательский сценарий.

Для PEr07 такой capability должен быть:
Cache / Optimization observability console или cache diagnostics mode в существующей RAG/Retrieval Settings консоли.

==================================================
КОНТЕКСТ
==================================================

Уже сделано:

1. docs/architecture/cache_layer_design.md
2. retrieval cache operationalization pass
3. telemetry normalization:
   - retrieval_cache_hit
   - retrieval_cache_miss
   - cache_layer
   - cache_latency_ms
   - retrieval_cache_generation
   - retrieval_cache_backend
   - retrieval_cache_key_hash_prefix
4. invalidation discipline:
   - backend-sensitive key
   - top_k-sensitive key
   - embedding-model-sensitive key
   - retrieval_generation-sensitive key
5. evaluation bypass:
   - evaluation_cache_bypass=true
   - evaluation_cache_policy="retrieval_cache_disabled"

Теперь нужно спроектировать, как оператор увидит и проверит это в Admin UI.

==================================================
ЦЕЛЬ ЭТАПА
==================================================

Подготовить UI/UX + API design для Cache Observability capability.

Нужно ответить:

1. Где в Admin UI должен жить cache observability:
   - отдельная страница Cache / Optimization;
   - вкладка/режим внутри RAG;
   - секция внутри Retrieval Settings;
   - или комбинированная модель.

2. Какие действия оператор должен уметь выполнить руками.

3. Какие telemetry поля нужно показать.

4. Как показать:
   - первый запрос → cache miss;
   - повторный запрос → cache hit;
   - reindex/generation bump → invalidation;
   - backend/top_k switch → новый fingerprint/cache miss;
   - evaluation mode → bypass.

5. Что минимально реализовать первым bounded UI pass.

==================================================
ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ
==================================================

1. PROJECT_STATE.md

2. docs/architecture/cache_layer_design.md

3. docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md

4. docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md

5. UI standards / Admin UI sections in PROJECT_STATE.md

6. Current frontend:
   - frontend/admin-ui/src/pages/RagPage.tsx
   - frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx
   - frontend/admin-ui/src/pages/LogsPage.tsx
   - frontend/admin-ui/src/pages/EvaluationPage.tsx
   - frontend/admin-ui/src/navigation/routes.ts
   - frontend/admin-ui/src/api/client.ts
   - frontend/admin-ui/src/styles/globals.css

7. Current backend/API:
   - admin_api/routes/*
   - admin_api/deps.py
   - services/rag_query_service.py
   - services/rag_types.py
   - services/cache/*

==================================================
ЧТО НУЖНО СДЕЛАТЬ
==================================================

1. Проанализировать текущие Admin UI паттерны
--------------------------------------------------

Найти:
- где лучше разместить cache observability;
- какие существующие компоненты/паттерны переиспользовать;
- какие страницы уже показывают RAG telemetry;
- где не надо дублировать Logs.

Важно:
Cache UI не должен стать копией Logs.
Он должен быть operator-facing optimization console.

==================================================

2. Спроектировать user workflow
--------------------------------------------------

Описать сценарий оператора:

A. Baseline query
- оператор задаёт RAG-запрос;
- видит cache miss;
- видит latency;
- видит retrieval backend/generation/key prefix.

B. Repeat query
- оператор повторяет тот же запрос;
- видит cache hit;
- видит уменьшение retrieval latency;
- видит skipped retrieval/backend call если это фиксируется.

C. Change top_k / backend
- оператор меняет retrieval параметр;
- видит новый fingerprint;
- cache miss ожидаем.

D. Reindex / generation bump
- оператор переиндексирует документы;
- старый cache не используется;
- видит invalidation/generation change.

E. Evaluation mode
- оператор видит, что Evaluation/RAGAS bypass cache;
- это объясняется как reproducibility protection.

==================================================

3. Спроектировать UI структуру
--------------------------------------------------

Нужно предложить конкретный low-fidelity layout.

Варианты:
- отдельная страница "Оптимизация";
- вкладка "Кэш" внутри RAG;
- секция "Cache diagnostics" в Retrieval Settings;
- комбинированно: short cache status в Retrieval Settings + full details в RAG.

Нужно выбрать рекомендуемый вариант и объяснить почему.

Ожидаемые блоки:

- cache status summary;
- recent RAG sessions with cache badges;
- selected session detail with cache telemetry;
- comparison panel: previous identical query / current query;
- invalidation/generation panel;
- evaluation bypass explanation;
- raw diagnostics collapsed JSON.

==================================================

4. API / data needs
--------------------------------------------------

Определить:
- достаточно ли текущих processing_logs/details;
- нужны ли новые admin endpoints;
- нужны ли новые fields в existing endpoints;
- какие поля UI может взять уже сейчас;
- какие поля нужно добавить минимально.

Важно:
не предлагать schema migration без необходимости.

==================================================

5. Acceptance criteria для первого UI implementation pass
--------------------------------------------------

Сформулировать критерии:

- оператор может визуально отличить cache hit от miss;
- оператор видит cache latency;
- оператор видит retrieval generation/backend/key prefix;
- оператор видит cache bypass в evaluation sessions;
- UI не скрывает missing telemetry;
- повторный одинаковый запрос можно проверить через RAG/Telegram + Admin UI.

==================================================

6. Report / lesson framing
--------------------------------------------------

Сформулировать, как это будет описано в отчете PEr07:

Не:
"мы сделали cache.json".

А:
"в Assistant Flow создан контур наблюдаемой оптимизации retrieval: оператор видит cache hit/miss, latency, invalidation и evaluation bypass".

==================================================
НЕ ДЕЛАТЬ
==================================================

На этом этапе НЕ реализовывать:
- frontend code;
- backend code;
- schema migration;
- Redis;
- final answer cache;
- embedding cache;
- distributed cache;
- broad UI redesign.

Это design/spec pass.

==================================================
DELIVERABLES
==================================================

Создать документ:

docs/architecture/cache_observability_console_design.md

Создать session log:

docs/cursor_sessions/YYYY-MM-DD_cache_observability_console_design.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

В конец session log добавить:
1. analyzed files;
2. UI placement decision;
3. proposed operator workflow;
4. proposed UI layout;
5. API/data needs;
6. first implementation pass scope;
7. report framing for PEr07;
8. risks/warnings;
9. git status.

==================================================
ОТВЕТ
==================================================

В ответе предоставить только:
1. changed files;
2. recommended UI placement;
3. first implementation pass scope;
4. API/data needs;
5. report framing;
6. git status.

Commit НЕ выполнять.

---

## analyzed files

- `PROJECT_STATE.md` (разделы про Admin UI philosophy, RAG operational decisions, retrieval observability contract, cache invalidation strategy)
- `docs/architecture/cache_layer_design.md`
- `docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md`
- `docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md`
- `frontend/admin-ui/src/pages/RagPage.tsx`
- `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx`
- `frontend/admin-ui/src/pages/LogsPage.tsx`
- `frontend/admin-ui/src/pages/EvaluationPage.tsx`
- `frontend/admin-ui/src/navigation/routes.ts`
- `frontend/admin-ui/src/api/client.ts`
- `frontend/admin-ui/src/styles/globals.css`
- `admin_api/routes/logs.py`
- `admin_api/routes/retrieval.py`
- `admin_api/routes/evaluation.py`
- `admin_api/deps.py`
- `services/rag_types.py`
- `services/evaluation_admin_service.py`

## UI placement decision

Рекомендуется комбинированная модель:
- короткий cache status в `Retrieval Settings`;
- полный `Cache Diagnostics Mode` в `RAG`;
- явный cache bypass indicator в `Evaluation`.

Почему:
- сохраняется session-centric операторская проверка hit/miss/invalidation в RAG;
- не дублируется общий execution journal из Logs;
- config/policy контекст остаётся рядом с retrieval controls.

## proposed operator workflow

1. Baseline query: первый RAG-запрос -> `MISS`, latency, backend/generation/key prefix.
2. Repeat query: повтор -> `HIT`, сравнение latency с baseline.
3. Parameter shift: смена `top_k` или backend -> новый fingerprint, ожидаемый `MISS`.
4. Reindex/generation bump: повтор после изменения retrieval space -> старый cache не используется.
5. Evaluation mode: в evaluation-сессиях виден policy `bypass` как reproducibility protection.

## proposed UI layout

### Retrieval Settings
- Cache status summary (enabled/disabled, generation, TTL, backend).
- Invalidation hints и ссылка в RAG diagnostics mode.

### RAG
- Cache summary по окну;
- список сессий с cache badges (`HIT/MISS/N/A`);
- detail-блок cache telemetry;
- comparison panel (previous identical query vs current);
- invalidation/generation panel;
- evaluation bypass explainer;
- raw diagnostics JSON (collapsed).

### Evaluation
- чёткий `Cache Policy` indicator (`evaluation_cache_bypass`, `evaluation_cache_policy`).

## API/data needs

Достаточно текущих endpoint для pass-1:
- `GET /api/logs/recent` (processing_logs.details уже содержит cache telemetry);
- `GET /api/retrieval/overview` (config/status snapshot);
- `GET /api/evaluation/rag-turns/{execution_id}` (retrieval_diag/metadata с bypass policy).

Нужны только минимальные enrichments (без migration):
- нормализованный `cache_state` (`hit/miss/na`) в list-представлении;
- стабильная прокладка evaluation cache policy полей в UI detail.

Новые admin endpoint и schema migration на этом этапе не требуются.

## first implementation pass scope

Bounded scope:
1. Добавить в `Retrieval Settings` компактный cache status summary.
2. Расширить `RAG` страницу cache diagnostics mode блоками (badges, detail telemetry, comparison, invalidation panel).
3. Добавить в `Evaluation` явную индикацию cache bypass policy.
4. Сохранить явную видимость telemetry gaps (`N/A`), без сокрытия отсутствующих полей.

Out of scope:
- новая страница `Optimization`;
- backend refactor;
- агрегирующие analytics endpoint;
- broad redesign.

## report framing for PEr07

Рекомендуемая формулировка:

"В Assistant Flow создан контур наблюдаемой оптимизации retrieval: оператор в Admin UI видит cache hit/miss, cache latency, generation/backend fingerprint, invalidation-поведение и evaluation cache bypass."

## risks/warnings

- риск перегрузить RAG page и потерять фокус на операционном сценарии;
- older logs могут не содержать часть cache telemetry (нужны явные gap markers);
- comparison "identical query" ограничен окном загруженных сессий;
- нельзя смешивать interpretation evaluation latency с production latency без учета bypass policy.

## git status

```text
 M PROJECT_STATE.md
 M admin_api/deps.py
 M scripts/evaluate_rag_smoke.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/invalidate.py
 M services/cache/retrieval_cache_key.py
 M services/evaluation/rag_evaluation_service.py
 M services/evaluation_service.py
 M services/rag_query_service.py
 M services/rag_types.py
?? docs/architecture/cache_layer_design.md
?? docs/architecture/cache_observability_console_design.md
?? docs/architecture/operational_discipline_assistant_flow_ru.md
?? docs/cursor_sessions/2026-05-16_project_state_rag_quality_analysis_update.md
?? docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md
?? docs/cursor_sessions/2026-05-17_cache_observability_console_design.md
?? docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md
```

