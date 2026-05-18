# Промпт для Cursor: Retrieval Cache Operationalization Pass

Используй Codex 5.3.

Прочитай и выполни. Общаемся, комментарии и отчёты пишем строго на русском языке.

Продолжаем subsystem-scoped sprint:
PEr07 / Retrieval Optimization / Cache Layer.

Контекст:
предыдущий architectural pass завершён.
Подготовлен:
- docs/architecture/cache_layer_design.md
- audit legacy/PEr07_source
- retrieval cache analysis
- invalidation model
- observability contract
- evaluation implications

Теперь нужен первый bounded implementation pass.

ВАЖНО:
это НЕ broad cache refactor.
НЕ distributed cache.
НЕ Redis migration.
НЕ final answer cache.

Работаем только с retrieval cache operationalization.

==================================================
ЦЕЛЬ
==================================================

Превратить существующий retrieval cache foundation в operationally observable и безопасный subsystem.

Основной принцип:
correctness > hit ratio.

==================================================
ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ
==================================================

1. PROJECT_STATE.md

2. docs/architecture/cache_layer_design.md

3. docs/architecture/*
Особенно:
- operational discipline
- cursor workflow regulation
- evaluation architecture

4. docs/cursor_sessions/*
Особенно:
- cache architecture design
- retrieval investigations
- RAGAS findings

==================================================
ЧТО НУЖНО СДЕЛАТЬ
==================================================

1. Retrieval cache observability normalization
--------------------------------------------------

Проверить и нормализовать logging contract.

Нужно убедиться, что retrieval cache consistently пишет:

- cache_hit
- cache_miss
- cache_layer
- cache_latency_ms
- retrieval_cache_generation
- retrieval_cache_backend
- retrieval_cache_key_hash_prefix
- cache_invalidation_reason (если применимо)

Telemetry должна попадать:
- в processing_logs.details
- retrieval diagnostics
- operational observability path

ВАЖНО:
не плодить отдельный logging subsystem.

==================================================

2. Invalidation discipline hardening
--------------------------------------------------

Проверить:

- invalidate hooks;
- generation bump handling;
- backend-sensitive invalidation;
- top_k-sensitive invalidation;
- embedding-model-sensitive invalidation.

Особенно:
что retrieval cache НЕ reused после:
- reindex;
- backend switch;
- retrieval generation change.

==================================================

3. Evaluation bypass
--------------------------------------------------

Нужно убедиться:

- evaluation/evaluation_ragas path умеет bypass retrieval cache;
- bypass явно фиксируется в diagnostics;
- reproducibility не ломается.

Если bypass уже partially реализован:
- проверить;
- задокументировать;
- нормализовать observability.

==================================================

4. Feature flags / rollback safety
--------------------------------------------------

Проверить:
- ENABLE_RETRIEVAL_CACHE
- graceful disable behavior
- fallback behavior

Нужен простой rollback:
feature flag OFF -> runtime работает штатно.

==================================================

5. Smoke verification
--------------------------------------------------

Нужны verification сценарии:

1.
cache miss → retrieval → cache set

2.
повторный identical retrieval → cache hit

3.
reindex/retrieval generation bump → old cache invalid

4.
backend switch → cache invalid

5.
evaluation mode → bypass cache

==================================================
НЕ ДЕЛАТЬ
==================================================

НЕ делать:
- final response cache;
- embedding cache;
- Redis;
- distributed cache;
- async workers;
- UI redesign;
- schema migration без необходимости;
- broad refactor.

==================================================
DELIVERABLES
==================================================

Создать session log:

docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_operationalization_pass.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

В конце session log добавить:
1. changed files;
2. observability changes;
3. invalidation findings;
4. evaluation bypass findings;
5. smoke verification results;
6. rollback verification;
7. risks/warnings;
8. git status.

==================================================
ОТВЕТ
==================================================

В ответе предоставить только:
1. changed files;
2. retrieval cache operational status;
3. invalidation verification summary;
4. evaluation bypass result;
5. remaining risks;
6. git status.

Commit НЕ выполнять.

---

## changed files

- `services/cache/retrieval_cache_key.py`
- `services/cache/caching_retrieval_backend.py`
- `services/cache/invalidate.py`
- `services/rag_query_service.py`
- `services/rag_types.py`
- `services/evaluation_service.py`
- `services/evaluation/rag_evaluation_service.py`
- `admin_api/deps.py`
- `scripts/evaluate_rag_smoke.py`

## observability changes

Нормализованы retrieval-cache telemetry поля:
- `retrieval_cache_hit`
- `retrieval_cache_miss`
- `cache_layer`
- `cache_latency_ms`
- `retrieval_cache_generation`
- `retrieval_cache_backend`
- `retrieval_cache_key_hash_prefix`
- `retrieval_cache_fingerprint_backend`

Где теперь доступны:
- `services/cache/caching_retrieval_backend.py`: thread-local diag + stdout cache log;
- `services/rag_query_service.py`: прокидывание в diagnostics/routing extras;
- `services/rag_types.py`: сериализация в `to_log_details()` и stdout diagnostics;
- `admin_api/deps.py`: добавлены в `_PRESERVED_DETAIL_KEYS` для operational path;
- `services/cache/invalidate.py`: лог инвалидации нормализован через `cache_invalidation_reason`.

## invalidation findings

Проверено и подтверждено:
- invalidate hooks уже есть в `CachingRetrievalBackend` для:
  - `reset_for_full_reindex()`
  - `add_documents()`
  - `delete_vectors_for_document_before_reindex()`
- generation-sensitive invalidation подтверждена через fingerprint test (`RAG_RETRIEVAL_GENERATION` влияет на ключ).
- backend-sensitive invalidation подтверждена через fingerprint test (смена backend меняет ключ).
- top_k-sensitive invalidation подтверждена через fingerprint test (смена `top_k` меняет ключ).
- embedding-model-sensitive invalidation сохранена в fingerprint (`openai_embedding_model` включён в ключ).

## evaluation bypass findings

Сделано:
- `services/evaluation_service.py`:
  - `build_rag_query_service_for_eval()` теперь принудительно выключает `enable_retrieval_cache`;
  - в `split_log_details_to_blobs()` добавлены:
    - `evaluation_cache_bypass=true`
    - `evaluation_cache_policy="retrieval_cache_disabled"`
- `services/evaluation/rag_evaluation_service.py`:
  - в diagnostics summary добавлены:
    - `evaluation_cache_bypass=true`
    - `evaluation_cache_policy="retrieval_cache_disabled"`
- `scripts/evaluate_rag_smoke.py`:
  - bootstrap evaluation run принудительно выполняется с `enable_retrieval_cache=false`.

Итог:
- evaluation path теперь явно фиксирует bypass policy в диагностике.

## smoke verification results

1) Cache foundation smoke  
Команда: `python3 scripts/test_cache_foundation_smoke.py`  
Результат: `OK: test_cache_foundation_smoke`

2) Backend/top_k key invalidation check  
Результат:
- `backend_switch_invalid=True`
- `topk_switch_invalid=True`

3) Retrieval generation bump invalidation check  
Результат:
- `generation_bump_invalid=True`

4) Syntax safety  
Команда: `python3 -m py_compile ...` (обновлённые модули)  
Результат: успешно, ошибок нет.

5) Full runtime smoke (cache hit/miss через live retrieval + evaluation API path)
- Ограничение текущего окружения: отсутствуют runtime зависимости (`langchain_openai`, `psycopg`) для полного end-to-end локального запуска.
- Архитектурный контракт и unit/smoke-level проверки инвалидации выполнены.

## rollback verification

Rollback-модель сохранена:
- флаг `ENABLE_RETRIEVAL_CACHE=false` оставляет runtime path без cache wrapper (`build_retrieval_backend` возвращает чистый backend).
- Изменения не ломают fallback behavior при отключённом кеше (не добавлен новый hard dependency).
- Evaluation path дополнительно принудительно bypass-ит retrieval cache независимо от global flag.

## risks/warnings

- В локальном sandbox окружении отсутствуют зависимости для полного e2e runtime smoke (`langchain_openai`, `psycopg`).
- `cache_invalidation_reason` логируется на invalidate path, но не в каждом `rag_answer_done`; это ожидаемо для event-driven invalidate модели.
- Для полной production-верификации нужны контейнерные smoke сценарии из task-а (miss/hit/reindex/backend-switch/eval-bypass) в штатном runtime окружении.

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
?? docs/architecture/operational_discipline_assistant_flow_ru.md
?? docs/cursor_sessions/2026-05-16_project_state_rag_quality_analysis_update.md
?? docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md
?? docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md
```

