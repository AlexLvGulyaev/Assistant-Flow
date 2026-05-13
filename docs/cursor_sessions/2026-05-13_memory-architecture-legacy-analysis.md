# Engineering log: memory architecture — анализ legacy PEr04 и целевой контур AF (2026-05-13)

---

## 1. Исходный Cursor prompt (полный текст запроса на analysis pass)

Ниже — **дословно** текст предыдущего сообщения пользователя, по которому выполнялся анализ (не текущее сообщение про создание лога).

```text
Проанализируй legacy/PEr04_source как reference implementation урока про память AI-ассистента.

Цель: НЕ переносить код напрямую, а определить, какие архитектурные идеи можно адаптировать в Assistant Flow.

Контекст Assistant Flow:
- основной контур: portfolio-test / GitHub container;
- Telegram handlers должны оставаться thin;
- бизнес-логика должна жить в services/orchestrator;
- PostgreSQL — source of truth;
- RAG/retrieval уже реализован отдельно;
- запрещено сохранять в историю system prompts, retrieved chunks, diagnostics, raw RAG context, prompt assembly;
- в персистентную историю должны попадать только clean user query и clean assistant answer;
- observability должна логировать memory-события компактно: session_id, messages_loaded, messages_saved, limit, latency_ms, без текста сообщений.

Проверь legacy/PEr04_source и подготовь engineering report:

1. Какие модули есть в legacy:
   - session manager;
   - user context;
   - memory/context retriever;
   - telegram handlers;
   - config;
   - storage;
   - LLM clients.

2. Какие идеи можно забрать в AF:
   - short-term memory limit;
   - session timeout;
   - /clear command;
   - user metadata;
   - message formatting for LLM;
   - top_k comparison test.

3. Какие решения НЕ переносить:
   - JSON-file storage, если есть;
   - in-memory only sessions, если есть;
   - direct coupling Telegram → LLM;
   - direct prompt assembly inside handler;
   - OpenAI-specific client logic, если оно дублирует существующие providers.

4. Предложи целевую AF-архитектуру:
   - repositories for chat_sessions/chat_messages/user_preferences;
   - MemoryService or ConversationMemoryService;
   - MemoryContextAssembler;
   - integration point in orchestrator/RagQueryService;
   - /clear behavior;
   - processing_logs stages for memory lifecycle.

5. Найди текущие файлы AF, которые уже содержат близкую функциональность:
   - repositories/*session*;
   - repositories/*user*;
   - repositories/*chat*;
   - core/orchestrator.py;
   - interfaces/telegram_bot.py;
   - services/rag_query_service.py;
   - services/hybrid_retrieval/*;
   - database/schema.sql;
   - utils/config.py.

6. Дай patch plan по файлам, но пока НЕ вноси изменения.
Формат ответа:
- Findings from legacy
- Reusable ideas
- Do not copy
- Target AF design
- File-level implementation plan
- Risks
- Smoke tests
```

---

## 2. Workspace snapshot

- **Корень репозитория:** `assistant-flow` (рабочая копия `/opt/assistant-flow` в среде анализа).
- **Legacy reference:** `legacy/PEr04_source/` (37 файлов: `dialog_controller/`, `memory_manager/`, `interface/`, `storage/`, `ai_processor/`, `ai_gigachat_processor/`, `config/`, `main.py`, и т.д.).
- **Основные контуры AF (по анализу):** `interfaces/telegram_bot.py`, `core/orchestrator.py`, `services/` (в т.ч. `rag_query_service.py`, `memory/`, `hybrid_retrieval/`, `chat_session_service.py`), `repositories/`, `database/schema.sql`, `utils/config.py`, `providers/`.
- **Состояние git на момент фиксации лога:** см. раздел **«Git status (без commit)»** в конце файла — актуально на дату создания файла.

---

## 3. Findings по `legacy/PEr04_source`

| Модуль | Назначение |
|--------|------------|
| **Session manager** | `dialog_controller/session_manager.py` — in-memory `Dict[user_id, UserContext]`, TTL `session_timeout`, очистка истёкших сессий. |
| **User context** | `dialog_controller/user_context.py` — список `conversation_history`, `metadata`, счётчики, `clear_conversation_history`, выборка последних N сообщений. |
| **Memory / context retriever** | `memory_manager/context_retriever.py` — поиск по `VectorDatabase` (Chroma-API), порог relevance, список источников. |
| **Prompt assembly** | `memory_manager/prompt_builder.py` — сборка текста из документов и списка сообщений для LLM (system + history + user с встроенным KB-блоком). В `main.py` создаётся, в показанном потоке `handlers.handle_message` **не используется** (дублирование идеи с `ResponseGenerator`). |
| **Telegram** | `interface/telegram_bot.py` + `interface/handlers.py` — регистрация команд, `handle_message`: user_db, session, retrieve, `response_generator.generate`, append в in-memory историю, ответ с источниками. |
| **Config** | `config/settings.py` — `session_timeout`, `max_context_messages`, `rag_n_results`, провайдеры, Chroma. |
| **Storage** | `storage/user_db.py` — **JSON-файл** пользователей; `storage/vector_db.py` — векторное хранилище. |
| **LLM** | `ai_processor/` (OpenAI), `ai_gigachat_processor/` (GigaChat) — отдельные клиенты и `ResponseGenerator`. |

**Наблюдение по потоку:** бизнес-цепочка RAG + история завязана на **handlers** (толстый слой относительно требований AF).

---

## 4. Разделение: краткосрочная / долгосрочная / семантическая память

### 4.1 Краткосрочная память (short-term)

- **Смысл:** последние реплики диалога, ограниченные по числу сообщений и/или символам, подаваемые в LLM как контекст multi-turn **без** записи RAG-обогащения в PG как «часть диалога».
- **В legacy:** in-memory `UserContext.conversation_history`, `max_context_messages` в settings.
- **В AF сейчас:** частично **in-memory** `utils/telegram_user_state.InMemoryTelegramUserStore.rag_conversation_history` (последние ходы для `RagQueryService.answer(..., conversation_history=...)`); частично **PG** через `ConversationMemoryService` + `chat_messages` при `persist_telegram_dialog_turn_best_effort`.
- **Целевое:** единый источник short-term для RAG из **PG** + бюджет (`MemoryBudgetPolicy`, лимиты в `HybridRetrievalPolicy`), in-memory только как опциональный кэш или удаление после миграции.

### 4.2 Долгосрочная память (long-term)

- **Смысл:** персистентная история пользователь↔ассистент, пригодная для аудита, восстановления сессии, аналитики; не смешивается с векторным KB без отдельного контракта.
- **В legacy:** только то, что попало в JSON `user_data` (метаданные пользователя), не полноценная история сообщений в файле на уровне PEr04 handlers.
- **В AF:** `chat_sessions` + `chat_messages` — **SoT** для чистых реплик; `user_preferences` для устойчивых настроек пользователя.
- **Целевое:** явные политики retention/archival (отдельная задача; в schema уже есть временные метки сообщений).

### 4.3 Семантическая память (semantic)

- **Смысл:** извлекаемые по смыслу записи (отдельный retrieval namespace / embeddings), не путать с `chat_messages` и не путать с Chroma KB документов.
- **В legacy:** не выделено; RAG = единственный «семантический» слой через `ContextRetriever`.
- **В AF:** зафиксировано в `services/memory/base.py` как **будущее** направление; текущий код — **dialog history**, не semantic memory retrieval.

---

## 5. Architectural invariants Assistant Flow

Инварианты, с которыми согласован analysis pass и текущий контур кода:

1. **Telegram handlers remain thin** — маршрутизация, ввод/вывод, вызов сервисов; без дублирования сборки промпта и retrieval внутри handler там, где уже есть сервисный слой.
2. **Orchestrator / services contain business logic** — оркестрация режимов, RAG, память, lifecycle; `PromptOrchestrator` для части text/image не отменяет правило для RAG/memory путей.
3. **PostgreSQL is source of truth** для персистентной истории и сессий (`chat_sessions`, `chat_messages`, `app_users`, `user_preferences`).
4. **No system prompts / retrieved chunks / diagnostics / raw RAG context / prompt assembly** в **персистентной** conversation history — только **clean user query** и **clean assistant answer** (как в контракте `ConversationMemoryService` / `persist_telegram_dialog_turn_best_effort`).
5. **Observability-first memory lifecycle** — компактные логи: `session_id`, `messages_loaded`, `messages_saved`, `limit`, `latency_ms`, **без текста** сообщений в stdout memory-lines (расширение: те же поля в `processing_logs` stages).
6. **Retrieval context must not pollute user conversation history** — KB chunks остаются в runtime сборке промпта / diagnostics / `HybridContextService`, не в `append_message` как user content.

---

## 6. Таблицы schema, уже подходящие под memory layer

| Таблица | Роль в memory layer |
|---------|---------------------|
| **`app_users`** | Идентификация пользователя (Telegram id и др.); FK для сессий и preferences. |
| **`chat_sessions`** | Логическая сессия: `user_id`, `mode`, `is_active`, `created_at` / `updated_at`; точка для idle-timeout и `/clear` (ротация/деактивация). |
| **`chat_messages`** | Персистентные реплики `user` / `assistant` (и др. роли по схеме), `metadata` JSONB, связь с `execution_id` / `intake_event_id`. |
| **`user_preferences`** | Долгосрочные настройки: `default_mode`, флаги, `language`, **`metadata JSONB`** для расширяемых user metadata без дублирования legacy JSON-file. |

Миграция схемы под memory **не требовалась** для фиксации этого отчёта: перечисленные объекты уже присутствуют в `database/schema.sql`.

---

## 7. Reusable ideas (адаптация, не копия кода)

- Лимит short-term (**последние N сообщений** + символьный бюджет) — как в legacy `max_context_messages`, в AF — `MemoryBudgetPolicy` / `HybridRetrievalPolicy`.
- **Session timeout / idle** — как политика новой сессии или деактивации в PG, а не только dict TTL.
- Команда сброса (**аналог `/clear`**) — в AF уже есть **`/reset`** для in-memory RAG buffer; расширение до PG + lifecycle.
- **User metadata** — `user_preferences.metadata` + при необходимости узкий контракт ключей.
- **Message formatting for LLM** — выделенный assembler из чистых записей + отдельный runtime RAG-блок (не сериализовать в PG).
- **top_k / n_results comparison tests** — регрессии конфигурации retrieval отдельно от memory.

---

## 8. Anti-patterns / what NOT to copy

- **JSON-file `user_data.json`** вместо PostgreSQL.
- **In-memory-only** сессии и полная история только в процессе (потеря при рестарте).
- **Handler → retrieval → LLM** без прохода через сервисный слой AF.
- **Сборка промпта с KB внутри handler** как основной паттерн.
- **Дублирующие OpenAI-клиенты** поверх существующих `providers/`.

---

## 9. Proposed AF memory architecture (целевое)

- **Repositories / services:** уже есть `SessionRepository`, `ChatSessionService`, `ConversationMemoryService`; при необходимости — thin слой над `user_preferences`.
- **`ConversationMemoryService`** — остаётся SoT read/write для **чистых** сообщений; расширить: clear/rotate session, унифицированные **processing_logs** stages.
- **`MemoryContextAssembler`** (новое имя или методы на `ConversationMemoryService`) — преобразование `ConversationMemoryRecord[]` → `list[dict]` для LLM **без** KB.
- **Integration:** `RagQueryService.answer(..., conversation_history=...)` — точка подачи short-term; источник — PG, не только `InMemoryTelegramUserStore`.
- **`/clear` / `/reset`:** сервисная операция — деактивация сессии / новая сессия + очистка in-memory буфера + stage в `processing_logs`.
- **`processing_logs`:** стадии `memory_load_*`, `memory_append_*`, `memory_session_cleared` (только метаданные, без текста).

---

## 10. Integration points

- **`interfaces/telegram_bot.py`** — после рефактора: вызов фасада «RAG + memory persist», тонкий handler.
- **`services/rag_query_service.py`** — не пишет в PG; принимает history только для runtime.
- **`services/hybrid_retrieval/hybrid_context_service.py`** — склейка KB + memory для prompt; не для persist.
- **`services/memory/conversation_memory_service.py`** + **`persist_telegram_dialog_turn_best_effort`** — единственная запись чистых реплик из Telegram path (best-effort).
- **`RuntimeLifecycleService`** — стадии memory lifecycle.

---

## 11. File-level implementation plan (patch plan, без изменений в том pass)

1. `utils/telegram_user_state.py` — миграция источника `rag_history_snapshot` на PG или согласование с PG.
2. `interfaces/telegram_bot.py` — вынести тело RAG-path в сервис; расширить `/reset` / добавить `/clear` с PG.
3. `services/memory/conversation_memory_service.py` — clear/rotate; при необходимости `to_llm_turns()`.
4. `repositories/session_repository.py` — деактивация сессии, при необходимости новые методы выборки.
5. `services/rag_query_service.py` — проверка контракта: history не содержит retrieval payload.
6. `services/hybrid_retrieval/hybrid_context_service.py` — избежать дублирования trim с memory-слоем.
7. `database/schema.sql` — только при появлении новых полей (например `cleared_at`); иначе обойтись `is_active` / новой сессией.
8. `utils/config.py` — env для memory limits / session idle.
9. Тесты / scripts — smoke PG ↔ RAG без утечки chunk в `chat_messages`.

---

## 12. Risks

- Расхождение **in-memory** RAG history и **PG** до завершения миграции.
- Двойное применение бюджетов (`HybridRetrievalPolicy` vs `MemoryBudgetPolicy`).
- Латентность лишних round-trip к PG на каждый turn.
- Риск утечки diagnostics в persist при регрессии в handler.

---

## 13. Smoke tests (рекомендации)

1. Три пары user/assistant в PG → `get_recent_messages` → в stdout memory-line **нет** полного `content`.
2. RAG-ответ → в `chat_messages` только чистые строки; в `processing_logs` для RAG — нет полных chunk texts (контракт slim).
3. `/reset` или `/clear` после реализации — новая/неактивная сессия + lifecycle stage.
4. Hybrid on — memory в runtime prompt есть; в PG нет KB-текста как сообщения пользователя.

---

## 14. Open questions

- Нужна ли **отдельная** таблица под semantic memory или достаточно отдельной коллекции / namespace в существующем retrieval с жёсткой изоляцией от KB?
- Политика **retention** для `chat_messages` (бессрочно vs архивация)?
- Синхронизация **`chat_sessions.mode`** с Telegram `InMemoryTelegramUserStore.mode` при рестарте бота.
- Нужен ли **явный** `cleared_at` на сессии vs только `is_active = false`?
- Как унифицировать **одну** команду для пользователя (`/reset` vs `/clear`) без ломания привычек?

---

## 15. Recommended implementation order

1. Зафиксировать контракт **persist only clean turns** (ревью `persist_telegram_dialog_turn_best_effort` + все вызовы `append_message` из Telegram).
2. Добавить **processing_logs** stages для memory load/save/clear (без текста).
3. Ввести **MemoryContextAssembler** (или методы на `ConversationMemoryService`) для списка сообщений LLM из PG.
4. Перевести **`rag_history_snapshot`** на чтение из PG (с лимитом), затем сократить или удалить дублирующий in-memory буфер.
5. Реализовать **PG-aware `/reset` или `/clear`** (ротация `chat_sessions`).
6. Опционально: использовать **`user_preferences.metadata`** для пользовательских метаданных, не дублируя legacy JSON.
7. Отложенно: **semantic memory** как отдельный эпик (схема + retrieval + политика безопасности).

---

## 16. Git status (без commit)

Файл создан как неотслеживаемый до `git add`. Актуальный статус рабочей копии — выполнить:

```bash
cd /opt/assistant-flow && git status -sb
```

На момент генерации этого лога в среде анализа (до добавления только этого файла) в статусе уже были другие локальные изменения; после сохранения файла **`docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md`** он появится как **`??`** в `git status`. **Commit не выполнялся.**

---

## Path

`docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md`
