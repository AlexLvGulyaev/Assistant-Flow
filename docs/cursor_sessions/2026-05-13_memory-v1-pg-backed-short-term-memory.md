# Engineering log (2026-05-13): Memory v1 (PostgreSQL short-term RAG memory)

**Календарная дата лога:** `2026-05-13` — имя файла и этот заголовок зафиксированы по выводу `date +%F` на момент записи (operational hygiene: не копировать дату из analysis pass или старых шаблонов).

## 1. Полный текст prompt

```
Cursor, начинаем реализацию Memory v1 для Assistant Flow.

Обязательное правило дисциплины:
перед началом изменений создай engineering log в `docs/cursor_sessions/`:

`YYYY-MM-DD_memory-v1-pg-backed-short-term-memory.md`
(в имени файла подставить результат `date +%F` на день создания лога)

В этот файл внеси:

1. полный текст этого prompt;
2. workspace snapshot;
3. git status before;
4. план изменений;
5. список изменённых файлов;
6. краткий отчёт по реализации;
7. smoke tests / команды проверки;
8. git status after;
9. open issues / risks.

Commit НЕ выполнять.

Контекст:
Уже выполнен analysis pass:
`docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md`

Главные инварианты:

* Telegram handlers remain thin;
* PostgreSQL is source of truth;
* persistent conversation history stores only clean user query and clean assistant answer;
* never persist system prompts, retrieved chunks, diagnostics, raw RAG context, prompt assembly;
* runtime context != persistent memory;
* retrieval context must not pollute user conversation history;
* observability-first memory lifecycle;
* no direct copy-paste from `legacy/PEr04_source`.

Цель Memory v1:
Перевести short-term RAG conversation memory на PostgreSQL-backed источник через существующие таблицы:

* `app_users`
* `chat_sessions`
* `chat_messages`
* `user_preferences`

Текущая проблема:
В AF сейчас есть риск раздвоения:

* in-memory RAG history в `utils/telegram_user_state.py`;
* persistent PG memory через существующий memory/session layer.

Нужно сделать PG основным источником short-term memory для RAG runtime context.

Что нужно реализовать:

1. Проведи code audit текущих файлов: (список файлов из задания)
2. Найди существующие методы: создания/получения app_user; chat_session; chat_messages; recent messages; best-effort persist Telegram turn. Не дублировать сервисы.
3. Реализуй или доработай `ConversationMemoryService`: recent clean turns из PG; лимит пар/сообщений; LLM-ready list; clear/rotate session.
4. Clear semantics: не удалять старые сообщения; деактивировать сессию или новая active session; `/reset` PG-aware; `/clear` alias; обе чистят in-memory и ротируют PG session.
5. Интеграция Telegram RAG: загрузка history из PG; `RagQueryService.answer(..., conversation_history=...)`; после ответа persist clean user/assistant; не сохранять RAG prompt; риск если clean answer включает источники — open issue.
6. Observability: processing_logs stages memory_load_started, memory_load_done, memory_append_done, memory_session_cleared, memory_error (details без текстов сообщений).
7. Config: max messages/pairs; session idle timeout если есть; memory enabled; не ломать env.
8. Tests: `scripts/test_memory_v1_pg_short_term_smoke.py`.
9. После: py_compile/smoke, обновить log, git status, без commit.

Формат ответа в чат: что изменено; файлы; тесты; риски; path к log.
```

## 2. Workspace snapshot

- Path: `/opt/assistant-flow`
- Затронуты в рамках Memory v1: `interfaces/telegram_bot.py`, `services/memory/conversation_memory_service.py`, `services/chat_session_service.py`, `repositories/session_repository.py`, `utils/config.py`, `utils/telegram_user_state.py`, `scripts/test_memory_v1_pg_short_term_smoke.py`, этот файл лога.

## 3. Git status before

```
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/deps.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/retrieval_cache_key.py
 M services/rag_query_service.py
 M services/rag_types.py
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? scripts/test_retrieval_backend_identity_smoke.py
```

## 4. План изменений

1. `SessionRepository` + `ChatSessionService`: деактивация активных сессий и `rotate_active_session`.
2. `ConversationMemoryService`: `get_llm_turns_for_session`, `load_telegram_rag_history_for_llm`, `rotate_telegram_conversation_session_best_effort`, lifecycle + stdout.
3. `persist_telegram_dialog_turn_best_effort`: clean assistant; `memory_append_done` / `memory_error` в lifecycle при переданном `execution_id`.
4. `AppConfig` + `load_config`: TELEGRAM_PG_CONVERSATION_MEMORY, лимиты пар/сообщений, заглушка idle timeout.
5. `telegram_bot.py`: RAG — PG history + hybrid ids; `/reset` и `/clear`; persist `result.answer`.
6. `telegram_user_state.py`: `clear_rag_history_only`.
7. Smoke-скрипт.

## 5. Список изменённых файлов (Memory v1)

- `repositories/session_repository.py` — `deactivate_all_active_for_user`
- `services/chat_session_service.py` — `rotate_active_session`
- `services/memory/conversation_memory_service.py` — LLM history, load/rotate helpers, lifecycle на persist
- `interfaces/telegram_bot.py` — RAG path, `/clear`, `/reset` PG-aware
- `utils/config.py` — поля и env для памяти
- `utils/telegram_user_state.py` — `clear_rag_history_only`, docstring
- `scripts/test_memory_v1_pg_short_term_smoke.py` — новый
- `docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md` — этот лог (дата имени по `date +%F`)

## 6. Краткий отчёт по реализации

- **PG как основной источник** для RAG runtime history при `DATABASE_URL` и `TELEGRAM_PG_CONVERSATION_MEMORY` (default true): `load_telegram_rag_history_for_llm` → только `user`/`assistant` из активной сессии, LLM-ready список, лимиты через config.
- **Fallback**: при выключенной памяти или без БД — прежний `rag_history_snapshot` + `append_rag_turn`.
- **Persist**: в PG уходит `(result.answer).strip()`, не `format_for_telegram(telegram_reply)` — чтобы не тащить Telegram-форматирование в `chat_messages`.
- **Clear**: `/reset` — `user_store.reset` + ротация сессии с `mode=text`; `/clear` — только очистка in-memory RAG buffer + ротация с `mode=rag` если пользователь в rag, иначе `text` (режим OCR/text не маппится в CHECK схемы — новая сессия `text`).
- **Hybrid**: при `enable_hybrid_retrieval` передаются `hybrid_session_id` / `hybrid_user_id` из активной PG-сессии и `app_users.id`.
- **Observability**: стадии `memory_*` через `RuntimeLifecycleService.log_processing_event` там, где есть `lifecycle` и `execution_id`; дублирующий компактный stdout сохранён.
- **2026-05-13:** файл лога переименован с ошибочного `2026-05-11_*` на календарную дату выполнения по правилу operational hygiene (`date +%F`).

## 7. Smoke tests / команды проверки

Выполнено в среде без PostgreSQL:

```bash
cd /opt/assistant-flow
date +%F
python3 -m py_compile interfaces/telegram_bot.py \
  services/memory/conversation_memory_service.py \
  services/chat_session_service.py \
  repositories/session_repository.py \
  utils/config.py \
  utils/telegram_user_state.py \
  scripts/test_memory_v1_pg_short_term_smoke.py
python3 scripts/test_memory_v1_pg_short_term_smoke.py
# вывод: SKIP: DATABASE_URL not set ; exit 0
```

С реальной БД: задать `DATABASE_URL`, ожидается `OK memory_v1_pg_short_term_smoke`.

## 8. Git status after

```
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/deps.py
 M interfaces/telegram_bot.py
 M repositories/session_repository.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/retrieval_cache_key.py
 M services/chat_session_service.py
 M services/memory/conversation_memory_service.py
 M services/rag_query_service.py
 M services/rag_types.py
 M utils/config.py
 M utils/telegram_user_state.py
?? docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? scripts/test_retrieval_backend_identity_smoke.py
```

## 9. Open issues / risks

- **`user_preferences`**: в этом проходе не задействованы (нет существующего use-case в RAG path); при необходимости связать default_mode с `/mode` — отдельная задача.
- **`CHAT_SESSION_IDLE_TIMEOUT_SECONDS`**: только в config, в рантайме не применяется (в кодовой базе не было consumer — зафиксировано как зарезервированное).
- **Режим OCR**: `/clear` создаёт новую сессию с `mode=text` (в `chat_sessions` нет `ocr` в CHECK); история OCR в PG в этой ветке не разделялась.
- **Двойной источник при `TELEGRAM_PG_CONVERSATION_MEMORY=false`**: persist в PG может продолжаться, а LLM history — in-memory; возможен рассинхрон при последующем включении PG — риск для операторов.
- **Источники в тексте ответа**: если в будущем `result.answer` будет содержать блок источников, это попадёт в `chat_messages` — сейчас `_format_rag_telegram_reply` возвращает сырой `answer`; источники обычно отдельно в `RagQueryResult.sources`.
