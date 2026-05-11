# Session: P6.1 — Retrieval Abstraction Layer (Chroma-first)

## Задание (полный текст)

Cursor, начинаем реализацию P6.

Работаем по-русски в комментариях, отчётах и пояснениях. Имена файлов/классов/переменных — на английском, как принято в Python-проекте.

# Задача: P6.1 — Retrieval Abstraction Layer, Chroma-first

## Цель

Ввести foundation-слой retrieval abstraction, НЕ ломая текущий рабочий Chroma RAG pipeline.

На этом шаге:

* НЕ внедряем FAISS;
* НЕ меняем production semantics;
* НЕ меняем compose;
* НЕ создаём migrations;
* НЕ трогаем UI;
* НЕ меняем DB schema;
* НЕ меняем внешнее поведение Telegram/Admin API;
* НЕ переписываем весь RAG.

Нужно сделать минимальный, безопасный abstraction layer поверх текущего Chroma-кода.

---

# Архитектурная цель

Сейчас AF напрямую зависит от `services/rag_chroma_store.py`.

Нужно подготовить основу:

```text
services/retrieval/
    __init__.py
    base.py
    chroma_backend.py
    factory.py
```

Но на первом этапе поведение должно остаться идентичным текущему Chroma path.

Chroma остаётся primary production backend.

FAISS появится следующим шагом, после проверки Chroma adapter.

---

# Требования к реализации

## 1. Создать `services/retrieval/base.py`

Определи dataclass/DTO и Protocol/ABC для retrieval.

Нужны минимальные сущности:

* `RetrievalChunk`
* `RetrievalSearchResult`
* `RetrievalHealth`
* `RetrievalBackend`

Интерфейс backend должен покрывать текущие реальные операции, без overengineering:

```python
class RetrievalBackend(Protocol):
    def collection_count(self) -> int: ...
    def search(self, query: str, top_k: int = 5) -> list[RetrievalSearchResult]: ...
    def healthcheck(self) -> RetrievalHealth: ...
```

Если текущий Chroma store требует другие поля/методы, аккуратно адаптируй, но не расширяй интерфейс без необходимости.

Важно:

* не тащи сразу `add_chunks/reset` если текущий безопасный этап этого не требует;
* но можешь оставить TODO/комментарий, что indexing-side методы появятся после стабилизации query-side abstraction.

---

## 2. Создать `services/retrieval/chroma_backend.py`

Сделать тонкий adapter поверх существующего `ChromaRagStore`.

Правило:
`ChromaBackend` НЕ должен заново реализовывать Chroma logic.

Он должен:

* принимать уже существующие config параметры;
* внутри использовать `ChromaRagStore`;
* нормализовать результат поиска в `RetrievalSearchResult`;
* прокидывать health/count;
* не менять scoring behavior;
* не менять collection name;
* не менять embedding behavior.

Если `ChromaRagStore` возвращает данные в другом формате — сделай аккуратный mapping.

---

## 3. Создать `services/retrieval/factory.py`

Фабрика должна возвращать backend по config/env.

На этом шаге поддерживаем только:

```text
RAG_BACKEND=chroma
```

Если значение:

* отсутствует → использовать `chroma`;
* `chroma` → использовать ChromaBackend;
* любое другое → явно raise ValueError с понятным сообщением.

НЕ добавлять FAISS пока.

Но подготовить безопасное место для будущего FAISS.

---

## 4. Обновить config минимально

Если в `utils/config.py` уже есть общий config object, добавь поле:

```python
rag_backend: str = "chroma"
```

Значение из env:

```env
RAG_BACKEND
```

Default:

```text
chroma
```

Важно:

* не ломать существующие env;
* не требовать обязательного наличия RAG_BACKEND;
* не менять старые CHROMA_* настройки.

---

## 5. Интеграция в query path

Найди, где сейчас создаётся/используется `ChromaRagStore` в runtime RAG query path.

Сделай минимальную замену:

```text
direct ChromaRagStore construction
→ retrieval factory
→ backend.search()
```

Но очень осторожно.

Если безопаснее оставить старый `ChromaRagStore` внутри `RagQueryService`, то допускается промежуточный вариант:

* `RagQueryService` принимает retrieval backend;
* default создаётся через factory;
* Chroma поведение остаётся прежним.

Главное:

* текущие RAG-запросы должны продолжить работать;
* формат ответа наружу не должен измениться;
* Admin UI не должен сломаться.

---

## 6. Observability: минимально

На этом шаге не строим полный telemetry contract.

Но добавь в debug/info logs хотя бы:

* active retrieval backend;
* collection count при healthcheck/startup, если это уже логируется;
* fallback/error при невозможности создать backend.

Не засоряй логи.

---

## 7. Тесты / smoke

Добавь или обнови минимальный smoke test/script, если в проекте уже есть подходящий.

Нужно проверить:

1. `RAG_BACKEND` отсутствует → используется Chroma.
2. `RAG_BACKEND=chroma` → используется Chroma.
3. `RAG_BACKEND=faiss` → понятная ошибка, что backend пока не реализован.
4. Старый RAG smoke test проходит.

Если есть `scripts/test_rag_regression.py`, не ломай его. При возможности добавь отдельный:

```text
scripts/test_retrieval_backend_factory.py
```

или аналогичный lightweight test.

---

# Ограничения

НЕ делать:

* FAISS backend;
* smart chunking;
* memory retrieval;
* hybrid retrieval;
* RAGAS;
* cache;
* RBAC;
* migrations;
* compose/env.example массовый рефакторинг;
* UI изменения.

---

# Критерии готовности

Работа считается готовой, если:

1. Появился `services/retrieval/` с base/chroma/factory.
2. Chroma path работает через adapter/factory или подготовлен максимально безопасный adapter без регресса.
3. Default backend = chroma.
4. Unsupported backend даёт явную ошибку.
5. Старые RAG сценарии не сломаны.
6. Есть краткий отчёт:

   * какие файлы изменены;
   * как протестировано;
   * какие риски остались;
   * что будет следующим шагом для FAISS.

---

## Session log (после выполнения)

*(ниже — append-only результаты работы)*

### Краткое summary (2026-05-11)

- Добавлен слой `services/retrieval/`: DTO + `RetrievalBackend`, `ChromaBackend` (делегирование в `ChromaRagStore`), фабрика `build_retrieval_backend` (только `chroma`; `faiss` и прочее — `ValueError`).
- В `AppConfig` поле `rag_backend` из `RAG_BACKEND` (по умолчанию `chroma`).
- `RagQueryService` принимает `RetrievalBackend`, поиск через `backend.search()` с тем же маппингом в `Document`/score.
- `build_rag_query_service` в `telegram_bot.py`: factory + лог health (`backend`, `collection_count`); при ошибке factory — лог и re-raise.
- Скрипты `rag_smoke_test.py`, `test_rag_regression.py` собирают backend через factory.
- Импорты: `factory` подгружает `ChromaBackend` лениво; `chroma_backend` не импортирует `langchain_core` на уровне модуля (атрибуты документа через `getattr`), чтобы лёгкий `test_retrieval_backend_factory.py` работал без полного стека RAG.

### Изменённые / добавленные файлы

- `services/retrieval/__init__.py`, `base.py`, `chroma_backend.py`, `factory.py`
- `utils/config.py`
- `services/rag_query_service.py`
- `interfaces/telegram_bot.py`
- `scripts/rag_smoke_test.py`, `scripts/test_rag_regression.py`
- `scripts/test_retrieval_backend_factory.py` (новый)

### Команды тестирования

```bash
python scripts/test_retrieval_backend_factory.py
python scripts/test_rag_regression.py   # требует OPENAI_API_KEY и окружение Chroma/embeddings
```

### Результаты

- `test_retrieval_backend_factory.py`: **OK** (в среде без `langchain_core` на глобальном import path).
- `test_rag_regression.py`: в данной среде не прогнан до конца — **FAIL: OPENAI_API_KEY is not set** (ожидаемо для песочницы без секретов).

### Оставшиеся риски

- Регресс RAG end-to-end не подтверждён автоматически без ключей и индекса.
- Индексация и `/stats` по-прежнему используют `ChromaRagStore` напрямую — два входа в Chroma до выноса indexing в abstraction.
- `__getattr__` в `retrieval/__init__.py` для `ChromaBackend`: при статическом анализе импорт может быть менее очевиден.

### Следующий рекомендуемый шаг (FAISS)

- Реализовать `FaissBackend`, ветку `RAG_BACKEND=faiss` в factory, общие тесты на одинаковый контракт `search`/`healthcheck`, затем поэтапное переключение compose/env без смены внешнего API.

---

### Regression script: порядок загрузки `.env` (append-only)

**Root cause:** в `scripts/test_rag_regression.py` проверялся `os.getenv("OPENAI_API_KEY")` до вызова `load_config()`, поэтому переменные из `.env` (через `load_dotenv()` / `_load_dotenv()` внутри `load_config`) ещё не попадали в процесс — операционный баг скрипта, не retrieval/config.

**Исправлено:** после `sys.path` добавлен импорт `load_config`; в начале `main()` сначала `config = load_config()`, затем проверка `config.openai_api_key`; дублирующий импорт `load_config` из блока провайдеров убран; неиспользуемый `import os` удалён.

**Повторный прогон (среда агента):**

- `python scripts/test_retrieval_backend_factory.py` → **OK**
- `python scripts/test_rag_regression.py` → после фикса проверка ключа не режет запуск «вхолостую» при ключе только в `.env`; в этой среде дальше **ModuleNotFoundError: No module named 'openai'** при импорте `OpenAIChatProvider` (нет зависимостей проекта в venv), не связано с порядком env.

**Подтверждение:** проблема была именно в порядке «проверка до `load_config()`»; исправление устраняет её без смены production semantics и retrieval.

---

### Operational decision: primary contour = GitHub / portfolio container (append-only)

**Решение:** дальнейшее развитие Assistant Flow и приёмка регрессий/интеграционных проверок (в т.ч. **P6+**) ведётся с опорой на **GitHub / portfolio container** как на **основной** development/runtime contour.

**Почему смена контура:** portfolio stack архитектурно чище, разворачивается **с нуля**, включает **свежий PostgreSQL**, лучше совпадает с **reproducible deployment** и **portfolio/distribution** стратегией, снижает **historical drift** и **hidden state**, ближе к **clean deployment model** для этапов **P6–P11**.

**Почему regression/tests именно там:** эталон проверки — **воспроизводимое** окружение, а не уникальное долгоживущее состояние старого server contour; иначе риск «тест прошёл на сервере из-за локального дрейфа, а чистый деплой сломан».

**Старый server contour:** не удаляется; не primary baseline; остаётся **fallback / reference / historical / сравнение при миграциях**.

**Это не migration task:** зафиксирована **смена первичного рабочего и проверочного контура**, без обязательства в этом же шаге переносить данные или переписывать compose/env под миграцию.

---

## P6.2a — FAISS secondary backend (append-only)

### Изменённые / добавленные файлы

- `services/retrieval/faiss_backend.py` — новый: `FaissBackend`, `resolve_faiss_index_dir`, константы имён файлов.
- `services/retrieval/factory.py` — ветка `faiss`, опциональный `chroma_store` только для `chroma`, для `faiss` обязателен `embeddings`, явные `ValueError` при отсутствии индекса (без fallback на Chroma).
- `services/retrieval/__init__.py` — ленивый экспорт `FaissBackend`.
- `utils/config.py` — `faiss_index_dir` / `FAISS_INDEX_DIR` (default `storage/faiss`).
- `interfaces/telegram_bot.py` — `build_retrieval_backend(..., embeddings=...)`, лог `index_dir` для FAISS, деталь health при `detail`, предупреждение если `ok=False`.
- `scripts/rag_smoke_test.py`, `scripts/test_rag_regression.py` — передача `embeddings` в factory.
- `scripts/test_retrieval_backend_factory.py` — сценарии chroma/faiss без молчаливого faiss-error.
- `scripts/build_faiss_demo_index.py` — новый: демо-корпус + OpenAI embeddings + запись `vectors.faiss` / `chunks.json` / `manifest.json`.
- `scripts/test_retrieval_backend_parity.py` — новый: smoke сравнения Chroma (best-effort) + FAISS.
- `requirements.txt` — `faiss-cpu>=1.8.0`.

### Как устроен FAISS storage

- Каталог из `FAISS_INDEX_DIR` (относительно **корня репозитория** при сборке factory из `services/retrieval/factory.py` через `project_root=parents[2]`).
- Файлы: **`vectors.faiss`** (IndexFlatL2, float32), **`chunks.json`** (массив `{page_content, metadata}` в порядке id строк FAISS), опционально **`manifest.json`** (`embedding_dim`, `embedding_model`).
- Не пересекается с Chroma persist и не использует PostgreSQL.

### Metadata mapping

- `chunks.json[i]` соответствует вектору с id `i` в FAISS (как в legacy PEr01, но схема под `RetrievalChunk`: `page_content` + `metadata` dict).
- `search` возвращает `RetrievalSearchResult` с **L2 distance** как `score` (сопоставимо с Chroma L2 в query path).

### Тестирование (команды)

```bash
pip install -r requirements.txt   # подтянуть faiss-cpu
python scripts/test_retrieval_backend_factory.py
python scripts/build_faiss_demo_index.py          # нужен OPENAI_API_KEY
python scripts/test_retrieval_backend_parity.py   # после сборки индекса
RAG_BACKEND=faiss python run_telegram_bot.py      # только при готовом индексе; иначе ValueError при старте
```

### Результаты в среде агента

- `test_retrieval_backend_factory.py`: **OK** (после `pip install faiss-cpu`).
- Полный прогон `build_faiss_demo_index` / `parity` / бот с FAISS не выполнялся здесь из‑за отсутствия полного venv (`langchain_openai` и т.д.) — ожидается на portfolio-контуре с `.env`.

### Operational риски

- `RAG_BACKEND=faiss` без индекса → **жёсткий ValueError** при `build_retrieval_backend` (бот не стартует) — намеренно, без silent Chroma.
- Пустой индекс (`ntotal=0`) → `healthcheck` **ok=False**; поиск пустой.
- Расхождение размерности embeddings ↔ индекс → ошибка при `search`.
- Два независимых источника истины для корпуса (Chroma vs FAISS) до будущего hybrid — рассинхрон содержимого **не** диагностируется автоматически.

### Future: indexing abstraction

- Нет `add_chunks`/`reset` в `RetrievalBackend`; сбор индекса только через **`build_faiss_demo_index`** (offline). Дальше: общий indexing interface, единая политика reindex/invalidation.

### Future: backend parity / hybrid

- Сейчас: общий контракт `search` + L2 score + DTO; **нет** merge KB+memory, **нет** нормализации scores между backend, **нет** единого corpus revision. Для hybrid понадобятся политика merge, бюджет контекста и согласованная ревизия знаний.

### Что уже даёт задел под hybrid

- Единый `RetrievalBackend` + фабрика по `RAG_BACKEND`; второй backend изолирован на диске; тот же embedding provider AF для запроса и (в demo script) для индексации.

### Чего не хватает до hybrid

- Индексация в контракте backend, согласование lifecycle с PostgreSQL, merge ранжирования, feature flags, observability нормализации между Chroma distance и FAISS L2 при смешении результатов.

---

## P6.2b — retrieval stabilization (append-only)

### Суть

Закрытие архитектурных дыр перед hybrid: контракт scores (backend-local), минимальный metadata contract с safe defaults, единая интерпретация `RetrievalHealth`, компактный лог retrieval (backend, top_k, retrieved_count, latency_ms) без текста запроса и без dump чанков, smoke-скрипт стабилизации.

### Изменённые / добавленные файлы

- `PROJECT_STATE.md` — §29 (scores, metadata, health, legacy note).
- `services/retrieval/base.py` — docstrings `RetrievalChunk`, `RetrievalSearchResult`, `RetrievalHealth`, `search` в Protocol.
- `services/retrieval/chunk_metadata.py` — новый: `apply_retrieval_metadata_contract`.
- `services/retrieval/chroma_backend.py`, `services/retrieval/faiss_backend.py` — обогащение metadata при `search`.
- `services/rag_query_service.py` — строка `[assistant-flow] rag retrieval: backend=… top_k=… retrieved_count=… latency_ms=…` (+ timeout-ветка).
- `scripts/test_retrieval_stabilization_smoke.py` — новый operational smoke.

### Что протестировано

- `python scripts/test_retrieval_stabilization_smoke.py` — логика: сначала **faiss_synthetic** без `langchain_openai`; затем при `OPENAI_API_KEY` и полном стеке — Chroma + опционально реальный `FAISS_INDEX_DIR`. В среде агента без `pip`/`faiss-cpu` блок synthetic вернул отсутствие faiss — прогон end-to-end не подтверждён; на portfolio с `requirements.txt` ожидается **OK**.

### Риски перед P6.3 (smart chunking)

- Синтетический `chunk_id` по рангу не заменяет стабильный id из индексации — до появления indexing abstraction возможны коллизии смысла в отчётах.
- Два лога latency: компактный `rag retrieval` + существующие `rag retrieve` / diagnostics — частичное дублирование по времени (разная гранулярность).

### Readiness к этапу smart chunking

- Контракт metadata и дисциплина scores зафиксированы в PROJECT_STATE и в коде комментариями; read-path не требует reindex для базовых полей.
- Готовность к chunking: можно вводить `document_id` / `version_id` в metadata на этапе индексации, не ломая читателей (backward-compatible).

---

## P6.3 — Smart Chunking Foundation (append-only)

### Суть

Введён каталог **`services/chunking/`**: контракты `ChunkingDocument`, `ChunkingResult`, `ChunkMetadata`, `Chunker`, детерминированный **`SmartChunker`** (paragraph-aware, bounded overlap, лимиты target/max, fallback для длинных абзацев, предупреждение при очень большом числе chunk’ов). Телеметрия: одна строка `chunking: strategy=… chunks_created=… avg_chunk_size=… max_chunk_size=…` без дампа текста.

### Интеграция

- **`services/rag_document_loader.py`** — `load_and_split_file` использует `SmartChunker.split_langchain_documents` вместо LangChain `RecursiveCharacterTextSplitter`.
- **`services/admin_knowledge_indexer.py`** — `_load_split_txt_md_for_index` аналогично.

### Файлы

- `services/chunking/__init__.py`, `base.py`, `smart_chunker.py`
- правки: `services/rag_document_loader.py`, `services/admin_knowledge_indexer.py`
- `scripts/test_smart_chunking_smoke.py`
- `PROJECT_STATE.md` — §30

### Тесты

- `python scripts/test_smart_chunking_smoke.py` — **OK** (короткий текст, длинные абзацы, большой документ, pathological long line).

### Риски перед conversational memory

- Character-based границы не совпадают с token windows LLM; возможны расхождения с экономикой embeddings до token-aware этапа.
- Сильно неоднородные PDF (таблицы/колонтитулы) без отдельного layout-слоя остаются источником шума.

### Readiness к conversational memory

- Chunk metadata несёт `chunk_index` / `total_chunks` / `chunking_strategy` / `approximate_size` и пробрасывает `document_id` / `version_id`, если уже есть в базовом metadata — задел для связки с сессией без смены внешнего API.

---

## P6.3 — Conversational Memory Foundation (append-only)

### Задание (полный текст)

Полная постановка задачи P6.3 «Conversational Memory Foundation» — в пользовательском сообщении чата (Cursor) относительно этого этапа; здесь — конспект требований: foundation для persistent conversational memory; **не** hybrid retrieval; **не** semantic memory / Chroma memory vectors; **не** LLM summarization; **не** RBAC/UI; **не** migrations без необходимости; **не** переписывание orchestrator; **не** изменение ответов Telegram; **не** сохранение RAG context в dialog history; только **dialog history access** с budget и observability.

### Инвентаризация (что было до слоя)

- Схема `database/schema.sql`: таблицы `chat_sessions` (user_id, mode, is_active, timestamps), `chat_messages` (session_id, user_id, role, content, modality, metadata JSONB, execution_id, intake_event_id, created_at).
- Ранее `SessionRepository` / `ChatSessionService` / часть user path были заглушками или не использовались для стабильной записи истории из Telegram; in-memory RAG history остаётся в `utils/telegram_user_state.py` для контекста RAG и **не** заменяется семантикой PG на этом шаге.
- Запись user/assistant в PG выполняется через `SessionRepository.append_message` и `ChatSessionService.record_message`; связь с `execution_id` опциональна в metadata/колонке.

### Что реализовано

- `services/memory/`: `ConversationMemoryRecord`, `ConversationMemoryQuery`, `MemoryBudgetPolicy`, `ConversationMemoryService` (`get_recent_messages`, `get_session_messages`, `append_user_message`, `append_assistant_message`), комментарии о разделении **dialog history** / **semantic memory** / **KB retrieval context**.
- Реализации репозитория сессий и `AppUserService.ensure_user_for_telegram` для связки Telegram → `app_users` → session.
- `persist_telegram_dialog_turn_best_effort`: при наличии `DATABASE_URL` — ensure user, session, два append (user + assistant), компактный лог без текста сообщений.
- Интеграция в `interfaces/telegram_bot.py`: после успешной отправки — RAG path, text orchestrator path, voice→text path (транскрипт как user text).
- `scripts/test_conversation_memory_smoke.py`: сессия, append, порядок (chronological), trim по `max_message_chars`, metadata JSONB.

### Изменённые / добавленные файлы

- `services/memory/__init__.py`, `services/memory/base.py`, `services/memory/conversation_memory_service.py`
- `repositories/session_repository.py`, `repositories/user_repository.py`, `services/chat_session_service.py`, `services/app_user_service.py`
- `interfaces/telegram_bot.py`
- `scripts/test_conversation_memory_smoke.py`
- `PROJECT_STATE.md` — §31

### Тесты

- Команда: `python scripts/test_conversation_memory_smoke.py` (из корня репозитория, с `DATABASE_URL` в окружении). Без БД скрипт печатает `SKIP` и выходит с кодом 0.
- Прогон в образе против уже поднятого portfolio Postgres (порт 5433 на хосте):  
  `docker compose -f docker-compose.portfolio.yml build assistant-flow`  
  затем одноразово:  
  `docker run --rm --network host -e DATABASE_URL=postgresql://assistant:assistant@127.0.0.1:5433/assistant_flow assistant-flow-assistant-flow:latest python scripts/test_conversation_memory_smoke.py`  
  либо в поднятом контейнере `assistant-flow` (primary contour `portfolio-test-*`, проект `-p portfolio-test`):  
  `docker compose -p portfolio-test -f docker-compose.portfolio.yml exec assistant-flow python scripts/test_conversation_memory_smoke.py`  
  — расширенный smoke: **OK** (`OK: test_conversation_memory_smoke`, exit 0), подтверждено прогоном образа после `build` (в т.ч. с `docker run --network host` к Postgres :5433).

### Риски

- Дублирование смысла in-memory RAG history и PG dialog history до этапа унификации источников для RAG.
- Character budget не равен token budget LLM.
- Ошибки БД глушатся в best-effort persist — история может пропускаться без сигнала пользователю.

### Перед hybrid retrieval / semantic memory retrieval

- Нужны: стабильные id сообщений в логах/трассировке, политика retention, token-aware budget, явный отдельный store/namespace для semantic memory, согласование с RBAC если появится multi-tenant.

### Готовность базы к semantic memory retrieval

- **Структурно готовы** таблицы и слой чтения/записи dialog history; **не готовы** к semantic retrieval: нет embedding store для memory, нет ranking и отдельного retrieval pipeline — это следующие этапы.

---

## P6.3 — Conversational Memory: архитектурные уточнения и инвентаризация (append-only)

### Existing persistence paths (до / вместе с этапом)

- **Уже в схеме:** `chat_sessions`, `chat_messages` (`database/schema.sql`) — колонки `session_id`, `user_id`, `role`, `content`, `modality`, `metadata` JSONB, `execution_id`, `intake_event_id`, `created_at`.
- **Lifecycle / observability:** `services/runtime_lifecycle_service.py` и intake/processing events — **отдельный** контур от conversational memory; correlation с `execution_id` в memory **опциональна**, без обязательности для старых строк.
- **RAG in Telegram:** `utils/telegram_user_state.py` — in-memory `conversation_history` для **KB-контекста** в `rag_service.answer`; **не** переносится в векторный store и **не** объявляется SoT для персистентной истории; PG dialog history дополняет продуктовый след, не заменяя RAG history на этом шаге.
- **Запись в PG:** единый технический путь append — `SessionRepository.append_message` → `ChatSessionService.record_message`; memory layer **не** дублирует SQL параллельным репозиторием.

### Reused vs newly introduced

- **Reused:** таблицы и контракт БД без новых миграций; `ChatSessionService` / `SessionRepository` как **source of truth** для строк сообщений.
- **Newly introduced:** каталог `services/memory/` как **явный subsystem** (DTO, policy, `ConversationMemoryService`, `persist_telegram_dialog_turn_best_effort`); компактные `memory:` логи с `limit` и `latency_ms` на read/append; char-budget на read без превышения суммарной длины выдачи; smoke-расширения.

### Intentionally avoided overengineering

- Нет второго competing persistence layer для тех же таблиц.
- Нет embeddings / vector index для dialog history.
- Нет переписывания orchestrator и смешения KB retrieval path с memory read API.
- Нет обязательного `execution_id` и миграций только под correlation.

### Сохранённые архитектурные ограничения

- **dialog history ≠ semantic memory ≠ KB retrieval context** — зафиксировано в коде и `PROJECT_STATE` §31.
- **Hybrid retrieval и semantic memory retrieval** — **намеренно отложены** (нет runtime-path, нет memory-only vector storage).
- **Token-aware budget** — отложен; на этапе только **char-based** deterministic limits.

### Почему semantic retrieval отложен

- Нужны отдельный embedding store/namespace, политика retention, согласование с token budget и безопасностью (history hygiene уже критична для future hybrid); преждевременный semantic path размыл бы границы с KB и усложнил бы observability.

### Тесты (portfolio contour)

- Сборка образа: `docker compose -f docker-compose.portfolio.yml build assistant-flow`.
- Выполнение в контейнере сервиса (пример для стека `portfolio-test-*`):  
  `docker compose -f docker-compose.portfolio.yml exec assistant-flow python scripts/test_conversation_memory_smoke.py`  
  (требуется уже поднятый `assistant-flow` с валидным `DATABASE_URL` на postgres в той же compose-сети.)
- Альтернатива одноразового прогона с доступом к Postgres на хосте `:5433`:  
  `docker run --rm --network host -e DATABASE_URL=postgresql://assistant:assistant@127.0.0.1:5433/assistant_flow assistant-flow-assistant-flow:latest python scripts/test_conversation_memory_smoke.py`

### Готовность архитектуры

- **К semantic memory:** задел есть (отдельный subsystem, contracts, namespace separation в документации); **не готово** к runtime semantic retrieval (нет embeddings store для memory, нет ranking).
- **К hybrid retrieval:** **не готово** — hybrid намеренно не строился; dialog layer изолирован от KB path.

### Ограничения перед P6.4

- Два канала контекста (in-memory RAG history vs PG dialog) до продуктового решения.
- Char budget ≠ tokens.
- Best-effort persist скрывает сбои БД от пользователя.
- Нет retention/TTL policy на уровне приложения.

### Результат расширенного smoke (фактический прогон)

- После `docker compose -f docker-compose.portfolio.yml build assistant-flow`:  
  `docker run --rm --network host -e DATABASE_URL=postgresql://assistant:assistant@127.0.0.1:5433/assistant_flow assistant-flow-assistant-flow:latest python scripts/test_conversation_memory_smoke.py` → **OK**, exit 0; в логах — `budget_applied=true` при tight total budget, поля `limit` и `latency_ms` на read path.

---

## Operational testing rule + P6.4 Hybrid Retrieval Foundation (append-only)

### Полный prompt (конспект)

Зафиксировано **operational testing rule** (только `portfolio-test-assistant-flow-1` после rebuild для DB/RAG/runtime smoke; host — только pure unit без DB/Chroma). Реализация **P6.4**: отдельный `services/hybrid_retrieval/` (context assembly, не retriever backend); `ENABLE_HYBRID_RETRIEVAL=false` по умолчанию; `HybridRetrievalPolicy` (max_kb_chunks, max_memory_messages, max_context_chars, max_memory_chars, max_kb_chars); KB priority над memory; без semantic memory / vector memory / RAGAS / cache; без score mixing; детерминированный порядок KB → memory; observability без dump текста; smoke `scripts/test_hybrid_retrieval_smoke.py`; интеграция в `RagQueryService.answer` только при flag + `hybrid_session_id`.

### Изменённые / добавленные файлы

- `services/hybrid_retrieval/__init__.py`, `base.py`, `hybrid_context_service.py`
- `utils/config.py`, `.env.example`
- `services/rag_query_service.py`
- `scripts/test_hybrid_retrieval_smoke.py`
- `PROJECT_STATE.md` — §32 (operational rule), §33 (P6.4)

### Что реализовано

- `HybridContextService.build`: сборка KB items + optional dialog memory через `ConversationMemoryService`; финальный cap по `max_context_chars`; лог `[assistant-flow] hybrid: ...`.
- `RagQueryService.answer(..., hybrid_session_id=..., hybrid_user_id=...)`: при `enable_hybrid_retrieval` и непустом `hybrid_session_id` подмена строки контекста для LLM; расширенный system prompt только если в результате есть memory items.
- Telegram **по умолчанию** не передаёт `hybrid_session_id` — пользовательское поведение без изменений.

### Что протестировано / команды

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python scripts/test_hybrid_retrieval_smoke.py
```

Фактический прогон: `docker compose -p portfolio-test -f docker-compose.portfolio.yml build assistant-flow` + `up -d assistant-flow`, затем `docker exec portfolio-test-assistant-flow-1 python scripts/test_hybrid_retrieval_smoke.py` → **OK**, exit 0.

### Intentionally deferred

- Semantic memory embeddings, Chroma/FAISS для memory, LLM summarization memory, reranking, нормализация score между KB и memory, RAGAS, кэш.

### Риски перед P6.5

- Два источника «истории» (in-memory RAG vs PG) при включении hybrid в RAG понадобится явный выбор session id и согласование с Telegram.
- Char caps ≠ token economics LLM; финальный hard truncate контекста может резать посимвольно (ASCII-safe в тестах).
- Final `context_text` cap после заголовков секций — грубый guard; token-aware сборка — позже.

### Готовность: semantic memory / RAGAS

- **Semantic memory retrieval:** не готово (нет embeddings/ranking для memory namespace).
- **RAGAS evaluation:** не готово (нет датасетов/метрик/instrumentation под RAGAS).

### Ограничения перед P6.5

- Проброс `hybrid_session_id` из Telegram в `rag_service.answer`, политика приоритетов при частично пустом KB, UX и security review гибридного промпта.

---

## P6.5 — RAG Evaluation Foundation / RAGAS-ready layer (append-only)

### Полный prompt (конспект)

Offline evaluation для RAG: retrieval quality / answer relevance / grounding readiness через подсистему `services/evaluation/`; dataset JSON; internal deterministic metrics; RAGAS-ready rows (`question`, `answer`, `contexts`, `ground_truth`) с graceful skip без обязательного `ragas` в requirements; скрипт `scripts/evaluate_rag_smoke.py` → `outputs/evaluation/rag_smoke_report.json`; env `ENABLE_RAGAS_EVALUATION=false`, `RAG_EVAL_DATASET_PATH`, `RAG_EVAL_OUTPUT_DIR`; без Admin UI, production monitoring, async jobs, изменений runtime RAG/Telegram; operational rule §32 для прогона в `portfolio-test-assistant-flow-1`.

### Файлы

- `services/evaluation/__init__.py`, `base.py`, `rag_evaluation_service.py`, `ragas_adapter.py`
- `evaluation/datasets/rag_smoke_dataset.json`
- `scripts/evaluate_rag_smoke.py`
- `utils/config.py`, `.env.example`
- `PROJECT_STATE.md` — §34

### Legacy ideas (reuse без копипаста)

- Концепция «вопрос → ответ → контексты → метрики» из PEr06/PEr08; адаптация под `RagQueryService` и текущий retrieval abstraction.

### Intentionally deferred

- Полный RAGAS `evaluate()` с judge LLM; async evaluation; UI; кэш; RBAC; обязательная зависимость `ragas` в requirements.

### Команды rebuild / test

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python scripts/evaluate_rag_smoke.py
```

### Результаты smoke и report

- `docker compose -p portfolio-test -f docker-compose.portfolio.yml build assistant-flow` + `up -d assistant-flow`, затем `docker exec portfolio-test-assistant-flow-1 python scripts/evaluate_rag_smoke.py` → **OK: evaluate_rag_smoke**, exit 0.
- Сводка прогона: `total_questions=7`, `internal_checks_passed=6`, `avg_context_count≈1.29`, `avg_source_count≈1.29`, `ragas_status=skipped`, `ragas_detail=ENABLE_RAGAS_EVALUATION=false`.
- Отчёт: `/app/outputs/evaluation/rag_smoke_report.json` (на хосте при bind — под `outputs/evaluation/` в корне репозитория, каталог в `.gitignore`).

### Риски перед P6.6 (cache / optimization)

- Smoke dataset generic — риск ложных срабатываний эвристик при пустом или шумном индексе.
- Отчёт в `outputs/` (часто gitignored) — артефакты CI нужно сохранять отдельно при необходимости.
- Внутренние метрики не заменяют RAGAS faithfulness/context precision с LLM-judge.

### Готовность к полноценному RAGAS / production benchmark

- **RAGAS:** структура данных готова; **не готово** к production RAGAS без curated dataset, стабильного judge, версионирования промптов и регрессионной политики.
- **Production benchmark:** нужны фиксированный корпус, эталонные ответы/релевантность, offline/CI контур, хранение отчётов вне только локального `outputs/`.

---

## P6.6 — Retrieval Optimization & Cache Foundation (append-only)

### Полный prompt (конспект)

Локальный SQLite cache subsystem (`services/cache/`): `CacheStore` контракт, `SqliteCacheStore`, namespaces `query` / `retrieval` / `answer` / `evaluation`; fingerprint retrieval (query, backend, top_k, embedding model, `RAG_RETRIEVAL_GENERATION`, hybrid flag); `CachingRetrievalBackend` + `ENABLE_RETRIEVAL_CACHE=false` default; не кэшировать пустой retrieval / errors; `invalidate_retrieval_cache`; `AnswerCacheService` + `ENABLE_ANSWER_CACHE=false` без интеграции в RAG LLM path; observability без dump query/chunks; smoke `test_cache_foundation_smoke.py` + `test_retrieval_cache_smoke.py`; hook после `admin_index_documents`; без Redis/distributed/async workers; operational rule §32.

### Файлы

- `services/cache/__init__.py`, `base.py`, `sqlite_cache.py`, `retrieval_cache_key.py`, `retrieval_serializers.py`, `caching_retrieval_backend.py`, `invalidate.py`, `answer_cache_service.py`
- `services/retrieval/factory.py` — опциональная обёртка
- `scripts/test_cache_foundation_smoke.py`, `scripts/test_retrieval_cache_smoke.py`
- `scripts/admin_index_documents.py` — вызов `invalidate_retrieval_cache` после успешной индексации
- `utils/config.py`, `.env.example`
- `PROJECT_STATE.md` — §35

### Legacy ideas

- Локальный кэш результатов поиска (идея из monolith eval / RAG pipelines) — только как reference; реализация под AF контракты и feature flags.

### Intentionally deferred

- Redis, cluster cache, async workers, answer cache в production RAG path, кэш PII/hybrid memory/raw prompts, Admin UI metrics.

### Команды rebuild / test

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python scripts/test_cache_foundation_smoke.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_retrieval_cache_smoke.py
```

### Результаты smoke

- Host: `python scripts/test_cache_foundation_smoke.py` → **OK**, exit 0.
- `portfolio-test-assistant-flow-1` после `docker compose … build assistant-flow` + `up -d assistant-flow`:  
  `docker exec portfolio-test-assistant-flow-1 python scripts/test_cache_foundation_smoke.py` → **OK**, exit 0.  
  `docker exec portfolio-test-assistant-flow-1 python scripts/test_retrieval_cache_smoke.py` → **OK**, exit 0; в логах виден **miss_set** затем **hit** с тем же `key_hash_prefix` и низкой `latency_ms` на hit.

### Риски перед P6.7 Security Groundwork

- Stale retrieval cache без bump `RAG_RETRIEVAL_GENERATION` / revision (риск задокументирован в §35).
- SQLite file locking при высокой конкуренции; нет шифрования at-rest на этом этапе.
- Answer cache в runtime потребует PII/политики и согласования с compliance.

### Готовность: Redis / answer cache

- **Redis:** не готово (локальный SQLite foundation только).
- **Answer cache:** контракт `AnswerCacheService` готов; **не готово** к production answer caching без security review и интеграции в RAG.

