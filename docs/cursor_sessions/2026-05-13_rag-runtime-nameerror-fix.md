# Engineering log: RAG runtime NameError — `RagSourceChunk` (Memory v1.1 follow-up)

**Дата (`date +%F`):** `2026-05-13`

## Полный текст prompt

```text
Cursor, нужно сделать targeted runtime fix после Memory v1.1 stabilization.

Обязательное правило:
создай engineering log:

`docs/cursor_sessions/YYYY-MM-DD_rag-runtime-nameerror-fix.md`

Дата:

```bash
date +%F
```

В лог включить:

* полный текст prompt;
* workspace snapshot;
* git status before/after;
* root cause;
* changed files;
* smoke results;
* operator commands;
* open issues;
* commit НЕ выполнять.

==================================================
ПРОБЛЕМА
========

Во время RAG runtime flow после retrieval появился runtime exception:

```text
NameError: name 'RagSourceChunk' is not defined
```

Traceback:

```python
File "/app/services/rag_query_service.py", line 776, in answer
    sources_unique = _dedupe_sources_by_file(filtered)

File "/app/services/rag_query_service.py", line 406, in _dedupe_sources_by_file
    RagSourceChunk(
```

Контекст:

* retrieval работает;
* FAISS retrieval работает;
* memory работает;
* conversational assembly работает;
* observability работает;
* падает только post-retrieval runtime path.

==================================================
ЗАДАЧА
======

1. Найти корректный source/type definition для:

```python
RagSourceChunk
```

2. Исправить runtime/import issue в:

```text
/app/services/rag_query_service.py
```

3. Проверить:

* circular imports;
* typing/runtime import separation;
* dataclass/model availability;
* lazy import needs;
* **all** exports если используются.

4. После fix:
   прогнать RAG smoke scenario:

```text
/mode rag
Какой график работы?
А для удалённых сотрудников?
```

5. Проверить:

* retrieval проходит;
* answer generation проходит;
* followup_detected работает;
* memory lifecycle работает;
* processing_error больше нет.

6. Проверить processing_logs:
   должны появляться:

* memory_load_done
* conversational assembly telemetry
* rag_answer_done (или аналогичный success stage)

7. Проверить contamination boundaries:

* retrieval chunks НЕ пишутся в chat_messages;
* prompts НЕ persistятся;
* diagnostics НЕ загрязняют memory.

8. Если найдёшь дополнительные runtime issues,
   исправлять ТОЛЬКО:

* явно связанные с этим runtime path;
* НЕ делать refactor ради refactor.

==================================================
ФОРМАТ ОТВЕТА
=============

1. Root cause;
2. Что исправлено;
3. Какие imports/types были затронуты;
4. Smoke result;
5. Confirmed operational invariants;
6. Path к engineering log;
7. git status.

Commit НЕ выполнять.

==================================================
ВАЖНО
=====

Все operator commands в конце log давать только через canonical contour:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

НЕ использовать compose-команды без:

```bash
-p portfolio-test
```
```

## Workspace snapshot

Фрагмент корня `/opt/assistant-flow` (`ls -1 | head -35`):

```text
Dockerfile
PROJECT_STATE.md
README.md
admin_api
core
data
database
docker-compose.assistant.yml
docker-compose.portfolio.yml
docs
frontend
interfaces
providers
repositories
scripts
services
utils
```

## Git status

### Before (фиксация на начало задачи)

```text
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/app.py
 M admin_api/deps.py
 M frontend/admin-ui/src/App.tsx
 M frontend/admin-ui/src/api/client.ts
 M frontend/admin-ui/src/navigation/routes.ts
 M frontend/admin-ui/src/pages/RagPage.tsx
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
 M interfaces/telegram_bot.py
 M repositories/processing_logs_repository.py
 M repositories/session_repository.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/retrieval_cache_key.py
 M services/chat_session_service.py
 M services/memory/conversation_memory_service.py
 M services/rag_query_service.py
 M services/rag_types.py
 M utils/config.py
 M utils/telegram_user_state.py
?? admin_api/routes/sessions.py
?? docs/cursor_sessions/2026-05-13_*.md (несколько)
?? frontend/admin-ui/src/pages/MemoryPage.tsx
?? scripts/test_memory_*.py
?? scripts/test_retrieval_backend_identity_smoke.py
?? services/conversational_context_assembly.py
?? services/memory_observability_service.py
```

### After

Тот же список, плюс:

- изменён `services/rag_query_service.py` (восстановлены импорты);
- добавлен этот файл: `docs/cursor_sessions/2026-05-13_rag-runtime-nameerror-fix.md`.

**Commit не выполнялся.**

## Root cause

При интеграции Memory v1.1 в `services/rag_query_service.py` блок `from services.rag_types import (...)` был **заменён** импортом из `services.conversational_context_assembly`, но типы **`RagSourceChunk`**, **`RagQueryResult`**, **`RagRequestDiagnostics`**, **`RagRetrievedChunkDiagnostics`** по-прежнему используются в модуле (`_sources_from_results`, `_dedupe_sources_by_file`, `_build_diagnostics`, `answer`, и т.д.). В результате в рантайме при первом обращении к имени **`RagSourceChunk`** в `_dedupe_sources_by_file` возникал **`NameError`**.

Определение типа: **`services/rag_types.py`** — dataclass **`RagSourceChunk`**.

## Changed files

| File | Change |
|------|--------|
| `services/rag_query_service.py` | Восстановлен `from services.rag_types import (RagQueryResult, RagRequestDiagnostics, RagRetrievedChunkDiagnostics, RagSourceChunk)` рядом с импортом assembly. |

## Проверки (imports / circular)

- **`services/rag_types.py`** не импортирует `rag_query_service` — циклического импорта нет.
- Lazy import не требуется: модули вер верхнего уровня достаточно.

## Smoke results

| Проверка | Результат |
|----------|-----------|
| `python3 -m py_compile services/rag_query_service.py` | **OK** |
| Полный Telegram-сценарий `/mode rag` + два вопроса в этом окружении | **Не выполнялся** (нет запущенного portfolio stack / Telegram в sandbox CI). |
| `docker exec portfolio-test-assistant-flow-1 …` | См. **Operator commands** — выполнить на стенде оператором после rebuild. |

Инварианты по коду (без изменений в этом патче): `persist_telegram_dialog_turn_best_effort` по-прежнему пишет только user/assistant текст; diagnostics остаются в `processing_logs`, не в `chat_messages`.

## Operator commands / next verification commands

Только canonical portfolio contour (**`-p portfolio-test`**):

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

Проверка контейнеров (ожидается префикс `portfolio-test-`):

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Smoke RAG внутри приложения (подставить нужный скрипт при наличии; иначе ручной Telegram):

```bash
docker exec portfolio-test-assistant-flow-1 python -m py_compile services/rag_query_service.py
```

После ручного прогона в Telegram убедиться в логах стадиях `memory_load_done`, telemetry assembly в `rag_answer_done` / `details`, отсутствии `processing_error` на успешном ответе.

```bash
git status -sb
```

## Open issues

- **E2E** сценарий из prompt и сверка `processing_logs` в PostgreSQL требуют **живого** portfolio stack и конфигурации бота — вне объёма автоматического прогона в текущей среде агента.
- На хосте без зависимостей (`langchain_core` и др.) полный `import services.rag_query_service` может падать — это ожидаемо; эталон проверки — **контейнер** `portfolio-test-assistant-flow-1`.
