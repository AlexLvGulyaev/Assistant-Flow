# Engineering log: Memory v1.2 — conversational / meta-intent routing

**Дата (`date +%F`):** `2026-05-13`

## Полный текст prompt

```text
Cursor, следующий этап:
Memory v1.2 — conversational / meta-intent routing.

Это развитие AF уже вне рамок учебного задания.

Цель:
научить Assistant Flow отличать обычный RAG-запрос к базе знаний от вопроса о текущем диалоге / памяти.

Примеры meta-intent queries:

```text
О чем был мой предыдущий вопрос?
Что мы обсуждали?
Что ты уже сказал про индексацию?
Какие темы мы затронули?
Повтори мой прошлый вопрос.
Кратко резюмируй нашу беседу.
```

Такие запросы НЕ должны уходить в vector retrieval как обычный RAG-запрос.

Они должны обрабатываться через PG-backed short-term conversation memory.

==================================================
ОБЯЗАТЕЛЬНАЯ ДИСЦИПЛИНА
=======================

Создай engineering log:

```text
docs/cursor_sessions/YYYY-MM-DD_memory-v1_2-meta-intent-routing.md
```

Дата:

```bash
date +%F
```

В log включить:

* полный текст prompt;
* workspace snapshot;
* git status before/after;
* architecture decisions;
* changed files;
* smoke scenarios;
* contamination audit;
* operator commands / next verification commands;
* open issues;
* commit НЕ выполнять.

Все operator commands только через canonical contour:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python <script>
```

НЕ использовать `docker compose up` без `-p portfolio-test`.

==================================================
КОНТЕКСТ
========

Уже реализовано:

* PG-backed short-term memory;
* `/clear` / `/reset` через session rotation;
* Memory observability + Sessions UI;
* contamination audit;
* retrieval-aware conversational context assembly;
* follow-up detection;
* separate history/retrieval budgets;
* RAG diagnostics fields.

Текущий gap:
вопросы о самом диалоге сейчас уходят в RAG retrieval и могут получать fallback:

```text
О чем был мой предыдущий вопрос?
→ В базе знаний нет достаточно релевантной информации
```

Это неверно для conversational assistant.

==================================================
ГЛАВНАЯ ЦЕЛЬ
============

Добавить lightweight routing перед RAG retrieval:

```text
incoming query
→ detect meta-memory intent?
   yes → answer from PG conversation memory
   no  → normal RAG path
```

==================================================

1. META-INTENT DETECTION
   ==================================================

Добавить детерминированную heuristic function, например:

```python
detect_memory_meta_intent(query: str) -> MemoryMetaIntent | None
```

Поддержать минимум intents:

1. previous_question

   * "о чем был мой предыдущий вопрос"
   * "что я спросил до этого"
   * "повтори мой прошлый вопрос"

2. conversation_summary

   * "что мы обсуждали"
   * "какие темы мы затронули"
   * "резюмируй нашу беседу"

3. previous_answer_about_topic

   * "что ты уже сказал про X"
   * "что было сказано про X"
   * "что известно из нашей беседы про X"

Heuristic only.
Без LLM classifier.
Без embeddings.
Без semantic memory.

==================================================
2. MEMORY-META ANSWER SERVICE
=============================

Реализовать отдельный service/helper, например:

```text
services/memory_meta_answer_service.py
```

Он должен:

* читать recent clean turns из PG через существующий ConversationMemoryService / repositories;
* не ходить в vector retrieval;
* не читать processing_logs как источник ответа;
* не использовать KB chunks;
* формировать компактный ответ пользователю.

Для MVP можно сделать deterministic answers:

previous_question:

```text
Ваш предыдущий вопрос был: "..."
```

conversation_summary:

```text
За последние N реплик мы обсуждали:
- ...
- ...
```

previous_answer_about_topic:

* найти последние turns, где user/assistant content содержит topic substring;
* если найдено, кратко вернуть найденные фрагменты;
* если не найдено: "В текущей беседе я не нашёл информации по этой теме."

Важно:
не делать giant dumps.
Ограничить:

* max turns scanned;
* max preview chars;
* max bullet count.

==================================================
3. INTEGRATION POINT
====================

В Telegram RAG path:

До вызова `rag_service.answer(...)`:

1. загрузить / определить PG session как сейчас;
2. проверить meta-intent;
3. если meta-intent detected:

   * сформировать ответ из memory;
   * отправить пользователю;
   * сохранить clean user query + clean assistant answer в `chat_messages`;
   * залогировать lifecycle;
   * НЕ вызывать retrieval;
   * НЕ вызывать LLM;
   * НЕ создавать RAG fallback.

Если meta-intent не detected:

* обычный RAG path без изменений.

==================================================
4. OBSERVABILITY
================

Добавить safe processing_logs stages:

```text
memory_meta_intent_detected
memory_meta_answer_done
memory_meta_answer_empty
memory_meta_error
```

details только:

* intent
* session_id
* user_id
* telegram_user_id
* scanned_turns
* matched_turns
* latency_ms
* answer_chars
* no message full text

Не логировать:

* full conversation;
* full prompts;
* retrieved chunks;
* diagnostics dumps.

==================================================
5. ADMIN UI / LOGS
==================

Минимально:

* убедиться, что stages не теряются в Logs;
* если есть route/modality classification, route может быть `memory_meta` или modality_route `memory`;
* без большого redesign.

Опционально:

* Memory page может показывать recent memory_meta events.

Но не делать большой UI-эпик.

==================================================
6. CONTAMINATION SAFEGUARDS
===========================

Проверить:

* meta answers сохраняются как обычный assistant message;
* в `chat_messages` не попадают processing_logs/details;
* в `chat_messages` не попадают raw dumps всей истории;
* нет retrieval chunks;
* нет system prompts.

==================================================
7. SMOKE TESTS
==============

Добавить smoke script:

```text
scripts/test_memory_v1_2_meta_intent_routing_smoke.py
```

Проверить:

* detection previous_question;
* detection conversation_summary;
* detection previous_answer_about_topic;
* false positive guard: обычный KB query не должен стать meta;
* deterministic answer builder не делает giant dump;
* no retrieval call marker in meta path if удобно протестировать.

Ручные Telegram scenarios:

A.

```text
/mode rag
Каков функционал системы Assistant Flow?
А как там построена индексация документов?
О чем был мой предыдущий вопрос?
```

Ожидаем:

```text
Ваш предыдущий вопрос был: "А как там построена индексация документов?"
```

B.

```text
Что мы обсуждали?
```

Ожидаем summary по текущей сессии.

C.

```text
Что ты уже сказал про индексацию?
```

Ожидаем ответ по recent conversation memory, без retrieval fallback.

D.
Обычный RAG:

```text
Каков функционал системы Assistant Flow?
```

Ожидаем обычный retrieval path.

==================================================
8. НЕ ДЕЛАТЬ
============

НЕ делать:

* semantic memory;
* vectorized dialog memory;
* memory embeddings;
* LLM-based meta-intent classifier;
* automatic long-term user facts extraction;
* summarization memory storage;
* cross-session semantic retrieval;
* major Admin UI redesign.

==================================================
9. RESULT FORMAT
================

В ответе Cursor должен дать:

1. Что реализовано;
2. Где находится detector/service;
3. Как встроено в Telegram RAG path;
4. Какие stages/log fields добавлены;
5. Какие smoke tests прошли;
6. Какие contamination safeguards подтверждены;
7. Какие ограничения остались;
8. Path к engineering log;
9. git status.

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

Корень репозитория `/opt/assistant-flow`: `interfaces/`, `services/`, `admin_api/`, `frontend/admin-ui/`, `scripts/`, `docs/cursor_sessions/`, compose `docker-compose.portfolio.yml`, и т.д.

## Git status

### Before (типичное состояние начала задачи в среде)

Локальная ветка `main` с несохранёнными изменениями в смежных файлах (полный список зависит от рабочей копии; для этого этапа релевантны только новые/изменённые файлы v1.2).

### After

```text
## main...origin/main [ahead 15]
 M admin_api/deps.py
 M frontend/admin-ui/src/utils/operationalLabels.ts
 M interfaces/telegram_bot.py
?? scripts/test_memory_v1_2_meta_intent_routing_smoke.py
?? services/memory_meta_answer_service.py
?? services/memory_meta_intent.py
```

Плюс добавлен этот файл лога (untracked). **Commit не выполнялся.**

## Architecture decisions

1. **Роутинг до retrieval:** после `load_telegram_rag_history_for_llm` вызывается детерминированный `detect_memory_meta_intent(text)`; при совпадении и наличии `session_id` / `user_id` из PG — **ветка memory_meta** без `rag_service.answer`, без LLM, без vector retrieval.
2. **Источник ответа:** только список `history` (чистые user/assistant turns из PG), через `build_memory_meta_reply` — лимиты `max_turns_scan`, `max_preview_chars`, `max_bullets`.
3. **Тема «про X»:** сопоставление с телом реплик через `_topic_matches_body` (substring + грубый prefix по словам из-за русских окончаний).
4. **Логи:** стадии `memory_meta_intent_detected`, `memory_meta_answer_done` / `memory_meta_answer_empty`, `memory_meta_error`; в `details` только скаляры/короткие поля + `answer_text` усечённый как в RAG (`_safe_answer_text_for_log`). Полная история и чанки не пишутся.
5. **Modality для Admin API:** `infer_modality_route` возвращает **`rag`** для `route=memory_meta` и стадий `memory_meta_*`, чтобы сессии оставались в привычном RAG-фильтре логов.
6. **Без PG session:** meta-ветка не активируется (`sid_str`/`uid_str` пустые) — поведение как раньше (обычный RAG).

## Changed files

| Path | Назначение |
|------|------------|
| `services/memory_meta_intent.py` | `MemoryMetaIntent`, `MemoryMetaIntentKind`, `detect_memory_meta_intent` |
| `services/memory_meta_answer_service.py` | `build_memory_meta_reply`, лимиты ответа, `_topic_matches_body` |
| `interfaces/telegram_bot.py` | Ветвление в RAG handler: meta vs `rag_service.answer`; persist + lifecycle |
| `admin_api/deps.py` | `infer_modality_route` + `_PRESERVED_DETAIL_KEYS` для slim API |
| `frontend/admin-ui/src/utils/operationalLabels.ts` | RU-подписи стадий `memory_*` / `memory_meta_*` |
| `scripts/test_memory_v1_2_meta_intent_routing_smoke.py` | Статический smoke детектора и билдера |

## Smoke scenarios

| Автоматический smoke | Результат |
|----------------------|-----------|
| `python3 scripts/test_memory_v1_2_meta_intent_routing_smoke.py` | **OK** (KB не meta; previous_question; summary; topic; bounded summary) |
| `python3 -m py_compile interfaces/telegram_bot.py` | **OK** |
| `npm run build` в `frontend/admin-ui` | **OK** |

Ручные сценарии A–D из prompt — на стенде с Telegram + portfolio (см. operator commands).

## Contamination audit

- **Persist:** только `user_text` (мета-запрос) и **готовый** `assistant_text` (детерминированный ответ), через существующий `persist_telegram_dialog_turn_best_effort` — без `processing_logs`, без retrieval chunks, без system prompts.
- **Meta path:** не вызывается `rag_service.answer` → нет `RagRequestDiagnostics`/чанков в этом execution для ответа (стадии `rag_answer_done` нет).
- **Логи:** в `details` нет полного дампа диалога; `answer_text` усечён тем же хелпером, что и RAG.

## Operator commands / next verification commands

Только canonical portfolio contour:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Проверка импорта/смока в контейнере приложения:

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_memory_v1_2_meta_intent_routing_smoke.py
```

Ручной Telegram (после деплоя образа с этим кодом):

```text
/mode rag
… сценарии A–D из пользовательского prompt …
```

Проверка логов в БД / Admin UI: наличие `memory_meta_intent_detected` → `memory_meta_answer_done` (или `_empty` / `_error`), отсутствие `rag_answer_done` на том же `execution_id` для meta-запроса.

```bash
git status -sb
```

## Open issues

- При **выключенной** PG-памяти meta-intent **не** обрабатывается (нет `sid_str`); запрос уходит в обычный RAG.
- Сопоставление темы по русским формам слова — **эвристика**, возможны пропуски/лишние совпадения.
- Нет отдельного маркера в логах «retrieval skipped» кроме отсутствия `rag_answer_done` — при необходимости можно добавить явное поле в `memory_meta_answer_done` в будущем.
