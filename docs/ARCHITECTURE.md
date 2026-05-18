# Архитектура Assistant Flow

Документ дополняет [README.md](../README.md): границы компонентов, потоки данных и модели развёртывания. Рантайм — `core/`, `services/`, `providers/`, `interfaces/`, `repositories/`, `admin_api/`, `frontend/admin-ui/`.

Платформа изначально **мультимодальная** (текст, голос, изображения в Telegram); полноценный **RAG**-контур и операционная React-консоль развивались как следующий этап.

---

## Схема верхнего уровня

```text
 +-------------------+       +----------------------+
 |     Telegram      |       |  Admin UI (React)    |
 +---------+---------+       +----------+-----------+
           |                            |
           v                            v
 +---------+---------+       +----------+-----------+
 |  Telegram-бот     |       |  Admin API (FastAPI) |
 +---------+---------+       +----------+-----------+
           \                            /
            v                          v
          +--------------------------------+
          |   Оркестратор запросов       |
          +----------------+-------------+
                           |
     +-------+-------+-----+-----+-------+
     v       v       v           v       v
 [Текст] [Аудио] [Изобр.] [RAG/поиск] [Память]
     |       |       |           |       |
     +-------+-------+-----------+-------+
                         |
                         v
              [ OpenAI / GigaChat / Proxy API ]
                         |
         +---------------+---------------+
         v               v               v
   [Chroma/FAISS/   [PostgreSQL]   [Логи, телеметрия,
    Weaviate]                        Evaluation/RAGAS]
```

---

## Общая идея

Система разделена на **пользовательский** и **операционный** контуры.

| Контур | Назначение |
|--------|------------|
| **Telegram** | Единственный канал для конечного пользователя: диалог, режимы, RAG без загрузки корпуса в чат |
| **Admin UI + Admin API** | Обзор здоровья, документы, RAG-диагностика, Memory, Audio, Images, Evaluation — панель оператора |
| **PostgreSQL** | Документы, версии, метаданные чанков, `processing_logs`, память сессий (не векторы) |
| **Векторные backend** | Chroma / FAISS / Weaviate — эмбеддинги и поиск; синхронизация с Postgres при индексации |
| **Кэш поиска** | SQLite (`storage/cache/`) — ускорение повторных RAG-запросов, наблюдаемость OFF/MISS/HIT |
| **Индексация** | Отделена от пользовательского чата: Admin UI, CLI `scripts/admin_index_documents.py` |

---

## Основные компоненты

### Telegram bot

- `interfaces/telegram_bot.py` — long polling (**pyTelegramBotAPI**).
- Режимы `text` / `rag` — `utils/telegram_user_state.py`; память диалога — PostgreSQL (`chat_sessions`, `chat_messages`) при настроенном `DATABASE_URL`.
- Плейсхолдер токена (portfolio): polling не стартует, контейнер ждёт реальный токен.

### Orchestrator

- `core/orchestrator.py` — **PromptOrchestrator**: текст, изображения, маршрутизация к провайдерам.
- `RequestLogger` (**SQLite** `logs.db`) на части путей.

### RAG и retrieval

- `services/rag_query_service.py` — поиск + ответ LLM, диагностика чанков (`services/rag_types.py`).
- Абстракция backend: Chroma, FAISS, Weaviate через фабрику retrieval (`services/retrieval/`).
- `services/admin_knowledge_indexer.py` + `scripts/admin_index_documents.py` — индексация корпуса.
- `services/cache/caching_retrieval_backend.py` — обёртка кэша с live-настройкой из БД.

### FastAPI Admin API

- `admin_api/`, `run_admin_api.py` (порт **8600**).
- `/api`: `health`, `overview`, `summary`, `logs`, `documents`, `assets`, retrieval settings, evaluation и др.
- Аутентификация на уровне приложения **не** реализована — [SECURITY_NOTES.md](SECURITY_NOTES.md).

### React Admin UI

- `frontend/admin-ui/` — **Vite** + **React**.
- Разделы: Обзор, Сводка, Текст, RAG, Изображения, Аудио, Документы, Retrieval Settings, Логи, Memory, Анализ RAG.
- `VITE_ADMIN_API_BASE_URL` при сборке образа.

### PostgreSQL

- `database/schema.sql`, контракт: `database/db_contract.md`.
- Доступ: `repositories/`, сервисы lifecycle.

### Провайдеры

- `providers/` — GigaChat, OpenAI-совместимый чат, эмбеддинги, изображения, STT/TTS (`disabled` по умолчанию).

### Evaluation

- RAGAS и ручная оценка — Admin UI **Анализ RAG**, опционально `ENABLE_RAGAS_EVALUATION`.
- Дизайн: `docs/architecture/evaluation_layer_design.md`.

### Asset storage

- `services/asset_repository_factory.py` — превью изображений/аудио через Admin API.

---

## Потоки обработки

### Text

Telegram → оркестратор → GigaChat (и связанные сервисы) → ответ; lifecycle в `processing_logs` при Postgres.

### RAG

Режим `rag`: **read-only** поиск по векторному backend → контекст → LLM с источниками → диагностика в Telegram и Admin UI.

### Image / Audio

Изображения: оркестратор → image-провайдер → ассет в чат.  
Аудио: STT → текстовый/RAG-путь; TTS при включении.

### Document indexing

Оператор: Admin UI **Документы** или CLI → чанки → векторный backend + Postgres (`documents`, `document_versions`, `document_chunks`, события). Telegram этот путь не использует.

---

## Наблюдаемость

- **processing_logs** (PostgreSQL) — стадии, `execution_id`, JSON-детали для консоли.
- **logs.db** (SQLite) — технические записи провайдеров; не смешивать со схемой Postgres без явной связи.
- **GET /api/health** — postgres, chroma, rag, LLM; статус `degraded` при частичных сбоях.

Страницы: Overview, Summary, Logs; модальные экраны по модальностям.

---

## Развёртывание

### Portfolio (канонический GitHub/demo)

`docker-compose.portfolio.yml` — автономная сеть, postgres + chroma + weaviate + bot + admin-api + admin-ui.  
Команда и порты: [OPERATIONS.md](OPERATIONS.md), [RUNBOOK.md](../RUNBOOK.md).

### Server (продвинутый)

`docker-compose.assistant.yml` — внешние сети, Traefik, `.env.server`. Не основной путь для клона репозитория.  
Исторический Streamlit (`admin_ui/`) в server-compose **не** заменяет React Admin UI.

---

## Ограничения

- Прототип / single-tenant; без RBAC на Admin API.
- Потеря тома Chroma/Weaviate = переиндексация.
- Фильтрация поиска по источникам — задел `retrieval_security`, не основной путь Telegram по умолчанию.

Риски: [SECURITY_NOTES.md](SECURITY_NOTES.md). Операции: [OPERATIONS.md](OPERATIONS.md).
