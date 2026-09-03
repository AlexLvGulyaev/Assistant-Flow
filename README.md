# 🏠 Assistant Flow

Мультимодальная AI-платформа для работы с корпоративными знаниями, AI-ассистентами и эксплуатацией AI-сервисов.

RAG и операционная консоль встроены в уже существующий мультимодальный контур обработки запросов, а не заменяют его.

---

## Бизнес-сценарий и идея

Во многих компаниях знания существуют, но ими сложно пользоваться.

Регламенты лежат в PDF-файлах и папках.  
Инструкции быстро устаревают.  
Поддержка отвечает на одни и те же вопросы.  
Новые сотрудники долго разбираются во внутренних процессах.  
AI-боты часто работают как «черный ящик», когда невозможно понять, почему был получен тот или иной ответ.

Assistant Flow создается как единая AI-платформа, которая объединяет:

- AI-ассистента в Telegram;
- текстовые, голосовые, графические сценарии и OCR с фотографий;
- память диалога;
- поиск по корпоративной базе знаний (RAG);
- диагностику AI-контуров;
- контроль качества ответов;
- эксплуатационную телеметрию.

Платформа ориентирована не только на генерацию ответов, но и на полноценную эксплуатацию AI-систем:

- с диагностикой;
- трассировкой обработки запросов;
- наблюдаемостью поиска по базе знаний;
- анализом качества ответов;
- управлением индексами документов;
- поддержкой нескольких AI-провайдеров.

---

## Основные возможности платформы

### Мультимодальные сценарии

Assistant Flow изначально рассчитан на несколько типов запросов в одном Telegram-боте:

- текстовые ответы и диалог;
- RAG-запросы по корпоративной базе знаний;
- генерация изображений по описанию;
- голос: распознавание речи (STT) и озвучивание (TTS), если включено в окружении;
- **OCR / Vision** — извлечение текста с фото через OpenAI Vision.

Примеры формулировок в Telegram:

- «объясни простыми словами, что такое фотосинтез» — текстовый режим;
- «дай полную сводку по компании NovaTex» — RAG по проиндексированным документам;
- «распознай текст на изображении» — OCR (режим `/mode ocr` или подпись к фото);
- «нарисуй слона в посудной лавке» — генерация изображения в текстовом режиме.

---

### Текстовые AI-сценарии

Assistant Flow поддерживает текстовые AI-ответы через Telegram и административную консоль.

Платформа:
- определяет тип запроса;
- запускает нужный сценарий обработки;
- сохраняет историю взаимодействия;
- отображает этапы обработки;
- фиксирует задержки и техническую телеметрию.

📷 Скриншоты:

![Пример текстового ответа в Telegram](docs/screenshots/text-tg.png)

<p align="center"><em>
Пример текстового ответа Telegram-ассистента в режиме обычного диалога.
</em></p>

![Консоль текстового pipeline](docs/screenshots/text-adm.png)

<p align="center"><em>
Консоль текстового pipeline: параметры LLM-запроса, telemetry и таймлайн обработки text-response.
</em></p>

---

### Работа с базой знаний (RAG)

Платформа поддерживает полноценный контур поиска по базе знаний:

- загрузку документов;
- индексацию;
- разбиение документов на смысловые фрагменты;
- поиск релевантной информации;
- настройку параметров поиска;
- анализ найденных чанков;
- диагностику поиска;
- выбор backend векторного поиска (Chroma / FAISS / Weaviate).

Через административную консоль можно наблюдать RAG-сессии, анализировать чанки, настраивать поиск и переключать backend векторного хранилища.

📷 Скриншоты:

![RAG-ответ в Telegram](docs/screenshots/rag-tg.png)

<p align="center"><em>
RAG-ответ Telegram-ассистента на основе корпоративной базы знаний Assistant Flow.
</em></p>

![Операционная консоль RAG-сессий](docs/screenshots/rag-adm.png)

<p align="center"><em>
Операционная консоль RAG-сессий с диагностикой retrieval, latency, cache-state и найденных чанков.
</em></p>

![Расширенная диагностика retrieval](docs/screenshots/retrieval-details-adm.png)

<p align="center"><em>
Расширенная диагностика retrieval: найденные чанки, relevance-score, latency retrieval и состояние retrieval cache.
</em></p>

![Управление документами knowledge base](docs/screenshots/documents-adm.png)

<p align="center"><em>
Управление документами knowledge base: индексация, preprocessing, версии документов, жизненный цикл ingestion pipeline и фоновые задачи reindex (воркер потребляет очередь <code>async_jobs</code> внутри admin-api).
</em></p>

![Панель Retrieval Settings](docs/screenshots/rs-adm.png)

<p align="center"><em>
Панель управления retrieval backend: переключение vector storage, runtime tuning, chunking и cache-настройки RAG.
</em></p>

---

### Кэширование запросов к базе знаний

Повторяемые RAG-запросы можно ускорять кэшем результатов поиска. В консоли видны состояния OFF / MISS / HIT и задержки поиска. Включение и TTL — в **Retrieval Settings** или через `.env` (подробности — `docs/architecture/cache_layer_design.md`).

📷 Скриншот:

![Сравнение retrieval cache MISS и HIT](docs/screenshots/cache-hit-adm.png)

<p align="center"><em>
Сравнение retrieval cache MISS и HIT: снижение latency retrieval при повторном запросе.
</em></p>

---

### Память диалога

Платформа запоминает контекст разговора с пользователем: можно продолжить диалог без повторения вводных. История хранится в PostgreSQL (при настроенной БД); размер контекста, передаваемого модели, ограничивается, чтобы ответы оставались устойчивыми и предсказуемыми.

Оператор в административной консоли (**Memory**, `/memory`) видит сессии, реплики и диагностику того, как память повлияла на ответ.

📷 Скриншот:

![Диагностика runtime memory](docs/screenshots/mem-adm.png)

<p align="center"><em>
Диагностика runtime memory: контекст диалога, trimming history и политика ограничения conversational memory.
</em></p>

---

### Голосовые сценарии

Платформа поддерживает:

- распознавание речи (STT);
- синтез речи (TTS);
- голосовые ответы;
- диагностику аудио-сценариев;
- телеметрию голосовых AI-контуров.

📷 Скриншоты:

![Голосовое взаимодействие в Telegram](docs/screenshots/audio-tg.png)

<p align="center"><em>
Пример голосового взаимодействия с Telegram-ассистентом: распознавание речи и генерация аудио-ответа.
</em></p>

![Консоль voice pipeline](docs/screenshots/audio-adm.png)

<p align="center"><em>
Операционная консоль voice pipeline: STT/TTS telemetry, аудио-сессия и таймлайн обработки голосового запроса.
</em></p>

---

### Генерация изображений

Assistant Flow поддерживает генерацию изображений по текстовому описанию.

Платформа:
- обрабатывает пользовательский запрос;
- уточняет описание для генерации;
- запускает контур генерации изображений;
- сохраняет сохранённые ассеты;
- отображает этапы обработки в административной консоли.

📷 Скриншоты:

![Генерация изображения в Telegram](docs/screenshots/image-tg.png)

<p align="center"><em>
Пример генерации изображения Telegram-ассистентом по текстовому запросу пользователя.
</em></p>

![Консоль генерации изображений](docs/screenshots/image-adm.png)

<p align="center"><em>
Консоль генерации изображений: refined prompt, telemetry image pipeline и сохранённый generated asset.
</em></p>

---

### Распознавание текста (OCR)

Распознавание выполняется через **OpenAI Vision** (без локальных OCR-библиотек). Нужны `OPENAI_API_KEY` и vision-capable модель из `.env`.

**Как запустить:**

- режим **`/mode ocr`** — отправьте фото (подпись необязательна);
- в режимах **`text`** или **`rag`** — фото с подписью, где явно просят прочитать текст, например: «распознай текст», «OCR», «извлеки текст», «прочитай изображение».

Ответ приходит одним сообщением с распознанным текстом. В режиме OCR подпись может уточнить задание для vision-модели (например «объясни простыми словами, что написано») — это один вызов Vision, без отдельного текстового ассистента после OCR.

**Ограничения:** качество зависит от снимка; хуже распознаются размытые кадры, рукопись, мелкий шрифт и сложные таблицы. RAG по содержимому изображения без OCR отдельно не запускается.

📷 Скриншоты:

![OCR в Telegram](docs/screenshots/ocr_tg.png)

<p align="center"><em>
Пример OCR-обработки изображения в Telegram: распознавание текста средствами OpenAI Vision.
</em></p>

![OCR / Vision pipeline в консоли](docs/screenshots/ocr_adm.png)

<p align="center"><em>
OCR/Vision pipeline: распознавание изображения, telemetry обработки и извлечённый текст документа.
</em></p>

Подробнее — [USER_GUIDE.md](USER_GUIDE.md).

---

## Операционная консоль

Административная консоль предназначена для эксплуатации и наблюдаемости AI-платформы.

Консоль позволяет:

- контролировать состояние платформы;
- анализировать AI-сессии;
- наблюдать этапы обработки запросов;
- анализировать этапы поиска по базе знаний;
- управлять индексацией документов;
- наблюдать память диалога;
- анализировать качество RAG;
- отслеживать техническую телеметрию AI-контуров.

Основной UI: `frontend/admin-ui` (React). Пункты бокового меню (как в коде):

| Раздел | Путь |
|--------|------|
| Обзор | `/` |
| Сводка | `/summary` |
| Текст | `/text` |
| RAG | `/rag` |
| Изображения | `/images` |
| Аудио | `/audio` |
| Документы | `/documents` |
| Retrieval Settings | `/retrieval` |
| Логи | `/logs` |
| Memory | `/memory` |
| Анализ RAG | `/evaluation` |
| Аудит | `/audit` |

Доступ к консоли: при заданных `AF_ADMIN_TOKEN` / `AF_ADMIN_DEMO_TOKEN` вход по Bearer-токену (экран `/login`), есть демо-вход read-only; без токенов консоль открыта (локальный режим). Журнал `/audit` фиксирует обращения к Admin API.

📷 Скриншоты:

![Обзор состояния платформы](docs/screenshots/overview-adm.png)

<p align="center"><em>
Обзор состояния платформы Assistant Flow: health-check сервисов, активные AI-провайдеры, retrieval backend и операционные метрики.
</em></p>

![Сводная операционная статистика](docs/screenshots/summary-adm.png)

<p align="center"><em>
Сводная операционная статистика платформы: маршруты обработки, этапы pipeline, телеметрия провайдеров и агрегированные метрики.
</em></p>

![Журнал execution-сессий](docs/screenshots/logs-adm.png)

<p align="center"><em>
Журнал execution-сессий и трассировка pipeline обработки запросов Assistant Flow.
</em></p>

---

## Анализ качества RAG

В платформу встроен отдельный контур оценки качества RAG и AI-ответов.

Поддерживаются:
- RAGAS;
- ручная оценка ответов;
- анализ точности поиска;
- анализ найденных чанков;
- оценка faithfulness;
- оценка relevance.

Это позволяет не только запускать RAG, но и контролировать качество работы поиска по базе знаний.

📷 Скриншоты:

![Консоль оценки качества RAG](docs/screenshots/ragas-adm.png)

<p align="center"><em>
Консоль оценки качества RAG: RAGAS-метрики, ручная валидация ответов и анализ retrieved chunks.
</em></p>

![Сравнение сессий в evaluation run](docs/screenshots/evaluation-run-adm.png)

<p align="center"><em>
Сравнение отдельных RAG-сессий внутри evaluation run с отображением метрик quality evaluation.
</em></p>

---

## Типовой сценарий работы

1. Оператор загружает документы в административную консоль.
2. Платформа индексирует базу знаний.
3. Пользователь задаёт вопрос в Telegram.
4. Система выполняет поиск по базе знаний и формирует ответ.
5. Оператор просматривает диагностику запроса в консоли (RAG, логи, задержки).

---

## Архитектура платформы

Assistant Flow состоит из нескольких связанных контуров. Ниже — схема верхнего уровня (без деталей реализации).

```mermaid
flowchart TD
    TG[Telegram] --> BOT[Telegram-бот]
    UI[Admin UI] --> API[Admin API]

    BOT --> ORCH[Оркестратор запросов]
    API --> ORCH

    ORCH --> TEXT[Текстовый контур]
    ORCH --> RAG[RAG]
    ORCH --> OCR[OCR]
    ORCH --> VOICE[Voice STT/TTS]
    ORCH --> IMG[Генерация изображений]
    ORCH --> MEM[Memory]

    TEXT --> PROV[AI providers<br/>OpenAI · GigaChat · Proxy API]
    RAG --> PROV
    OCR --> PROV
    VOICE --> PROV
    IMG --> PROV

    RAG --> CACHE[Retrieval Cache]
    CACHE --> RET[Retrieval backends<br/>Chroma · FAISS · Weaviate]
    RAG --> PG[(PostgreSQL<br/>metadata · sessions · logs)]

    MEM --> PG
    API --> PG

    STOR[Asset / Storage<br/>assets · documents · outputs]
    IMG --> STOR
    OCR --> STOR
    API --> STOR

    ORCH --> OBS[Логи и телеметрия]
    API --> OBS
```

### Пользовательский контур

Поддерживает:
- Telegram-интерфейс;
- текстовые сценарии;
- голосовые сценарии;
- генерацию изображений;
- RAG-запросы.

---

### Контур обработки запросов

Маршрутизация по типу запроса, контуры обработки AI, память диалога, логирование и диагностика этапов.

---

### Контур базы знаний

Загрузка документов, индексация, метаданные чанков, настройка поиска и опциональный кэш повторных запросов.

---

### Контур наблюдаемости

Поддерживаются:
- трассировка AI-сессий;
- техническое логирование;
- диагностика контуров обработки AI;
- анализ задержек;
- контроль состояния сервисов;
- эксплуатационная телеметрия.

---

## Технологический стек

### Backend

- Python
- FastAPI
- PostgreSQL
- ChromaDB
- Weaviate
- FAISS

---

### Frontend

- React
- Vite

---

### AI-провайдеры

- OpenAI
- GigaChat
- Proxy API

---

### Инфраструктура

- Docker
- Docker Compose (`docker-compose.portfolio.yml`)

---

## Структура проекта

```text
assistant-flow/
├── admin_api/              # FastAPI Admin API
├── core/                   # оркестрация запросов
├── providers/              # клиенты AI-провайдеров, embeddings
├── services/               # RAG, поиск, кэш, evaluation, индексация
├── interfaces/             # Telegram-бот (run_telegram_bot.py)
├── repositories/           # PostgreSQL
├── database/               # schema.sql, миграции
├── frontend/
│   └── admin-ui/           # React операционная консоль (Vite)
├── docs/                   # архитектура, OPERATIONS, screenshots/
├── evaluation/             # датасеты и контур оценки качества
├── scripts/                # smoke, индексация, утилиты
├── storage/                # FAISS, SQLite cache, assets (volume в compose)
├── utils/                  # AppConfig, общие утилиты
├── docker-compose.portfolio.yml
├── .env.example
├── RUNBOOK.md
├── USER_GUIDE.md
├── PROJECT_STATE.md
└── README.md
```


---

## Развертывание

Каноническая команда для локального демо и GitHub (имя compose-проекта берётся из имени каталога, по умолчанию `assistant-flow`):

```bash
cp .env.example .env
COMPOSE_BAKE=false docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

Поднимаются сервисы: `postgres`, `chroma`, `weaviate`, `assistant-flow` (Telegram), `admin-api`, `admin-ui`.

Порты на хосте (по умолчанию):

| Сервис | Порт |
|--------|------|
| Admin UI | 8080 |
| Admin API | 8600 |
| PostgreSQL | 5433 → 5432 в сети compose |
| Chroma HTTP | 8001 → 8000 |
| Weaviate HTTP | 8089 → 8080 |

Volumes: `./data/documents`, `./storage`, `./outputs` → контейнеры `assistant-flow` и `admin-api`. Данные PostgreSQL и векторных хранилищ живут в named volumes вида `assistant-flow_portfolio_*`.

Backend-образы собираются multi-stage: сборочные зависимости остаются в builder-стадии, runtime содержит только venv + ffmpeg. Опциональные extras включаются build-args (`INSTALL_RAGAS`, `INSTALL_DASHBOARD`) — см. RUNBOOK §E.

Проверка после запуска:

```bash
curl -sS http://localhost:8600/api/health
# браузер: http://localhost:8080 (UI), API: http://localhost:8600
```

Подробные эксплуатационные процедуры, SSH-туннель и типовые сбои — в [RUNBOOK.md](RUNBOOK.md).

---

## Конфигурация (.env)

`cp .env.example .env` — только плейсхолдеры в git; секреты не коммитить.

| Группа | Ключевые переменные |
|--------|---------------------|
| Telegram | `TELEGRAM_BOT_TOKEN` (реальный токен, не заглушка) |
| Текст / RAG | `GIGACHAT_*`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, `PROXY_*` |
| PostgreSQL | `DATABASE_URL` → `postgresql://assistant:assistant@postgres:5432/assistant_flow` (portfolio) |
| Поиск / кэш | `RAG_BACKEND`, `CHROMA_*`, `FAISS_INDEX_DIR`, `WEAVIATE_*`, `RAG_DOCUMENTS_DIR`, `ENABLE_RETRIEVAL_CACHE` |
| Аудио | `AUDIO_ENABLED`, `STT_PROVIDER`, `TTS_PROVIDER` (по умолчанию `disabled`), `AUDIO_TIMEOUT_SECONDS` (default 60), `AUDIO_MAX_RETRIES` (default 1), `STT_COST_PER_MINUTE_USD` (default 0.006), `TTS_COST_PER_1M_CHARS_USD` (default 15.0) — таймауты/ретраи OpenAI-клиентов STT/TTS и оценочная стоимость (cost_basis=estimated) |
| Доступ к консоли | `AF_ADMIN_TOKEN` (полный доступ), `AF_ADMIN_DEMO_TOKEN` (демо read-only, запечён в UI при сборке), `AF_AUTH_MIDDLEWARE_MODE` (legacy Basic-аутентификация) |
| Лимиты | `ADMIN_UPLOAD_MAX_MB` (лимит размера документа, default 25) |
| Фоновый воркер | `AF_ASYNC_WORKER_ENABLED` (default on), `AF_ASYNC_WORKER_POLL_SECONDS` (default 5), `AF_ASYNC_WORKER_STALE_RUNNING_SECONDS` (default 1800) |
| Admin UI | `ADMIN_API_CORS_ORIGINS` → `http://localhost:8080` |

Полный перечень — `.env.example`, [docs/OPERATIONS.md](docs/OPERATIONS.md).

---

## Текущий статус проекта

### Стабильные подсистемы

- текстовый AI-контур;
- RAG-контур (Chroma / FAISS / Weaviate, backend переключается в Retrieval Settings);
- индексация документов с heavy-RAG safeguard-ами (лимит размера upload, защита reindex);
- диагностика поиска по базе знаний и полный текст чанка в консоли;
- кэширование запросов к базе знаний;
- техническое логирование и трассировка pipeline;
- механизм памяти диалога;
- авторизация консоли (Bearer-токен, демо-вход read-only) и журнал аудита обращений к Admin API;
- операционная наблюдаемость;
- multi-stage production-образы (без сборочных зависимостей и dev-пакетов в runtime).

---

### Активно развиваются

- React Admin UI;
- оценка качества RAG (RAGAS, `ENABLE_RAGAS_EVALUATION`);
- аудио-контур (STT/TTS) — остаток по P5.4;
- фильтрация поиска по источникам.

---

## Roadmap

- Завершение аудио-контура (P5.4 remainder).
- Фильтрация поиска по источникам.
- Резервная маршрутизация провайдеров (OpenAI / GigaChat / Proxy API).
- Улучшение разбиения документов на чанки.

---

## Документация проекта

| Документ | Назначение |
|---|---|
| [README.md](README.md) | Общее описание платформы (входная точка GitHub) |
| [RUNBOOK.md](RUNBOOK.md) | Развёртывание, smoke-проверки, эксплуатация и диагностика |
| [USER_GUIDE.md](USER_GUIDE.md) | Руководство пользователя и оператора |
| [docs/SPEC.md](docs/SPEC.md) | Продуктовая спецификация |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Технический план реализации |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура системы |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Compose, env, процедуры развёртывания |
| [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md) | Модель безопасности и авторизация |
| [docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md) | Демо-чеклист |
| [database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md) | PostgreSQL: схема и миграции |
| [docs/architecture/](docs/architecture/) | Детальные проектные документы (кэш, оценка, UI contract) |

---

## Важное замечание

Assistant Flow является инженерным AI-проектом и исследовательской платформой для:

- RAG;
- мультимодальных AI-сценариев;
- эксплуатации AI-систем;
- наблюдаемости AI-контуров;
- диагностики поиска по базе знаний;
- проектирования мультимодальных AI-систем.

Проект активно развивается и используется как практический полигон для разработки и сопровождения AI-сервисов.
