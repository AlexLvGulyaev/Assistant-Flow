# Session: Cache config audit & unification (2026-05-17)

## Prompt (полная копия задачи)

# P6 Retrieval Cache — Configuration Audit & Operational Unification

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную. Если Auto явно не справляется с анализом нескольких файлов или правками React/TypeScript, только тогда предложи оператору переключение. По умолчанию не расходуй API pool без необходимости.

Общаемся, комментарии, выводы и engineering log пишем строго на русском языке.

---

## Контекст

В текущем состоянии Admin UI / Retrieval Settings содержит два отдельных блока, связанных с retrieval cache:

1. «Кэш retrieval»
2. «Cache»

Сейчас наблюдается потенциальное дублирование operational/runtime параметров и infrastructure/config параметров.

Это создаёт:
- неоднозначность для оператора;
- риск рассинхрона runtime vs UI;
- неочевидный source of truth;
- накопление долга в operational UI.

AF позиционируется как operational-first platform.
Для такой архитектуры retrieval cache control plane должен быть:
- однозначным;
- explainable;
- observability-oriented;
- без скрытых дублей.

---

# Задача

Провести полную инженерную ревизию retrieval cache configuration/runtime model.

Нужен:
- code audit;
- runtime audit;
- UI audit;
- configuration audit;
- operational semantics audit.

Никаких «косметических» исправлений без понимания runtime semantics.

---

# Важно

Это НЕ задача «просто убрать один из блоков».

Сначала:
- понять архитектуру;
- выявить source of truth;
- выявить реальные runtime зависимости;
- определить, какие параметры:
  - operational;
  - effective runtime;
  - infrastructure-only;
  - legacy;
  - future placeholders;
  - dead config.

Только после этого:
- предложить новую структуру;
- затем реализовать cleanup/unification.

---

# Обязательно прочитать

1. PROJECT_STATE.md

2. docs/architecture/cache_layer_design.md

3. docs/architecture/cache_observability_console_design.md

4. docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md

5. docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md

6. docs/cursor_sessions/2026-05-17_cache_observability_console_design.md

7. docs/cursor_sessions/2026-05-17_cache_observability_ui_pass.md

8. Current frontend:
- frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx
- frontend/admin-ui/src/pages/RagPage.tsx
- frontend/admin-ui/src/pages/EvaluationPage.tsx
- frontend/admin-ui/src/components/CacheObservabilityBadge.tsx
- frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx
- frontend/admin-ui/src/components/EvaluationCachePolicyPanel.tsx
- frontend/admin-ui/src/utils/cacheObservability.ts
- frontend/admin-ui/src/api/client.ts
- frontend/admin-ui/src/styles/globals.css

9. Current backend/config/cache:
- utils/config.py
- admin_api/routes/retrieval.py
- admin_api/deps.py
- services/cache/*
- services/retrieval/*
- services/rag_query_service.py
- services/rag_types.py
- services/evaluation_service.py
- services/evaluation/rag_evaluation_service.py
- docker-compose.portfolio.yml
- .env.example
- .env.portfolio-test, если доступен в локальном контуре

10. Legacy reference:
- legacy/PEr07_source
- legacy/PEr08_source

Legacy — только reference material. Не переносить код напрямую.

---

# Обязательный scope ревизии

## 1. Runtime source of truth

Определить:
- кто реально управляет retrieval cache runtime;
- где хранится effective state;
- env vs DB vs runtime singleton vs service state;
- есть ли runtime overrides;
- что authoritative.

Нужна явная схема.

---

## 2. Полная карта параметров

Построить mapping:

- UI field
- runtime variable
- config/env field
- DB override
- actual usage
- code location
- semantics

Для каждого параметра.

Особенно проверить:

- ENABLE_RETRIEVAL_CACHE
- ENABLE_ANSWER_CACHE
- RETRIEVAL_CACHE_TTL_SECONDS
- ANSWER_CACHE_TTL_SECONDS
- RAG_RETRIEVAL_GENERATION
- CACHE_DB_PATH
- generation/revision
- effective TTL
- fingerprint/backend
- status enabled/disabled

---

## 3. Проверка дублирования

Определить:

что является:
- exact duplicate;
- effective runtime mirror;
- infrastructure config reflection;
- stale UI field;
- placeholder;
- dead config;
- future feature stub.

---

## 4. Retrieval cache invalidation semantics

Проверить:
- как работает generation;
- кто делает bump;
- как происходит invalidation;
- invalidates ли:
  - reindex;
  - backend switch;
  - top_k change;
  - retrieval settings change;
  - chunking change;
  - retrieval space change.

Проверить не только UI, но и реальный runtime behavior.

---

## 5. SQLite cache architecture review

Проверить текущую реализацию:
- schema;
- access pattern;
- concurrency assumptions;
- persistence semantics;
- lifecycle.

Подтвердить:
используется ли SQLite осознанно как:
- local performance cache;
- non-authoritative acceleration layer.

Или это случайное legacy-решение.

---

## 6. PostgreSQL vs SQLite rationale

Нужен engineering verdict:
почему retrieval cache:
- должен/не должен жить в PostgreSQL;
- какие trade-offs;
- operational implications;
- scalability implications;
- observability implications.

---

# Целевая архитектурная модель

После ревизии предложить unified operational structure.

Предварительное направление:

Вместо двух partially duplicated panels:

- единый Retrieval Cache operational block;
- runtime state;
- effective policy;
- invalidation semantics;
- infrastructure details;
- optional advanced/raw config section.

Но:
НЕ внедрять это слепо.
Сначала доказать code/runtime audit.

---

# Требования к реализации

## Обязательно

- НЕ ломать runtime retrieval;
- НЕ ломать cache invalidation;
- НЕ ломать existing DB/platform settings;
- НЕ вводить hidden defaults;
- НЕ удалять поля без проверки использования;
- НЕ делать silent fallback semantics.

---

## Observability

После cleanup operator должен понимать:

- cache реально включен или нет;
- что source of truth;
- какой effective TTL;
- какая retrieval generation;
- почему произошёл invalidation;
- какой backend/fingerprint используется;
- где лежит cache;
- runtime это или infrastructure-only.

---

# UI/UX требования

Operational-first.

Нельзя:
- дублировать параметры;
- показывать conflicting values;
- смешивать runtime state и raw env dump;
- скрывать authoritative source.

Если нужен raw config:
- collapsible;
- advanced;
- clearly marked as infrastructure/debug info.

---

# Что можно менять

Можно менять:
- RetrievalSettingsPage UI structure;
- cache-related frontend helpers/components;
- labels/section grouping;
- docs/architecture/cache_layer_design.md;
- PROJECT_STATE.md при необходимости;
- minimal API enrichment, если audit докажет необходимость.

---

# Что нельзя менять без отдельного решения

Нельзя:
- менять storage backend cache с SQLite на PostgreSQL;
- включать answer cache;
- включать Redis;
- делать schema migration;
- удалять env/config поля без доказательства, что они dead;
- делать broad redesign страницы Retrieval Settings;
- ломать RAG page cache diagnostics;
- ломать Evaluation bypass indicator.

---

# Legacy review

Проверить reuse/влияние:
- legacy/PEr07_source
- legacy/PEr08_source

Особенно:
- SQLite cache patterns;
- retrieval cache semantics;
- answer cache semantics.

---

# Документация

После завершения:

1. Обновить:
- docs/architecture/cache_layer_design.md
- при необходимости PROJECT_STATE.md

2. Добавить:
- runtime semantics;
- source-of-truth model;
- invalidation policy;
- operational behavior;
- SQLite vs PostgreSQL rationale.

---

# Acceptance criteria

Задача считается завершённой только если:

- проведён полный audit;
- устранены реальные дубли;
- source of truth стал однозначным;
- UI больше не вводит operator в заблуждение;
- runtime semantics объяснимы;
- retrieval cache operational model документирован;
- нет silent legacy ambiguity;
- frontend build проходит.

---

# Финальный engineering log

Создать файл:

docs/cursor_sessions/YYYY-MM-DD_cache_config_audit_and_unification.md

Дата:
date +%F

В начало session log полностью помести этот prompt.

В engineering log обязательно включить:

1. analyzed files;
2. findings;
3. runtime ownership model;
4. duplicate map;
5. parameter mapping table;
6. invalidation behavior;
7. SQLite rationale;
8. PostgreSQL vs SQLite verdict;
9. список удалённых/оставленных/переименованных UI-полей;
10. migration notes;
11. operator impact;
12. frontend build result;
13. residual risks;
14. git status.

В конце файла обязательно добавь раздел:

## Operator commands / next verification commands

С конкретными командами:
- frontend build;
- точечный rebuild admin-ui в portfolio stack;
- API checks, если backend затронут;
- UI acceptance checklist;
- git status.

Использовать только portfolio stack форму:

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...

Не писать обобщённо `docker compose up -d --build` без `-p portfolio-test`.

---

# Ответ в чат Cursor

В ответе предоставить только:

1. changed files;
2. audit verdict;
3. duplicate cleanup summary;
4. final UI structure;
5. SQLite vs PostgreSQL verdict;
6. frontend build result;
7. remaining risks;
8. git status.

Commit НЕ выполнять.

---

## Engineering log

### 1. Analyzed files

- `cursor_tasks_local/2026-05-17_cache_config_audit_and_unification.md`
- `utils/config.py`, `services/admin_service.py` (`get_retrieval_overview` → `cache`)
- `services/cache/*` (`sqlite_cache.py`, `caching_retrieval_backend.py`, `retrieval_cache_key.py`, `invalidate.py`)
- `services/retrieval/factory.py`
- `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx`
- `frontend/admin-ui/src/components/RetrievalCacheSettingsPanel.tsx` (новый)
- `frontend/admin-ui/src/pages/RagPage.tsx`, `EvaluationPage.tsx` (без изменений в этом pass)
- `docs/architecture/cache_layer_design.md`

### 2. Findings

- Retrieval cache policy **authoritative только в env/AppConfig**, не в PostgreSQL.
- `RAG_RETRIEVAL_GENERATION` читается через `os.getenv` в `retrieval_cache_key.py`, не как поле `AppConfig`.
- Admin UI показывал **два блока** с пересечением: status, generation, TTL, ENABLE_* — exact duplicate для оператора.
- Answer cache — foundation stub, не hot path RAG.
- Backend API enrichment не потребовался: `/api/retrieval/overview` уже отдаёт полный `cache` dict.

### 3. Runtime ownership model

```
Operator / deploy
    → env (.env, compose)
        → AppConfig (load_config)
            → CachingRetrievalBackend (if ENABLE_RETRIEVAL_CACHE)
                → SqliteCacheStore (CACHE_DB_PATH, namespace retrieval)
        → os.getenv RAG_RETRIEVAL_GENERATION (fingerprint)
        → platform_settings PG (top_k, backend) → fingerprint miss, не cache flags
```

### 4. Duplicate map

| Было | Тип | Действие |
|------|-----|----------|
| «Кэш retrieval» status + generation + TTL + backend | effective runtime mirror | Объединено в runtime section |
| «Cache» ENABLE_* + TTL + generation + path | infrastructure reflection | Перенесено в collapsible advanced |
| Два заголовка SectionCard | exact duplicate UX | Один `Retrieval cache` |

### 5. Parameter mapping table

См. `docs/architecture/cache_layer_design.md` §12.2.

### 6. Invalidation behavior

- Explicit: `invalidate_retrieval_cache()` on vector mutations.
- Implicit: fingerprint change (top_k, backend, generation, embedding model).
- Evaluation: bypass (не затронут этим pass).

### 7. SQLite rationale

`SqliteCacheStore`: WAL, namespace `retrieval`, локальный файл — осознанный acceleration layer, не SoT.

### 8. PostgreSQL vs SQLite verdict

**Оставить SQLite.** PostgreSQL — metadata/tuning/evaluation SoT. Перенос cache entries в PG не делался (вне scope, нет operational выигрыша для portfolio single-node).

### 9. UI fields: removed / kept / renamed

**Удалено (как отдельные блоки):** SectionCard «Кэш retrieval», SectionCard «Cache» (двухколоночный env dump наверху).

**Добавлено:** `RetrievalCacheSettingsPanel` — SoT banner, runtime KV, invalidation list, link RAG, advanced `<details>` env.

**Сохранено без изменений:** RAG `RagCacheDiagnosticsPanel`, Evaluation `EvaluationCachePolicyPanel`.

### 10. Migration notes

- Только frontend/docs; backend без изменений в этом pass.
- Перезапуск сервиса по-прежнему нужен для смены cache env.
- Rebuild admin-ui в compose для отображения новой панели.

### 11. Operator impact

- Одна панель «Retrieval cache» вместо двух; меньше путаницы SoT vs env dump.
- Диагностика hit/miss — по-прежнему на странице RAG.

### 12. Frontend build result

```
cd frontend/admin-ui && npm run build
# tsc -b && vite build — OK (2026-05-17)
```

### 13. Residual risks

- Смена env без restart → UI/API могут показывать устаревшее до рестарта.
- Старые cache rows при fingerprint-only miss истекают по TTL, не удаляются сразу.
- `editable_via_api=false` — оператор не может включить cache из UI (by design).

### 14. Git status (на момент завершения pass)

См. `git status --short` в разделе Operator commands (много файлов от смежных pass в той же ветке; commit не выполнялся).

---

## Operator commands / next verification commands

### Frontend build

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
```

### Rebuild admin-ui в portfolio stack

```bash
cd /opt/assistant-flow
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui
```

### API checks (backend не менялся; smoke)

```bash
curl -sS http://localhost:PORT/api/retrieval/overview | jq '.cache'
# Ожидание: enable_retrieval_cache, rag_retrieval_generation, editable_via_api=false
```

### UI acceptance checklist

- [ ] Retrieval Settings: один блок «Retrieval cache», без второго «Cache»
- [ ] Runtime: status, generation, TTL, backend, path видны без дубля в advanced
- [ ] Advanced details: env read-only, collapsible
- [ ] Ссылка на RAG diagnostics работает
- [ ] RAG: badges HIT/MISS/BYPASS без регрессии
- [ ] Evaluation: bypass panel на месте

### Git status

```bash
cd /opt/assistant-flow && git status --short
```
