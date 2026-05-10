# Assistant Flow

**Portfolio-grade прототип** платформы операций вокруг мультимодального AI-ассистента: Telegram как канал для пользователей, **RAG** по администрируемой базе знаний (**Chroma**), контракт данных в **PostgreSQL**, операционная **FastAPI Admin API** и **React/Vite** консоль.

Это **single-tenant** демонстрационный проект: **нет публичной аутентификации и RBAC** для Admin API. Не выставляйте Admin API в интернет без reverse proxy, TLS и своей модели доступа.

---

## Что внутри

| Область | Описание |
|--------|----------|
| Пользователи | Telegram-бот: режимы text / RAG, опционально изображения и аудио по конфигурации |
| Знания | Индексация документов администратором (CLI), векторы в Chroma |
| Данные | PostgreSQL: документы, версии, логи обработки и др. (см. `database/schema.sql`) |
| Операции | FastAPI (`run_admin_api.py`), React admin UI, legacy Streamlit (`docker-compose.assistant.yml`) |

Подробная архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Быстрый старт (portfolio Docker)

Проверено smoke-тестом: `docker compose -f docker-compose.portfolio.yml` поднимает Postgres (с авто-init схемы), Chroma, `assistant-flow` (standby без реального Telegram token), Admin API и статический Admin UI.

1. Скопировать окружение (ключи провайдеров можно оставить placeholder для проверки UI/API):

   ```bash
   cp .env.example .env
   ```

2. Запуск:

   ```bash
   docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans
   ```

   Флаг `--remove-orphans` убирает контейнеры, которых больше нет в этом compose-файле. Если в одном каталоге параллельно поднимали `docker-compose.assistant.yml`, у обоих по умолчанию одинаковый **project name** — задайте уникальный, например:  
   `COMPOSE_PROJECT_NAME=assistant-flow-portfolio docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans`.

3. Проверки: `http://localhost:8080` (UI), `http://localhost:8600/api/health` (API). Chroma с хоста: `http://localhost:8001` (внутри compose — `chroma:8000`). PostgreSQL с хоста: `localhost:5433`.

4. **Telegram:** значение `your_telegram_bot_token` из шаблона не запускает polling — контейнер не падает. Для живого бота задайте токен вида `123456:AA...` и перезапустите сервис `assistant-flow`.

5. **Индексация RAG / LLM:** ключи GigaChat/OpenAI/Proxy и загрузка документов — отдельно (см. [docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md)); без них часть провайдеров в health будет `degraded` / не настроено.

**Серверный** сценарий: `docker-compose.assistant.yml`, `.env.server.example`.

**TODO (публичный README):** при смене портов или хоста пересобрать образ `admin-ui` с нужным `VITE_ADMIN_API_BASE_URL`.

---

## Документация

| Файл | Назначение |
|------|------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура и потоки данных |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Запуск, порты, порядок действий |
| [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md) | Риски и границы доверия |
| [docs/GITHUB_PREP.md](docs/GITHUB_PREP.md) | План очистки репозитория перед публичным GitHub |
| [docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md) | Индексация базы знаний |
| [docs/RAG_SMOKE_TEST.md](docs/RAG_SMOKE_TEST.md) | Локальная проверка RAG |
| [docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md) | Демо-сценарии |

---

## Шаблоны окружения

- **`.env.example`** — локальный/portfolio сценарий (имена сервисов `postgres`, `chroma` из `docker-compose.portfolio.yml`).
- **`.env.server.example`** — сервер: внешний Postgres, имена хостов как в вашей инфраструктуре, плейсхолдеры без секретов.

---

## Ограничения прототипа

- Один арендатор, упрощённая модель угроз для демо.
- Admin API без встроенного auth — см. [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md).
- Часть телеметрии и degraded-mode поведения — best-effort; том Chroma не удалять без осознанного reindex.

---

## Легаси

Каталог **`legacy/pem09_source/`** — справочный материал, **не импортируется** в рантайме.
