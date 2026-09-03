# ⚙️ Операции Assistant Flow — справочник

**Роли документов:**

| Документ | Назначение |
|----------|------------|
| [RUNBOOK.md](../RUNBOOK.md) | Onboarding: пошаговый запуск, smoke, Telegram, SSH, типовые сбои |
| **OPERATIONS.md** (этот файл) | Справочник: compose, порты, топология, Postgres, backends, диагностика |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Компоненты и потоки |
| [database/POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md) | Детали SQL и миграций вне Docker |

Быстрый старт — [RUNBOOK.md](../RUNBOOK.md) («Быстрый маршрут с нуля»).

---

## RUNBOOK как часть runtime contract

Изменения compose, портов, `.env.example`, миграций БД или маршрутов Telegram/OCR/RAG должны сопровождаться обновлением **RUNBOOK.md** и этого файла; при смене UX — **USER_GUIDE.md**; при смене компонентов — **ARCHITECTURE.md**. См. [RUNBOOK.md](../RUNBOOK.md) § «RUNBOOK как часть runtime contract».

---

## Operational topology (portfolio)

Кто с кем говорит при локальном запуске:

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

Субдомен (с 2026-09-02): роутер `assistant-flow-admin` в `/opt/n8n/dynamic.yml`
(файл-провайдер traefik без watch — после правки нужен `docker restart
n8n-traefik-1`); бандл UI собирается с пустым `VITE_ADMIN_API_BASE_URL`
(относительные `/api`), поэтому `ADMIN_API_CORS_ORIGINS` не требуется —
запросы same-origin.

Авторизация (демо-стандарт APL, с 2026-09-02): вход консоли по Bearer-токену —
`AF_ADMIN_TOKEN` (роль `admin`) и `AF_ADMIN_DEMO_TOKEN` (витринный вход
«Войти в демо-режиме», роль `demo`, read-only). Токены заданы в `.env`
(значения не коммитятся); при заданном `AF_ADMIN_TOKEN` enforcement
автоматически `required`. Проверка токена — `GET /api/auth/whoami`, входы
пишутся в аудит (`console_login`). Демо-токен запекается в бандл при сборке
(`VITE_OPS_DEMO_TOKEN` из `AF_ADMIN_DEMO_TOKEN`). Смена токенов → обновить
`.env` и пересобрать `admin-ui` (демо-токен в бандле) + пересоздать
`admin-api` (env).

SSH tunnel: проброс host-портов на ноутбук — [RUNBOOK.md](../RUNBOOK.md) §J.

![Обзор состояния платформы](screenshots/overview-adm.png)

<p align="center"><em>
Обзор состояния платформы Assistant Flow: health-check сервисов, активные AI-провайдеры, retrieval backend и операционные метрики.
</em></p>

---

## Compose portfolio

| Параметр | Значение |
|----------|----------|
| Файл | `docker-compose.portfolio.yml` |
| Project | из имени каталога (по умолчанию `assistant-flow`), флаг `-p` не используется |
| Команда | см. RUNBOOK §C |

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

### Admin UI build

`VITE_ADMIN_API_BASE_URL=http://localhost:8600` при сборке образа `admin-ui`. Смена хоста/порта → пересборка с другим build-arg + `ADMIN_API_CORS_ORIGINS`.

---

## PostgreSQL (справочник)

**Первый запуск / smoke:** [RUNBOOK.md](../RUNBOOK.md) §D.  
**SQL, роли, цепочка миграций:** [database/POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md).

Факты для compose:

| Initdb (новый volume) | Файл |
|----------------------|------|
| `01_schema.sql` | `database/schema.sql` (snapshot, вкл. 005/006) |
| `02_async_jobs.sql` | `database/migrations/004_async_jobs_foundation.sql` |

005/006 **не** в initdb — на свежей БД уже в `schema.sql`; файлы 005/006 — апгрейд **старых** volume.

```bash
# проверка с хоста
psql "postgresql://assistant:assistant@localhost:5433/assistant_flow" -c '\dt' | head -15
```

---

## Vector backends

| Backend | Хранение | Env / UI |
|---------|----------|----------|
| **Chroma** | volume `assistant-flow_portfolio_chroma_data` | `CHROMA_USE_HTTP=true`, `CHROMA_HOST=chroma`, `CHROMA_PORT=8000` |
| **Weaviate** | volume `assistant-flow_portfolio_weaviate_data` | `RAG_BACKEND=weaviate`, `WEAVIATE_HOST=weaviate` |
| **FAISS** | `storage/faiss` (bind) | `RAG_BACKEND=faiss`, `FAISS_INDEX_DIR` |

Удаление volume Chroma/Weaviate = полная переиндексация.

Активный backend: Admin UI **Retrieval Settings** (`/retrieval`) → `platform_settings` в Postgres.

![Панель Retrieval Settings](screenshots/rs-adm.png)

<p align="center"><em>
Панель управления retrieval backend: переключение vector storage, runtime tuning, chunking и cache-настройки RAG.
</em></p>

---

## Retrieval cache

- SQLite: `storage/cache/assistant_cache.sqlite3` (`CACHE_DB_PATH`).
- Включение: `ENABLE_RETRIEVAL_CACHE` или Retrieval Settings (override в БД).
- UI: OFF / MISS / HIT в RAG-консоли.
- Дизайн: [architecture/cache_layer_design.md](architecture/cache_layer_design.md).

### Полный текст чанка

Операционные логи RAG-сессий хранят только preview чанка (96 символов). Полный текст живёт в vector store и доступен:

- **UI**: карточка чанка → «показать полный текст» — модалка запрашивает полный текст с сервера; при недоступности (чанк вне индекса, ошибка backend) показывается текст из логов с пояснением.
- **API**: `GET /api/retrieval/chunk-fulltext?source=<file>&text_fp=<fp>&chunk_index=<n>` (право `retrieval:read`). Совпадение по порядку: `text_fp` (fingerprint текста) → `chunk_index` → единственный кандидат. Ответ: `found, matched_by, text, truncated, reason|…`.

Ограничение: если документ удалён из индекса (переиндексация), полный текст недоступен — модалка показывает лог-preview с note.

![Расширенная диагностика retrieval](screenshots/retrieval-details-adm.png)

<p align="center"><em>
Расширенная диагностика retrieval: найденные чанки, relevance-score, latency retrieval и состояние retrieval cache.
</em></p>

![Сравнение retrieval cache MISS и HIT](screenshots/cache-hit-adm.png)

<p align="center"><em>
Сравнение retrieval cache MISS и HIT: снижение latency retrieval при повторном запросе.
</em></p>

---

## Asset / Storage

- `services/asset_repository_factory.py` — абстракция хранения.
- Каталоги: `storage/assets`, `data/documents`, `outputs` (compose volumes).
- Admin API: upload документов, preview изображений/аудио.

![Управление документами knowledge base](screenshots/documents-adm.png)

<p align="center"><em>
Управление документами knowledge base: индексация, preprocessing, версии документов и жизненный цикл ingestion pipeline.
</em></p>

---

## Логи

```bash
docker compose -f docker-compose.portfolio.yml logs -f admin-api
docker compose -f docker-compose.portfolio.yml logs -f assistant-flow
```

| Слой | Где |
|------|-----|
| Продуктовый lifecycle | PostgreSQL `processing_logs`, `intake_events` |
| Технический провайдер | SQLite `logs.db` (часть оркестратора/изображений) |

Admin UI: **Overview**, **Summary**, **Logs**.

Токен-экономика (долг №3, 2026-09-02): панель **Summary → F. Токен-экономика
(точное окно)** — SQL-агрегация `processing_logs` за период (`/api/summary`
→ `token_economy`): гранд-тотал, разбивка по этапам (`by_stage`) и моделям
(`by_model`). Это точные суммы по полному окну, в отличие от блока
«Телеметрия провайдеров», который считает по хвостовой выборке.
Покрытие: `rag_answer_done`, `text_answer_done`, OCR, image-refinement,
STT/TTS (usage провайдера, с 02.09). Embeddings (`text-embedding-3-small`)
не захватываются на уровне API-usage — LangChain `OpenAIEmbeddings` не
экспонирует usage ответа; оценка — по объёму чанков (chars/4), не замер.

![Журнал execution-сессий](screenshots/logs-adm.png)

<p align="center"><em>
Журнал execution-сессий и трассировка pipeline обработки запросов Assistant Flow.
</em></p>

![Сводная операционная статистика](screenshots/summary-adm.png)

<p align="center"><em>
Сводная операционная статистика платформы: маршруты обработки, этапы pipeline, телеметрия провайдеров и агрегированные метрики.
</em></p>

---

## SSH tunnel

Пошагово: [RUNBOOK.md](../RUNBOOK.md) §J.

---

## Server-контур

`docker-compose.assistant.yml`, `.env.server`, Traefik — [RUNBOOK.md](../RUNBOOK.md) (конец). Не основной путь GitHub demo.

Исторический Streamlit (`admin_ui/`) **не** текущая консоль; UI — `frontend/admin-ui/`.

---

## См. также

- [ADMIN_INDEXING.md](ADMIN_INDEXING.md)
- [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md)
- [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md)
