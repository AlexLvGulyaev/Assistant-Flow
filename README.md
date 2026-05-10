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

1. Скопировать переменные окружения и заполнить секреты:

   ```bash
   cp .env.example .env
   ```

2. Поднять стек (локальный Postgres + Chroma + бот + Admin API + статический UI):

   ```bash
   docker compose -f docker-compose.portfolio.yml up -d --build
   ```

3. Открыть в браузере:

   - Admin UI: `http://localhost:8080`
   - Admin API: `http://localhost:8600/api/health`

4. Перед полноценной работой с БД применить схему PostgreSQL (см. [docs/OPERATIONS.md](docs/OPERATIONS.md)).

**Серверный** сценарий с внешними сетями и Streamlit-админкой по-прежнему описан в `docker-compose.assistant.yml` и шаблоне `.env.server.example`.

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
