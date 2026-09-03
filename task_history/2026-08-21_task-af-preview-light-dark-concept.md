# Задача: анализ Assistant Flow и концепции Light/Dark preview

## Исходное задание

Провести анализ Assistant Flow (AF) и подготовить концепции Light/Dark preview для карточки проекта в AI Portfolio.

Ограничения этапа:
- НЕ генерировать изображения;
- НЕ писать финальные ImageGen-промпты;
- НЕ менять код, БД, конфигурацию или deployment;
- НЕ исправлять обнаруженный технический долг.

Требуется исследовательский отчёт, на основании которого отдельно будут выбраны и подготовлены сцены Light и Dark.

## Статус

completed

---

# 1. Executive Summary

Assistant Flow (AF) — это реально работающая мультимодальная AI-платформа с RAG и операционной консолью. Пользовательский контур построен вокруг Telegram-бота; операторский контур — вокруг FastAPI Admin API + React Admin UI.

Главная ценность для портфеля: **RAG-ассистент по корпоративной базе знаний с прозрачной диагностикой поиска**. Пользователь задаёт вопрос в Telegram, система ищет релевантные фрагменты документов и формирует ответ, а оператор в Admin UI видит, какие чанки были найдены, с какими скорами, через какой retrieval backend и какая модель отвечала.

Рекомендуемая пара preview:
- **Light** — пользовательский Telegram-сценарий RAG-вопроса про «ООО НоваТех» и полученный ответ.
- **Dark** — операторская RAG-консоль Admin UI с найденными чанками, retrieval scores, backend Weaviate и таймлайном обработки.

Это две содержательно разные сцены одного продукта: user contour vs operator/observability contour.

---

# 2. Источники и фактическая база

| Источник | Что проверено |
|---|---|
| `cases/assistant-flow/README.md` | Публичное описание платформы, возможности, стек, архитектура. |
| `cases/assistant-flow/PROJECT_STATE.md` | Инженерное состояние, решения, известные проблемы, roadmap. |
| `cases/assistant-flow/.env.portfolio-test` | Реальные настройки запущенного стека: ключи, модели, backend, флаги. |
| `cases/assistant-flow/docker-compose.portfolio.yml` | Состав сервисов: postgres, chroma, weaviate, assistant-flow, admin-api, admin-ui. |
| `cases/assistant-flow/database/schema.sql` | Схема PostgreSQL: users, sessions, messages, documents, chunks, logs, evaluation. |
| `cases/assistant-flow/core/orchestrator.py` | Бизнес-оркестратор text/image route, prompt enhancement, image pipeline. |
| `cases/assistant-flow/interfaces/telegram_bot.py` | Telegram handlers: text, rag, ocr, voice, commands. |
| `cases/assistant-flow/services/retrieval/runtime_manager.py` | Resolution активного retrieval backend (env + platform_settings). |
| `docker ps` на VPS | Running containers: `assistant-flow-*` (admin-ui, assistant-flow, admin-api, postgres, chroma, weaviate). |
| `curl http://localhost:8600/api/health` и `/api/overview` | Backend UP, effective backend Weaviate, Chroma/FAISS/Weaviate READY, 427/424 chunks. |
| БД `assistant_flow` в `assistant-flow-postgres-1` | Реальные данные: 22 документа, 427 чанков, 50 сессий, 657 сообщений, 310 intake-событий, 2271 processing-лог, 27 evaluation-ранов. |
| `cases/assistant-flow/docs/screenshots/` | Существующие скриншоты UI и текущие `AF_portfolio_light.png`/`AF_portfolio_dark.png` (низкое разрешение). |
| `cases/ai-portfolio/src/experiments/portfolio-v2-3plus9-dualtheme.html` | Текущее использование AF preview в портфолио. |

**Важное уточнение по runtime.** Канонический compose-проект в документации AF называется `portfolio-test`, но на VPS сейчас поднят стек с префиксом контейнеров `assistant-flow-*` (вероятно, запущен без явного `-p portfolio-test`). Внутри Postgres база называется `assistant_flow`. Данные в БД реальные и были перенесены предшественником при миграции AF в структуру APL.

---

# 3. Что реально представляет собой Assistant Flow

## 3.1 Продуктовый сценарий

- **Кого решает задачу:** компаниям с корпоративной базой знаний (регламенты, FAQ, инструкции), которыми сотрудники плохо пользуются.
- **Пользователь:** сотрудник или внешний клиент в Telegram.
- **Что передаёт:** текстовый вопрос, фото (OCR), голосовое сообщение (foundation) или запрос на генерацию изображения.
- **Что происходит:** запрос маршрутизируется по режиму (text / rag / image / ocr), проходит через memory, AI-провайдер, retrieval backend, asset storage; результат отправляется обратно в Telegram.
- **Где AI/LLM:**
  - GigaChat-Max для prompt enhancement и text-ответов;
  - OpenAI `text-embedding-3-small` для embeddings;
  - OpenAI `gpt-4o-mini` для RAG-ответов;
  - OpenAI Vision для OCR;
  - ProxyAPI/OpenAI-compatible для image generation.
- **Ветвления / маршрутизация:**
  - `/mode text` — обычный диалог;
  - `/mode rag` — вопросы по базе знаний;
  - `/mode ocr` — распознавание текста с фото;
  - keyword routing для image generation («нарисуй», «draw»).
- **Внешние системы / каналы:** Telegram Bot API, PostgreSQL, ChromaDB, Weaviate, FAISS, OpenAI, GigaChat, ProxyAPI, filesystem asset storage.
- **Пользователь получает:** ответ в Telegram — текст, изображение или распознанный текст.
- **Оператор/администратор получает:** в Admin UI — список сессий, детальную трассу обработки, найденные чанки, retrieval scores, backend, latency, модель.
- **Сохраняемые данные:** intake events, chat sessions/messages, documents/versions/chunks, processing logs, error logs, evaluation runs/items/metrics, generated assets, admin audit log.

## 3.2 Реальный E2E (короткая цепочка)

```text
Telegram: «Что ты знаешь про ООО НоваТех?»
  → intake_event (source=telegram, mode=rag)
  → route_selected = rag
  → memory_load (последние пары из chat_messages)
  → embedding через OpenAI
  → retrieval backend Weaviate, top_k=3
  → answer через gpt-4o-mini
  → Telegram reply
  → processing_logs + chat_messages сохранены
  → Admin UI показывает chunks, scores, latency, model
```

## 3.3 Подтверждения в code/runtime/DB

- Режим маршрутизации: `interfaces/telegram_bot.py:1631` (`mode == 'rag'`).
- RAG pipeline: `services/rag_query_service.py`, `services/retrieval/runtime_manager.py`.
- Memory load: `processing_logs` stage `memory_load_started/done` для execution `a4f7dbd2-...`.
- Retrieval backend: `platform_settings.active_rag_backend = '{"backend": "weaviate"}'`; `/api/overview` → `"effective_backend":"weaviate"`.
- Ответ и чанки: `chat_messages` + `processing_logs` для execution `a4f7dbd2-...`.
- Скора retrieval: `[0.4645, 0.6293, 0.6486]` из `rag_answer_done`.

---

# 4. REAL / PARTIAL / DECLARED / LEGACY / DEBT

## 4.1 REAL — реально работает

| Компонент | Подтверждение |
|---|---|
| Telegram text mode | 339 user / 318 assistant text-сообщений; `text_answer_done` success. |
| Telegram RAG mode | 19 rag-сессий; `rag_answer_done` success 274 раза. |
| Multiple retrieval backends | Chroma, FAISS, Weaviate — все READY в `/api/overview`; `processing_logs` фиксирует backend. |
| Documents + indexing | 22 документа, 36 версий, 427 чанков; indexing_jobs 2019 записей. |
| Memory / диалог | `chat_sessions` + `chat_messages`; `memory_load/append_done` stages. |
| Admin UI React/Vite | Running container `assistant-flow-admin-ui-1`, порты 8080. |
| Admin API endpoints | `/api/health`, `/api/overview`, `/api/summary`, `/api/logs/recent`, `/api/documents`, `/api/rag-turns` и др. |
| Processing logs / observability | 2271 processing log, трассировка по execution_id. |
| Evaluation layer | 27 evaluation runs, 189 evaluation items, RAGAS-метрики. |
| Healthcheck layer | `/api/health` показывает postgres, chroma, rag, llm-провайдеры. |
| Admin audit log | 354 записи. |

## 4.2 PARTIAL — реализовано частично

| Компонент | Статус |
|---|---|
| Voice / audio | UI-страница и asset storage есть, но `STT_PROVIDER=disabled`, `TTS_PROVIDER=disabled`; в логах только 3-4 `stt_completed`. |
| Image generation | Pipeline код есть, `generated_assets=0`, `image_provider_done` — 4 error; в реальном запуске не работает стабильно. |
| Retrieval cache | `ENABLE_RETRIEVAL_CACHE=false` в `.env`, `enable_retrieval_cache=true` в tuning, но `cache_state` в processing_logs отсутствует. |
| `request_logs` | Таблица есть, count = 0 — телеметрия не пишется в основной hot path. |
| `outbox` | Таблица есть, count = 0 — сообщения отправляются напрямую через Telegram API. |
| Token economy visibility | Декларируется, но `request_logs` пуста, нормализованная телеметрия не собрана. |

## 4.3 DECLARED — заявлено, но не подтверждено реализацией

- RBAC/auth: `AF_AUTH_MIDDLEWARE_MODE=disabled` в `.env`, auth endpoints есть, но защита выключена.
- Multi-tenant isolation: не реализована.
- Async workers / background task queue: schema `async_jobs` есть, но основной путь синхронный.
- S3/object storage backend: только `filesystem`.
- Production deployment mode для React UI beyond dev/Vite workflow.
- Полноценный token economy telemetry.

## 4.4 LEGACY

- Streamlit Admin UI — историческая основа, заменена на FastAPI + React.
- `/opt/assistant-flow/` — старый путь, сохранён как резервная копия.
- Старые режимы `career`, `hr_screening` в `chat_sessions.mode` — остатки от Career Knowledge Assistant.

## 4.5 DEBT — существующие проблемы текущей реализации

- **Скрытое переключение retrieval backend.** `RAG_BACKEND=chroma` в `.env`, но `platform_settings.active_rag_backend = weaviate`. Это operational риск, не должен визуализироваться как простота.
- **Пустые `request_logs`/`outbox`** при наличии полной схемы — архитектурная асимметрия.
- **Image generation нестабилен** — из-за бюджета/провайдера.
- **Heavy RAG instability** после reindex на больших документах (VPS RAM ~2 GB).
- **Audio включён, но провайдеры disabled** — конфигурационное противоречие.

---

# 5. Реальный E2E

## 5.1 Короткая цепочка

```text
ВХОД: Telegram вопрос «Что ты знаешь про ООО НоваТех?»
  → Telegram bot handler
  → intake_event + processing log: intake_received, route_selected = rag
  → memory_load (PostgreSQL chat_messages, limit=6)
  → OpenAI embedding → Weaviate retrieval, top_k=3
  → OpenAI gpt-4o-mini answer
  → Telegram reply
  → memory_append + processing_done
  → Admin UI RAG page: chunks + scores + model + backend
РЕЗУЛЬТАТ: пользователь получает ответ; оператор видит диагностику.
```

## 5.2 Подробная цепочка с подтверждениями

1. **Вход:** `chat_messages` для `execution_id = a4f7dbd2-268a-4428-87b8-7d1cf6f7516d`:
   - user: `Что ты знаешь про ООО НоваТех?`
   - assistant: `ООО «НоваТех» — общество с ограниченной ответственностью, зарегистрированное 14 марта 2019 года...`

2. **Маршрутизация:** `processing_logs`:
   - `intake_received` success, mode=rag
   - `route_selected` success, route=rag

3. **Memory:** `processing_logs`:
   - `memory_load_started` / `memory_load_done`, limit=6, latency_ms=73
   - `memory_append_done`, status=persisted

4. **Retrieval:** `processing_logs` stage `rag_answer_done`:
   - `llm_model`: gpt-4o-mini
   - `top_k`: 3
   - `scores`: `[0.46454524993896484, 0.6292791366577148, 0.6485806107521057]`
   - backend: weaviate (из `retrieval_backend` в processing logs, подтверждено `/api/overview`)

5. **Вывод:** Telegram message с ответом; `chat_messages` сохраняет реплики.

6. **Observability:** Admin UI `/rag` показывает execution_id, question, answer, found chunks, scores, latency, model.

---

# 6. Реальные данные и сценарии для preview

## 6.1 Реальные пользовательские запросы

| # | Запрос | Режим | Ответ | Источник |
|---|---|---|---|---|
| 1 | Что ты знаешь про ООО НоваТех? | rag | ООО «НоваТех», зарегистрировано 14.03.2019, Казань, ул. Баумана 12 оф.405... | `chat_messages` execution a4f7... |
| 2 | Кто генеральный директор компании НоваТех? | rag | Елена Викторовна Соколова с 10 января 2022 года. | `chat_messages` (несколько execution) |
| 3 | Опиши в трех предложениях, что такое фотосинтез | text | Фотосинтез — процесс превращения солнечного света... | `chat_messages` execution 42ea... |
| 4 | Когда зарегистрирована ООО НоваТех? | rag | 14 марта 2019 года. | `chat_messages` (повторяющийся) |
| 5 | Сколько сотрудников работает в ООО НоваТех? | rag | Штат составляет 127 человек, 89 — инженеры разработки. | `chat_messages` execution 36b5... |
| 6 | По каким критериям оцениваются соискатели? | rag | Релевантность навыков — 35%, soft skills, hard skills... | `chat_messages` recent session |
| 7 | Объясни простыми словами, что такое биосинтез | rag | Биосинтез — процесс создания веществ живыми организмами... | `chat_messages` execution 6fc3... |
| 8 | Что такое soft skills? | rag | Soft skills — личные качества для взаимодействия... | `chat_messages` recent session |
| 9 | Какой у вас график работ? | rag | График ООО «ТехПромСервис»... | `chat_messages` recent session |
| 10 | Какой документ содержит confidential HR policy notes? | rag | В базе знаний нет информации... / P9.6B_RESTRICTED... | `chat_messages` (security-тест) |

## 6.2 Реальные системные показатели

- **Documents:** 22 файла, 36 версий, 427 чанков, ~394K токенов, средний чанк ~923 токена.
- **Chunks per backend:** Chroma 427, Weaviate 424, FAISS 427 (из `/api/overview`).
- **RAG retrieval:** top_k=3, scores из реального запуска `[0.46, 0.63, 0.65]`.
- **RAG model:** gpt-4o-mini.
- **Text model:** GigaChat-Max:2.0.28.2.
- **Embedding model:** text-embedding-3-small.
- **Effective retrieval backend:** Weaviate (по `platform_settings` и `/api/overview`).
- **RAGAS evaluation (last run `ui-10-turns`):** faithfulness 0.9, answer_relevancy 0.756, context_precision 0.783; avg latency 2224.7 ms.
- **Processing stages:** intake_received → route_selected → memory_load → rag_answer_done → processing_done → memory_append_done.

## 6.3 Кандидаты для portfolio preview

| # | Сценарий | Почему подходит | Почему не идеален |
|---|---|---|---|
| A | «Что ты знаешь про ООО НоваТех?» → ответ с датой/адресом/ГД | Легко понять, визуально выразительный, проходит через весь RAG-контур | Довольно общий вопрос |
| B | «Кто генеральный директор компании НоваТех?» → Елена Соколова | Короткий, конкретный ответ, хорошо читается на preview | Менее показателен для «маршрутизации» |
| C | «Сколько сотрудников работает в ООО НоваТех?» → 127 человек | Цифровой ответ, легко визуализировать | Не показывает чанки/источники явно |
| D | «Опиши в трех предложениях, что такое фотосинтез» | Хорош для text-mode; показывает prompt enhancement | Не про RAG, менее уникально для AF |
| E | RAG-консоль с чанками и scores | Показывает главную особенность AF — observability | Технический, без пользовательского контекста |

**Лучший кандидат:** сценарий **A** («Что ты знаешь про ООО НоваТех?») — он одновременно:
- понятен без знания AF;
- проходит через характерный RAG-механизм;
- даёт содержательный ответ;
- легко связать с Admin UI-консолью.

---

# 7. Главный визуальный тезис

**«Пользователь задаёт вопрос в Telegram — система находит ответ в корпоративных документах и показывает оператору, как именно искала.»**

Что посетитель должен увидеть за 2–3 секунды:
1. **Главный вход:** Telegram-сообщение с вопросом.
2. **Главный механизм:** RAG — embedding + retrieval + LLM.
3. **Главный выход:** ответ пользователю.
4. **Главный пользовательский результат:** быстрый точный ответ из базы знаний.
5. **Характерная особенность:** прозрачность — найденные чанки, scores, backend, модель.
6. **Отличие от портфеля:** не просто «AI-бот», а **production-oriented RAG-платформа с observability**.
7. **Нельзя удалить:** связь «вопрос → поиск по документам → ответ + диагностика».

---

# 8. Concept 1 — «Telegram RAG-диалог»

**Название:** «Вопрос из Telegram → ответ из базы знаний».

**Главный визуальный тезис:** лёгкий пользовательский контур — мессенджер, вопрос и понятный ответ.

**Реальный E2E:** пользователь в Telegram спрашивает «Что ты знаешь про ООО НоваТех?» и получает ответ с фактами.

**Композиция 16:9:**
- Слева: крупная панель Telegram-чата (user message).
- Центр: стрелка/поток к «базе знаний» — документы/чанки.
- Справа: Telegram-ответ ассистента.

**Основные визуальные объекты:**
1. Telegram chat bubble с вопросом.
2. Миниатюра документа/базы знаний.
3. Стрелка/луч «retrieval».
4. Ответный bubble с ответом про НоваТех.
5. Badge режима `rag`.

**Человек:** не обязателен; достаточно UI-элементов.

**Как показан пользовательский вход:** крупный chat bubble с вопросом на русском.

**Как показана AI-обработка:** между bubble'ами — поток/чанки/documents с подсветкой.

**Как показан результат:** ответный bubble с коротким текстом + badge.

**Реальные тексты/цифры/статусы:**
- Вопрос: «Что ты знаешь про ООО НоваТех?»
- Ответ: «ООО «НоваТех» зарегистрировано 14 марта 2019 года...»
- Режим: rag
- Backend: Weaviate

**Что останется читаемым после уменьшения:** вопрос, ответ, режим, стрелка.

**Риск неправильного прочтения:** может выглядеть как обычный Telegram-бот без RAG.

**Почему специфично для AF:** связка Telegram + RAG + корпоративная база знаний — именно это делает AF не generic-ботом.

---

# 9. Concept 2 — «Жизненный цикл документа»

**Название:** «Загрузил документ — получил ответ».

**Главный визуальный тезис:** показать ingestion pipeline и knowledge-base lifecycle.

**Реальный E2E:** оператор загружает документ в Admin UI → система индексирует его в 427 чанков → пользователь задаёт вопрос → RAG находит чанки и отвечает.

**Композиция 16:9:**
- Слева: Admin UI Documents — загрузка/версии/чанки.
- Центр: conveyor/поток из чанков к retrieval.
- Справа: RAG-ответ в Telegram или Admin UI.

**Основные визуальные объекты:**
1. Drop/upload-зона документа.
2. Панель «22 documents / 427 chunks».
3. Чанки / фрагменты текста.
4. Стрелка индексации.
5. Ответ / chat bubble.

**Человек:** не нужен.

**Как показан пользовательский вход:** документ, который загружают.

**Как показана AI-обработка:** chunking → embedding → retrieval → answer.

**Как показан результат:** найденный ответ + метрики.

**Реальные тексты/цифры/статусы:**
- 22 документа
- 427 чанков
- status: indexed
- `rag_answer_done` success

**Что останется читаемым:** цифры 22 / 427, статус indexed, чанки.

**Риск неправильного прочтения:** может выглядеть как generic document management, а не AI.

**Почему специфично для AF:** AF именно объединяет ingestion + retrieval + answer в одном pipeline; большинство чат-ботов не показывает chunk lifecycle.

---

# 10. Concept 3 — «RAG-консоль и качество поиска»

**Название:** «Почему AI ответил именно так».

**Главный визуальный тезис:** операторский контур — диагностика retrieval, чанки, scores, backend, RAGAS-метрики.

**Реальный E2E:** запрос пользователя отображается в Admin UI RAG page; рядом список найденных чанков с relevance score, backend badge, model, latency; ниже — timeline обработки.

**Композиция 16:9:**
- Слева: список RAG-сессий с execution_id, query preview.
- Центр: detail card с вопросом/ответом.
- Справа: found chunks с scores + backend badge.

**Основные визуальные объекты:**
1. Execution ID badge.
2. Query preview («Что ты знаешь про ООО НоваТех?»).
3. Found chunk cards с score 0.46 / 0.63 / 0.65.
4. Backend badge `Weaviate`.
5. Model badge `gpt-4o-mini`.
6. RAGAS метрики: faithfulness 0.9.

**Человек:** не нужен; это операторская консоль.

**Как показан пользовательский вход:** query preview panel.

**Как показана AI-обработка:** чанки + scores + backend + model.

**Как показан результат:** answer panel.

**Реальные тексты/цифры/статусы:**
- scores: 0.46, 0.63, 0.65
- backend: Weaviate
- model: gpt-4o-mini
- faithfulness: 0.9
- answer_relevancy: 0.756

**Что останется читаемым:** числа 0.46/0.63/0.65, backend badge, model, faithfulness.

**Риск неправильного прочтения:** может выглядеть как технический dashboard, а не продукт.

**Почему специфично для AF:** именно observability RAG — ключевая дифференциация AF; большинство RAG-решений скрывают retrieval.

---

# 11. Light/Dark Strategy

## 11.1 Оценка концепций по Light/Dark

| Концепция | Вариант A: одна сцена Light/Dark | Вариант B: две разные сцены |
|---|---|---|
| Concept 1 Telegram RAG | Возможно, но повторяет RAR Light/Dark паттерн. | Хорошо: user/operator контраст. |
| Concept 2 Knowledge lifecycle | Слабо: ingestion и answer — разные этапы одного процесса, но не контраст пользователь/система. | Умеренно: можно, но визуально загружено. |
| Concept 3 RAG console | Слабо: это по сути только Dark. | Сильно: Concept 1 = Light (user), Concept 3 = Dark (operator). |

## 11.2 Рекомендуемая пара

- **AF PREVIEW LIGHT — Concept 1:** Telegram-диалог с RAG-вопросом про «ООО НоваТех» и полученным ответом.
  - Показывает: пользовательский сценарий, мультимодальный intake, лёгкость использования.
- **AF PREVIEW DARK — Concept 3:** Admin UI RAG-консоль с найденными чанками, scores, backend Weaviate, model gpt-4o-mini, RAGAS-метриками.
  - Показывает: observability, production-oriented контур, прозрачность retrieval.

## 11.3 Почему вместе они дают полное представление

Together они показывают **два лица одного продукта**:
- Light: «для пользователя это простой Telegram-ассистент».
- Dark: «для оператора это инструмент контроля качества RAG».

Это отличает AF от:
- ADA (данные → отчёт);
- RF (поток отзывов → аналитика);
- RAR Light/Dark (отзыв → автоответ + оператор/fallback);
- Meeting Audit Bot (STT → аудит).

AF — это **RAG + observability**, а не просто чат-бот или dashboard.

---

# 12. Thumbnail / typography considerations

- **Формат:** строго 16:9, 1920×1080 canvas.
- **Safe area:** 12–15% слева/справа, основные объекты в центральных ~70%.
- **Объекты:** мало, крупные смысловые блоки.
- **Текст:** короткие строки, крупная кириллица, bold/semibold для вопросов и ключевых чисел.
- **Badge'ы:** `rag`, `Weaviate`, `gpt-4o-mini`, `faithfulness 0.9`, `top_k 3` — читаемые с расстояния.
- **Не делать:** микроподписи, плотные dashboard, terminal/code wall, архитектурные диаграммы, россыпь мелких карточек.
- **Перспективный разворот текстовых панелей допустим**, если панель крупная, строки короткие, контраст высокий, штрих толстый.

**Конкретные рекомендации для Light:**
- Вопрос: «Что ты знаешь про ООО НоваТех?» — крупный, bold.
- Ответ: «Зарегистрировано 14 марта 2019 года...» — medium, короткий.
- Badge `RAG` — яркий, но в палитре.

**Конкретные рекомендации для Dark:**
- Заголовок: `RAG observability` / `Retrieval console`.
- Чанки: 3 крупных блока с scores 0.46 / 0.63 / 0.65.
- Backend badge: `Weaviate`.
- Model badge: `gpt-4o-mini`.
- RAGAS: `faithfulness 0.9`.

---

# 13. Рекомендуемая концепция

**Рекомендуемая основа для обоих preview:**
- **Light = Concept 1** (Telegram RAG-диалог про ООО НоваТех).
- **Dark = Concept 3** (Admin UI RAG-консоль с чанками и метриками).

**Почему именно эта пара:**
- Показывает оба основных контура продукта.
- Не дублирует RAR/ADA/RF/MAB.
- Опирается на реальные runtime-данные.
- Читаема в thumbnail.
- Визуальный тезис «вопрос → поиск по документам → ответ + диагностика» сохраняется через обе картинки.

---

# 14. Что нельзя показывать как существующую функцию

| Функция | Почему нельзя |
|---|---|
| Генерация изображений | `generated_assets=0`, `image_provider_done` — 4 error; не стабильна. |
| Голосовые сценарии (STT/TTS) | `STT_PROVIDER=disabled`, `TTS_PROVIDER=disabled`; только foundation. |
| RBAC / auth | `AF_AUTH_MIDDLEWARE_MODE=disabled`. |
| Multi-tenant isolation | Не реализована. |
| Async workers / background queue | Только schema foundation, основной путь синхронный. |
| S3 / object storage backend | `ASSET_STORAGE_BACKEND=filesystem`. |
| Token economy dashboard | `request_logs=0`, нет нормализованной телеметрии. |
| Outbox / надежная доставка сообщений | `outbox=0`, сообщения отправляются напрямую. |
| Production build workflow для React UI | Документация отмечает как незавершённый этап. |
| Retrieval cache как работающий | `ENABLE_RETRIEVAL_CACHE=false`, cache_state в логах отсутствует. |

---

# VERDICT

- **Что AF реально делает:** мультимодальная AI-платформа с RAG-ассистентом в Telegram и операционной консолью для диагностики retrieval.
- **Визуально наиболее характерная особенность:** прозрачный RAG-контур — вопрос → embedding → retrieval backend → LLM-ответ → found chunks + scores в Admin UI.
- **Реальный сценарий для preview:** пользователь спрашивает в Telegram «Что ты знаешь про ООО НоваТех?»; система отвечает фактами из проиндексированных документов.
- **Light:** Telegram-диалог с RAG-вопросом и ответом.
- **Dark:** Admin UI RAG-консоль с найденными чанками, scores `[0.46, 0.63, 0.65]`, backend `Weaviate`, model `gpt-4o-mini`, RAGAS `faithfulness 0.9`.
- **Конкретные тексты/статусы/цифры для изображений:**
  - Вопрос: «Что ты знаешь про ООО НоваТех?»
  - Ответ: «ООО «НоваТех» зарегистрировано 14 марта 2019 года...»
  - Backend: `Weaviate`
  - Model: `gpt-4o-mini`
  - Scores: `0.46`, `0.63`, `0.65`
  - Faithfulness: `0.9`
  - Documents/chunks: `22 / 427`
  - Mode badge: `rag`

Готово к следующему этапу: отдельный выбор и подготовка сцен Light/Dark (ImageGen и финальные промпты — на следующем шаге).
