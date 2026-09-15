# ⚙️ OPERATIONS.md — Assistant Flow

**Статус:** актуально на 2026-09-15.

Справочник эксплуатации portfolio-стека: топология, compose, PostgreSQL,
vector backends, кэш, логи, диагностика, типовые проблемы.

**Роли документов:**

| Документ | Назначение |
|----------|------------|
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Развёртывание с нуля (SOT воспроизводимости) |
| **OPERATIONS.md** (этот файл) | Эксплуатация запущенного стека: compose, порты, backends, диагностика |
| [USER_GUIDE.md](USER_GUIDE.md) | Как пользоваться ботом и консолью |
| [SECURITY_NOTES.md](SECURITY_NOTES.md) | Доступ, RBAC, аудит |

---

## Runtime contract

Изменения в репозитории сопровождаются обновлением документации:

| Что изменилось | Документ |
|----------------|----------|
| Запуск, порты, env, миграции | **DEPLOYMENT_GUIDE.md**, OPERATIONS.md |
| Поведение для пользователя | USER_GUIDE.md |
| Компоненты и потоки | ARCHITECTURE.md |
| SQL вне Docker | database/POSTGRES_SETUP.md |
| Доступ/роли/аудит | SECURITY_NOTES.md |

---

## Operational topology (portfolio)

```mermaid
flowchart TD
    DEV[Браузер / curl на хосте] --> UI[Admin UI :8080]
    DEV --> API[Admin API :8600]
    TG[Пользователь Telegram] --> BOT[assistant-flow]

    subgraph COMPOSE["assistant-flow compose"]
        UI
        API
        BOT
        PG[(PostgreSQL<br/>:5433 host → :5432 internal)]
        CH[Chroma<br/>:8001 → :8000]
        WV[Weaviate<br/>:8089 → :8080]
        ST[bind: storage / data / outputs]
    end

    API --> PG
    API --> CH
    API --> WV
    BOT --> PG
    BOT --> CH
    BOT --> WV
    API --> ST
    BOT --> ST
```

| Доступ | Адрес | Примечание |
|--------|--------|------------|
| **Публично (subdomain)** | `https://af-admin.alex-n8n.site` | traefik → `admin-ui` (сеть `n8n_default`); `/api/*` nginx контейнера проксирует в `admin-api:8600` — тот же origin |
| С **хоста** (браузер, `curl`, `psql`) | `localhost:8080`, `:8600`, `:5433`, `:8001`, `:8089` | порты из `docker-compose.portfolio.yml` |
| **Внутри** compose-сети | `postgres:5432`, `chroma:8000`, `weaviate:8080` | так задано в `.env` для контейнеров |
| Telegram | интернет → контейнер `assistant-flow` | порт наружу не публикуется |

Субдомен: роутер `assistant-flow-admin` в `/opt/n8n/dynamic.yml` (файл-провайдер
traefik без watch — после правки нужен `docker restart n8n-traefik-1`); бандл UI
собирается с пустым `VITE_ADMIN_API_BASE_URL` (относительные `/api`), поэтому
запросы same-origin и `ADMIN_API_CORS_ORIGINS` для него не требуются.

Сеть `n8n_default` — внешняя; её создание описано в DEPLOYMENT_GUIDE §3.

Авторизация консоли — Bearer-токены `AF_ADMIN_TOKEN` (admin) / `AF_ADMIN_DEMO_TOKEN`
(demo, read-only); полная модель доступа — [SECURITY_NOTES.md](SECURITY_NOTES.md) §2.

### SSH tunnel (удалённый сервер)

```bash
ssh -N \
  -L 8080:127.0.0.1:8080 \
  -L 8600:127.0.0.1:8600 \
  -L 8001:127.0.0.1:8001 \
  -L 5433:127.0.0.1:5433 \
  user@your-server
```

Порты сервера доступны на вашем `localhost`; проверка — `curl http://localhost:8600/api/health`.

---

## Compose portfolio

| Параметр | Значение |
|----------|----------|
| Файл | `docker-compose.portfolio.yml` |
| Project | из имени каталога (по умолчанию `assistant-flow`), флаг `-p` не используется |
| Запуск/остановка | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) §5, §9 |

⚠️ Не запускать второй `docker compose up` с этим файлом из каталога с другим
именем на той же машине — получите отдельный стек с пустыми volumes.

### Сервисы и порты (хост)

| Сервис | Контейнер (пример) | Порт хоста |
|--------|-------------------|------------|
| `postgres` | `assistant-flow-postgres-1` | **5433** → 5432 |
| `chroma` | `assistant-flow-chroma-1` | **8001** → 8000 |
| `weaviate` | `assistant-flow-weaviate-1` | **8089** → 8080 |
| `admin-api` | `assistant-flow-admin-api-1` | **8600** |
| `admin-ui` | `assistant-flow-admin-ui-1` | **8080** |
| `assistant-flow` | `assistant-flow-assistant-flow-1` | — |

Bind-mounts: `./data/documents`, `./storage`, `./outputs`.

### Admin UI build (same-origin)

Бандл admin-ui собирается с пустым `VITE_ADMIN_API_BASE_URL` — UI ходит по
относительным `/api`, nginx контейнера проксирует их в `admin-api`. Прямой
доступ браузера к `:8600` (не через admin-ui) потребует build-arg с полным URL
и `ADMIN_API_CORS_ORIGINS`. Демо-токен запекается через `VITE_OPS_DEMO_TOKEN`
(см. SECURITY_NOTES §2).

### Сборка образов (multi-stage)

Backend-образ (`Dockerfile`) — два этапа: build-зависимости остаются в
builder-стадии; runtime содержит только venv + ffmpeg + curl. Опциональные
extras через build-args: `INSTALL_RAGAS=true` (в portfolio compose включён для
`admin-api`).

---

## PostgreSQL (справочник)

**Развёртывание и проверка:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) §5–6.
**SQL, роли, цепочка миграций:** [database/POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md).

| Initdb (новый volume) | Файл |
|----------------------|------|
| `01_schema.sql` | `database/schema.sql` (snapshot целевой схемы, вкл. объекты 005–008) |
| `02_async_jobs.sql` | `database/migrations/004_async_jobs_foundation.sql` |

Файлы 005–008 в initdb не входят: на свежей БД их объекты уже в `schema.sql`;
сами файлы — для апгрейда **старых** volume ([POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md) §2b).

```bash
# проверка с хоста
psql "postgresql://assistant:assistant@localhost:5433/assistant_flow" -c '\dt' | head -15
```

Пересоздать БД с нуля: `docker compose -f docker-compose.portfolio.yml down` →
`docker volume rm assistant-flow_portfolio_pg_data` → запуск снова (**потеря данных**).

---

## Vector backends

| Backend | Хранение | Env |
|---------|----------|-----|
| **Chroma** | volume `assistant-flow_portfolio_chroma_data` | `CHROMA_USE_HTTP=true`, `CHROMA_HOST=chroma`, `CHROMA_PORT=8000` |
| **Weaviate** | volume `assistant-flow_portfolio_weaviate_data` | `RAG_BACKEND=weaviate`, `WEAVIATE_HOST=weaviate` |
| **FAISS** | `storage/faiss` (bind) | `RAG_BACKEND=faiss`, `FAISS_INDEX_DIR` |

Удаление volume Chroma/Weaviate = полная переиндексация из `data/documents/`.

Активный backend живёт в Postgres (`platform_settings.active_rag_backend`,
переключение — Admin UI **Retrieval Settings**) и может отличаться от
`RAG_BACKEND` в `.env` — проверять через `/retrieval`, а не только по env.

---

## Retrieval cache

- SQLite: `storage/cache/assistant_cache.sqlite3` (`CACHE_DB_PATH`).
- Включение: `ENABLE_RETRIEVAL_CACHE` или Retrieval Settings (override в БД);
  сброс поколения — `RAG_RETRIEVAL_GENERATION` после reindex/смены корпуса.
- UI: OFF / MISS / HIT в RAG-консоли; fingerprint кэша учитывает роль/visibility
  ([SECURITY_NOTES.md](SECURITY_NOTES.md) §5).

### Полный текст чанка

Операционные логи RAG-сессий хранят только preview чанка (96 символов). Полный
текст живёт в vector store и доступен:

- **UI**: карточка чанка → «показать полный текст» — модалка запрашивает полный
  текст с сервера; при недоступности показывается текст из логов с пояснением.
- **API**: `GET /api/retrieval/chunk-fulltext?source=<file>&text_fp=<fp>&chunk_index=<n>`
  (право `retrieval:read`). Совпадение по порядку: `text_fp` (fingerprint
  текста) → `chunk_index` → единственный кандидат.

Если документ удалён из индекса (переиндексация), полный текст недоступен.

---

## Asset / Storage

- `services/asset_repository_factory.py` — абстракция хранения.
- Каталоги: `storage/assets`, `data/documents`, `outputs` (compose volumes).
- Admin API: upload документов, preview изображений/аудио.

---

## Логи и диагностика

```bash
docker compose -f docker-compose.portfolio.yml logs -f admin-api
docker compose -f docker-compose.portfolio.yml logs -f assistant-flow
```

| Слой | Где |
|------|-----|
| Продуктовый lifecycle | PostgreSQL `processing_logs`, `intake_events` |
| Технический провайдер | SQLite `logs.db` (часть оркестратора/изображений) |

Admin UI: **Overview**, **Summary**, **Logs**.

Токен-экономика: панель **Сводка → Токен-экономика (точное окно)** — SQL-агрегация
`processing_logs` за период (`/api/summary` → `token_economy`): гранд-тотал,
разбивка по этапам (`by_stage`) и моделям (`by_model`). Точные суммы по полному
окну, в отличие от блока «Телеметрия провайдеров» (хвостовая выборка).
Покрытие: `rag_answer_done`, `text_answer_done`, OCR, image-refinement, STT/TTS.
Embeddings (`text-embedding-3-small`) на уровне API-usage не захватываются —
LangChain `OpenAIEmbeddings` не экспонирует usage; оценка — по объёму чанков
(chars/4), не замер.

---

## Типовые проблемы

| Симптом | Причина / действие |
|---------|--------------------|
| Занят порт (`address already in use`) | 5433/8001/8089/8600/8080 заняты — освободить или сменить маппинг в compose |
| UI «Failed to fetch» | health :8600; при прямом доступе к API — CORS в `.env` |
| Нет таблиц PG | volume без init — пересоздать volume или применить SQL ([POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md)) |
| Бот молчит | реальный `TELEGRAM_BOT_TOKEN` + `restart assistant-flow`; логи `assistant-flow` |
| Пустой RAG / без источников | корпус не индексирован — [ADMIN_INDEXING.md](ADMIN_INDEXING.md) |
| OCR error | `OPENAI_API_KEY` задан, режим `/mode ocr` |
| Degraded health | причины в теле `/api/health` (например, пустой корпус RAG — норма до индексации) |
| Медленный admin-api при reindex | heavy RAG safeguard; не совмещать reindex с параллельным RAG |

---

## См. также

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — развёртывание
- [ADMIN_INDEXING.md](ADMIN_INDEXING.md) — индексация
- [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md) — smoke RAG
- [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md) — демо-чеклист