# Engineering log: Memory v1.1 — retrieval-aware conversational context

## Timestamp

- **UTC:** `2026-05-13T19:13:26Z` (recorded at log finalization)
- **Session date (`date +%F`):** `2026-05-13`

## Полный текст prompt (как получен от пользователя)

```text
Cursor, следующий этап:
Retrieval-aware conversational memory orchestration (Memory v1.1)

Это НЕ semantic memory.
НЕ embeddings memory.
НЕ long-term user profiling.

Это:
production-style short-term conversational context orchestration.

Обязательное правило:
создай engineering log:

`docs/cursor_sessions/YYYY-MM-DD_memory-v1_1-retrieval-aware-context.md`

Дата:

```bash
date +%F
```

В лог включить:

* timestamp;
* полный текст prompt;
* workspace snapshot;
* git status before/after;
* architectural decisions;
* changed files;
* smoke scenarios;
* contamination findings;
* deferred items.

Commit НЕ выполнять.

==================================================
КОНТЕКСТ
========

Уже реализовано:

* PG-backed short-term memory;
* memory lifecycle observability;
* session operational UI;
* retrieval diagnostics;
* RAG operational console;
* contamination safeguards.

Сейчас memory существует,
но orchestration между:

* retrieval,
* dialog history,
* current user intent

ещё недостаточно formalized.

Нужно перейти от:

```text
history tail append
```

к:

```text
retrieval-aware conversational context assembly
```

==================================================
ГЛАВНАЯ ЦЕЛЬ
============

Сделать explicit conversational context orchestration layer.

AF должен:

* понимать follow-up questions;
* использовать краткосрочную память;
* не загрязнять persistent history retrieval payloads;
* прозрачно логировать assembled conversational context.

==================================================

1. CONVERSATIONAL CONTEXT ASSEMBLY
   ==================================================

Проведи review current pipeline:

* Telegram runtime path
* RagQueryService
* prompt assembly
* memory loading
* history trimming
* retrieval injection

Нужно реализовать explicit layer/function:

например:

```text
build_conversational_context(...)
```

или аналогичную abstraction.

Она должна:

* принимать:

  * current query
  * short-term memory
  * retrieval chunks
  * runtime metadata

* возвращать:

  * structured LLM context
  * diagnostics metadata

==================================================
2. FOLLOW-UP QUESTION SUPPORT
=============================

Очень важно:
система должна лучше понимать:

* "а если удаленно?"
* "а для стажеров?"
* "а сколько дней?"
* "а по выходным?"

после предыдущего вопроса.

Но:
без giant history dumps.

Нужно:

* проверить current behavior;
* улучшить conversational continuity;
* сохранить strict history budget.

==================================================
3. MEMORY BUDGET POLICY
=======================

Сделать explicit policy/config.

Например:

* max conversational turns;
* max chars/tokens for history;
* trimming strategy.

Важно:
retrieval context
и
conversation history
должны иметь отдельные budgets.

==================================================
4. CONTEXT OBSERVABILITY
========================

Добавить observability
для conversational assembly.

Но:
НЕ логировать full prompts.

Нужно логировать безопасно:

Например:

* history_turns_used;
* retrieval_chunks_used;
* retrieval_chars;
* history_chars;
* conversational_context_size;
* trimming_applied;
* followup_detected (bool).

В processing_logs/details.

==================================================
5. FOLLOW-UP DETECTION
======================

Добавить lightweight heuristic.

Например:
короткий вопрос:

* "а если..."
* "а как тогда..."
* "а для них?"
* "почему?"

может считаться follow-up.

Нужно:

* detection heuristic;
* observability flag;
* safe fallback.

Без отдельной ML модели.

==================================================
6. CONTAMINATION SAFEGUARDS
===========================

Критично:
убедиться, что:

* retrieval chunks
* diagnostics
* assembled prompts
* runtime telemetry

НЕ попадают:

* в persistent memory
* в chat_messages

Проверить весь runtime path.

==================================================
7. ADMIN UI / OBSERVABILITY
===========================

Если возможно минимально и безопасно:

добавить в RAG diagnostics:

* history turns used;
* follow-up detected;
* trimming applied.

Но:
без redesign.

==================================================
8. TESTING
==========

Провести smoke scenarios:

A.
Q1: "Какой график работы?"
Q2: "А для удаленных сотрудников?"

B.
Q1: "Сколько отпуск?"
Q2: "А для стажеров?"

C.
clear/reset
→ убедиться что continuity исчезает.

D.
long dialog
→ trimming работает.

==================================================
9. НЕ ДЕЛАТЬ
============

НЕ делать:

* semantic memory;
* embeddings memory;
* vectorized conversations;
* user profiling;
* summarization memory;
* auto-memory extraction;
* memory embeddings DB;
* long-term preferences.

==================================================
10. RESULT
==========

В конце:

1. Что изменено;
2. Как теперь работает conversational assembly;
3. Какие observability fields добавлены;
4. Как работает follow-up support;
5. Какие contamination safeguards подтверждены;
6. Какие ограничения остались;
7. Path к engineering log.

Commit НЕ выполнять.
```

## Workspace snapshot (кратко)

Корень репозитория `/opt/assistant-flow`: типичный монорепо с `admin_api/`, `frontend/admin-ui/`, `interfaces/`, `repositories/`, `scripts/`, `services/`, `utils/`, `docs/`, и т.д. (полный список не дублируется; см. `git status`).

## Git status

### Before (начало работ по этому этапу в сессии)

```
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/app.py
 M admin_api/deps.py
 M frontend/admin-ui/src/App.tsx
 M frontend/admin-ui/src/api/client.ts
 M frontend/admin-ui/src/navigation/routes.ts
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
?? docs/cursor_sessions/2026-05-13_PROJECT_STATE_section-47-pe02-retrieval-backlog.md
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? docs/cursor_sessions/2026-05-13_memory-observability-and-sessions-ui.md
?? docs/cursor_sessions/2026-05-13_memory-v1-operational-stabilization.md
?? docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md
?? frontend/admin-ui/src/pages/MemoryPage.tsx
?? scripts/test_memory_observability_admin_smoke.py
?? scripts/test_memory_v1_contamination_smoke.py
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? scripts/test_retrieval_backend_identity_smoke.py
?? services/memory_observability_service.py
```

### After (после Memory v1.1 + этот лог)

```
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
?? docs/cursor_sessions/2026-05-13_PROJECT_STATE_section-47-pe02-retrieval-backlog.md
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? docs/cursor_sessions/2026-05-13_memory-observability-and-sessions-ui.md
?? docs/cursor_sessions/2026-05-13_memory-v1-operational-stabilization.md
?? docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md
?? docs/cursor_sessions/2026-05-13_memory-v1_1-retrieval-aware-context.md
?? frontend/admin-ui/src/pages/MemoryPage.tsx
?? scripts/test_memory_observability_admin_smoke.py
?? scripts/test_memory_v1_1_conversational_assembly_smoke.py
?? scripts/test_memory_v1_contamination_smoke.py
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? scripts/test_retrieval_backend_identity_smoke.py
?? services/conversational_context_assembly.py
?? services/memory_observability_service.py
```

**Commit не выполнялся** (по требованию).

## Architectural decisions

1. **Явный слой сборки:** `services/conversational_context_assembly.py` — `build_rag_conversational_context` + `detect_followup_question`; результат `RagConversationalContextAssembly` (хвост для LLM + флаги/счётчики). Это не semantic memory, только детерминированные лимиты и эвристика.
2. **Два бюджета:** число сообщений — `telegram_memory_max_llm_messages` (как и PG/инмемори контракт); отдельный **символьный** потолок истории для RAG — `rag_conversation_history_max_chars` / `RAG_CONVERSATION_HISTORY_MAX_CHARS` (после cap по сообщениям отрезается с головы хвоста, пока сумма символов контента не уложится в бюджет). Размер retrieval по-прежнему отражается в `context_chars` и отдельно в `retrieval_chars` (длина KB-only `_format_context(filtered)` до hybrid merge).
3. **Один проход в `answer()`:** assembly вычисляется один раз на запрос; в LLM уходит уже `history_for_llm`, без повторного tail внутри `_rag_llm`.
4. **Follow-up:** эвристика по префиксам / длине + флаг `followup_question_detected` в diagnostics; при `followup_hint` и непустой истории в system prompt добавляется короткий **шаблонный** блок (без подстановки чанков/истории в текст правила).
5. **Наблюдаемость:** новые поля только в `RagRequestDiagnostics.to_log_details()` — скаляры и bool, без полных промптов.
6. **Admin API:** ключи добавлены в `_PRESERVED_DETAIL_KEYS` (`admin_api/deps.py`), чтобы поля доходили до UI после slim.

## Changed files (этот этап Memory v1.1)

| Path | Назначение |
|------|------------|
| `services/conversational_context_assembly.py` | Новый модуль: assembly + follow-up heuristic |
| `services/rag_query_service.py` | Вызов assembly, `_assembly_diag_for_logs`, `_rag_llm(history_for_llm, followup_hint)`, делегирование `_history_tail_for_llm` |
| `services/rag_types.py` | Поля diagnostics + `to_log_details` + частичный `emit_stdout` |
| `utils/config.py` | `rag_conversation_history_max_chars` / env |
| `admin_api/deps.py` | Allowlist ключей для RAG details |
| `frontend/admin-ui/src/pages/RagPage.tsx` | Три OpsRow + поля сессии + `pickBool` |
| `scripts/test_memory_v1_1_conversational_assembly_smoke.py` | Статический smoke |
| `docs/cursor_sessions/2026-05-13_memory-v1_1-retrieval-aware-context.md` | Этот лог |

## Smoke scenarios

| ID | Сценарий | Как проверено в этой сессии |
|----|----------|-----------------------------|
| A | Q1 график → Q2 «А для удалённых…» | Эвристика: `detect_followup_question("А для удалённых?", has_prior_dialog=True)` в unit-smoke; в продукте — ручной прогон Telegram RAG |
| B | Q1 отпуск → Q2 «А для стажеров?» | Аналогично префиксу `а для` в heuristic + follow-up hint в LLM при непустой истории |
| C | clear/reset → нет continuity | Не автоматизировано здесь; поведение по-прежнему от PG-сессии / `clear_rag_history_only` / отсутствия history |
| D | Long dialog → trimming | `test_char_trim` и `test_message_cap` в `scripts/test_memory_v1_1_conversational_assembly_smoke.py` |

Команды:

- `python3 scripts/test_memory_v1_1_conversational_assembly_smoke.py`
- `python3 scripts/test_memory_v1_contamination_smoke.py`
- `npm run build` в `frontend/admin-ui`

## Contamination findings

- **`chat_messages` / persistent memory:** по-прежнему `persist_telegram_dialog_turn_best_effort(..., user_text=text, assistant_text=result.answer)` — в PG уходит только пользовательский текст и ответ модели, не retrieval payload и не assembled system prompt.
- **`rag_answer_done` details:** расширены безопасными числами/bool; полные промпты по-прежнему не пишутся в эти поля (остаётся прежний контракт `query_preview` / previews чанков как раньше).
- **Hybrid:** если включён, `context_chars` и `retrieval_chars` могут расходиться (retrieval_chars = KB-only длина до merge) — это сознательно для раздельной телеметрии retrieval vs итоговый system context.

## Deferred items

- Нет отдельного **token**-бюджета для истории (только символы + сообщения).
- Нет автоматического E2E Telegram-теста для сценариев A–D (только статический smoke + ручная проверка).
- `retrieve()` без `answer()` по-прежнему не пишет conversational assembly telemetry (нет LLM-ветки).
- Не добавлялись поля в Memory ops UI — только RAG diagnostics, по запросу «минимально».

## Результат (раздел 10 из prompt)

1. **Что изменено:** см. таблицу «Changed files».
2. **Как работает assembly:** один вызов `build_rag_conversational_context` → tail сообщений + char trim → список для LLM; retrieval остаётся в `context` system-блока отдельно.
3. **Observability:** `followup_question_detected`, `history_turns_used`, `history_messages_used`, `history_messages_loaded`, `history_chars`, `history_trimming_applied`, `conversational_context_size_chars`, `retrieval_chunks_used`, `retrieval_chars` в `processing_logs.details` (через `to_log_details`).
4. **Follow-up:** эвристика + флаг + опциональный hint в system prompt при непустой истории.
5. **Contamination:** см. раздел выше; путь Telegram RAG проверен статически + код persist.
6. **Ограничения:** эвристика follow-up даёт ложноположительные на коротких вопросах при наличии истории; нет ML-классификатора (по ТЗ).
7. **Path к логу:** `docs/cursor_sessions/2026-05-13_memory-v1_1-retrieval-aware-context.md`
