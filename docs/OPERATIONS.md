# Операции Assistant Flow

Операционное дополнение к [RUNBOOK.md](../RUNBOOK.md): больше деталей по compose, портам, зависимостям и продвинутым сценариям. Для быстрого старта GitHub/demo сначала [README.md](../README.md) и RUNBOOK.

---

## Канонический запуск (portfolio)

Основной контур для локальной разработки, демо и GitHub:

```bash
cp .env.example .env
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

- **Имя проекта compose:** `portfolio-test` (изоляция от других стеков на той же машине).
- **Не использовать** обобщённую команду `docker compose up -d --build` без `-p portfolio-test` и без `-f docker-compose.portfolio.yml`.

### Сервисы и порты (хост)

| Сервис | Роль | Порт на хосте |
|--------|------|----------------|
| `postgres` | PostgreSQL 16 | **5433** → 5432 в сети compose |
| `chroma` | ChromaDB HTTP | **8001** → 8000 |
| `weaviate` | Weaviate HTTP | **8089** → 8080 |
| `admin-api` | FastAPI Admin API | **8600** |
| `admin-ui` | React (nginx + Vite build) | **8080** |
| `assistant-flow` | Telegram-бот | без публикации порта |

Volumes: `data/documents`, `storage`, `outputs` — см. `docker-compose.portfolio.yml`.

### Проверка после запуска

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml ps
curl -sS http://localhost:8600/api/health
# UI: http://localhost:8080
```

`GET /api/health` возвращает агрегированный статус (`ok` / `degraded`) по PostgreSQL, Chroma, RAG и снимкам LLM.

### Telegram

Контейнер `assistant-flow` запускает `run_telegram_bot.py`. Нужен реальный `TELEGRAM_BOT_TOKEN` (не плейсхолдер из `.env.example`). С плейсхолдером контейнер остаётся живым, polling не стартует.

### Admin UI и API

- API: `run_admin_api.py` → порт **8600**.
- UI: образ `admin-ui` со статикой; браузер обращается к `VITE_ADMIN_API_BASE_URL` (по умолчанию `http://localhost:8600`).
- CORS: `ADMIN_API_CORS_ORIGINS` (для portfolio: `http://localhost:8080`).

При смене хоста/порта API пересоберите `admin-ui` с нужным build-arg.

---

## PostgreSQL

При **первом** создании тома `portfolio_pg_data` выполняются скрипты из `/docker-entrypoint-initdb.d/`:

- `database/schema.sql`;
- `database/migrations/004_async_jobs_foundation.sql`.

Если том создан раньше без init — удалите volume (**потеря данных**) или примените SQL вручную.

`DATABASE_URL` в portfolio: `postgresql://assistant:assistant@postgres:5432/assistant_flow`.

---

## Chroma и Weaviate

### Chroma (portfolio)

- Том: `portfolio_chroma_data`.
- **Удаление volume = полная потеря векторов** до повторной индексации.
- В `.env` для portfolio: `CHROMA_USE_HTTP=true`, `CHROMA_HOST=chroma`, `CHROMA_PORT=8000` (внутри сети compose; с хоста — порт **8001**).

### Weaviate (portfolio)

- Том: `portfolio_weaviate_data`, порт на хосте **8089**.
- Активируется при `RAG_BACKEND=weaviate` (см. Retrieval Settings / `.env`).

### FAISS

- Каталог на диске: `storage/faiss` (volume `storage` в compose).
- Переключение backend — через Admin UI (**Retrieval Settings**) или env; после смены может потребоваться reindex.

---

## Индексация и документы

См. [ADMIN_INDEXING.md](ADMIN_INDEXING.md).

- Загрузка и reindex через Admin UI → **Документы** (`/documents`).
- CLI: `python scripts/admin_index_documents.py --reindex`.
- Каталог по умолчанию: `data/documents/`.

Предупреждение: повторная индексация без `--reindex` может дать **дубликаты чанков** в векторном хранилище.

---

## Кэш запросов к базе знаний

При `ENABLE_RETRIEVAL_CACHE=true` (env или Retrieval Settings → БД) в RAG-консоли видны OFF / MISS / HIT и задержки.

Диагностика:

1. Открыть **RAG** в Admin UI, выполнить два одинаковых запроса подряд.
2. Ожидание: первый MISS (или OFF), второй HIT при включённом кэше.
3. Сброс кэша: reindex, смена активного backend, часть параметров top_k — см. `docs/architecture/cache_layer_design.md`.

---

## Логи и наблюдаемость

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml logs -f admin-api
docker compose -p portfolio-test -f docker-compose.portfolio.yml logs -f assistant-flow
```

- **Overview** / **Summary** / **Logs** в Admin UI — агрегаты и `processing_logs` (PostgreSQL).
- Технический слой `logs.db` (SQLite) — отдельно от продуктового контура; см. [ARCHITECTURE.md](ARCHITECTURE.md).

Smoke-проверки RAG: [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md). Демо-сценарии: [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md).

---

## SSH-туннель (удалённый хост)

См. [RUNBOOK.md](../RUNBOOK.md) §6 — проброс портов UI, API и Chroma.

---

## Переменные окружения

- Локально / demo: `.env` из **`.env.example`** (только плейсхолдеры в git).
- Полный перечень — `.env.example`, краткий обзор — [README.md](../README.md).

---

## Продвинутое: server-контур (не основной путь)

Для развёртывания в существующей инфраструктуре (вне portfolio-demo):

- файл `docker-compose.assistant.yml`;
- внешние сети, Traefik / HTTPS на периметре;
- env: `.env.server` (не коммитить).

**Не смешивать** portfolio-команду с server-compose без понимания сетей и имён контейнеров. Детали — §8 в [RUNBOOK.md](../RUNBOOK.md).

Исторический Streamlit UI (`admin_ui/`, порт 8501) в server-compose **не** является текущей административной консолью; операторский UI — **React** `frontend/admin-ui/`.
