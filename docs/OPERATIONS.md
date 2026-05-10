# Операции (черновик)

Краткий каркас для запуска и сопровождения **assistant-flow**. Детали дорабатываются по мере упаковки репозитория.

## Сервисы и порты

### Portfolio compose (`docker-compose.portfolio.yml`)

| Сервис | Роль | Порт на хосте (по умолчанию) |
|--------|------|------------------------------|
| `postgres` | PostgreSQL 16 | 5432 |
| `chroma` | ChromaDB HTTP | 8000 |
| `assistant-flow` | Telegram-бот | — (без публикации порта) |
| `admin-api` | FastAPI Admin API | 8600 |
| `admin-ui` | Статика React (nginx после Vite build) | 8080 |

Все сервисы в одной пользовательской Docker-сети compose; **external networks не используются**.

### Server compose (`docker-compose.assistant.yml`)

Ориентирован на уже существующую инфраструктуру: внешние сети, `env_file: .env.server`, отдельный сервис Streamlit на 8501. Подробности в корневом `docker-compose.assistant.yml` и `.env.server.example`.

## Переменные окружения

- Локально / demo: `.env` из **`.env.example`**.
- Сервер: **`.env.server`** из **`.env.server.example`** (файл с секретами не коммитить).

## PostgreSQL: первичная настройка

1. Убедиться, что контейнер `postgres` healthy.
2. Применить **`database/schema.sql`** к базе `assistant_flow` (и при необходимости файлы из `database/migrations/` в согласованном порядке — уточняйте для своей среды).

Без схемы часть функций Admin API и lifecycle-логирования будет недоступна или будет деградировать.

## Chroma

- Индекс хранится в именованном volume **`portfolio_chroma_data`** (portfolio) или **`assistant_chroma_data`** (server compose).
- Удаление volume означает **полную потерю векторов** до повторной индексации.

## Индексация знаний

См. [ADMIN_INDEXING.md](ADMIN_INDEXING.md). Документы по умолчанию ожидаются под `data/documents/` (маппинг volume в compose).

## Admin API и UI

- API: `python run_admin_api.py` (uvicorn `0.0.0.0:8600` внутри контейнера `admin-api`).
- UI в portfolio: образ собирает фронт с `VITE_ADMIN_API_BASE_URL=http://localhost:8600` — браузер на хосте обращается к опубликованному порту API.

При смене хоста/порта API пересоберите образ `admin-ui` с нужным build-arg или задайте согласованный `ADMIN_API_CORS_ORIGINS` в `.env`.

## Telegram-бот

Контейнер `assistant-flow` запускает `run_telegram_bot.py`. Нужен валидный `TELEGRAM_BOT_TOKEN` в `.env`.

## Полезные проверки

- `GET http://localhost:8600/api/health` — агрегированный health / degraded.
- Логи: `docker compose -f docker-compose.portfolio.yml logs -f <service>`.
