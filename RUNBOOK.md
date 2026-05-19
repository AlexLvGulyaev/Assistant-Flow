# Assistant Flow — Operational Runbook

Как **поднять** portfolio-стек и **проверить**, что он работает. Как **пользоваться** ботом и консолью после запуска — [USER_GUIDE.md](USER_GUIDE.md). Справочник портов и топологии — [docs/OPERATIONS.md](docs/OPERATIONS.md).

---

## A. Требования

| Ресурс | Минимум |
|--------|---------|
| **ОС** | Linux/macOS + Docker; Windows — WSL2 + Docker Desktop |
| **Docker** | Engine 24+ и команда `docker compose` (v2) |
| **RAM** | 4 GB+ |
| **Диск** | 2 GB+ |
| **Свободные порты** | 5433, 8001, 8089, 8600, 8080 |

Нужен исходящий интернет к API OpenAI / GigaChat / Proxy (RAG, OCR, текст).

**Не обязательно** знать Kubernetes или писать SQL на старте — достаточно скопировать команды ниже.

---

## Быстрый маршрут с нуля

| # | Шаг | Подробности |
|---|-----|-------------|
| 1 | Склонировать репозиторий | [§B.1](#b1-клонирование) |
| 2 | `cp .env.example .env` | [§B.2](#b2-файл-окружения) |
| 3 | Создать бота в BotFather, вписать токен | [§B.3](#b3-telegram-бот-botfather) |
| 4 | Заполнить ключи OpenAI / GigaChat | [§B.2](#b2-файл-окружения) |
| 5 | `docker compose up` (portfolio) | [§C.1](#шаг-1--сборка-и-старт) |
| 6 | Проверить Admin API | [§C.2](#шаг-2--admin-api-health) |
| 7 | Открыть Admin UI в браузере | [§C.3](#шаг-3--admin-ui) |
| 8 | Убедиться, что PostgreSQL с таблицами | [§C.4](#шаг-4--postgresql) |
| 9 | Загрузить документ в **Документы** | [§I](#i-rag-smoke) |
| 10 | RAG smoke в Telegram | [§I](#i-rag-smoke) |
| 11 | OCR smoke в Telegram | [§H](#h-ocr-smoke) |
| 12 | Проверить **Логи** в Admin UI | [§I](#i-rag-smoke), [USER_GUIDE.md](USER_GUIDE.md) §13 |

---

## RUNBOOK как часть runtime contract

При изменении в репозитории:

- `docker-compose.portfolio.yml`, портов, имён сервисов;
- `.env.example` или обязательных переменных;
- startup Telegram / Admin API;
- `database/schema.sql` или `database/migrations/*`;
- маршрутов OCR / RAG / retrieval;

нужно обновить согласованно:

| Что изменилось | Документ |
|----------------|----------|
| Запуск, smoke, порты | **RUNBOOK.md**, [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| Поведение для пользователя | **USER_GUIDE.md** |
| Компоненты и потоки | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| SQL вне Docker | [database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md) |

Тот же принцип — в [docs/OPERATIONS.md](docs/OPERATIONS.md) § «Runtime contract».

---

## B. Подготовка

### B.1 Клонирование

```bash
git clone <URL-репозитория> assistant-flow
cd assistant-flow
```

**Что делает команда:** копирует проект на диск.

**Ожидаемый результат:** в каталоге есть `docker-compose.portfolio.yml`, `.env.example`, `README.md`.

**Если не получилось:** проверьте URL и доступ к git.

---

### B.2 Файл окружения

```bash
cp .env.example .env
```

**Что делает команда:** создаёт локальный `.env` (в git не коммитится).

**Ожидаемый результат:** файл `.env` рядом с compose.

**Минимум для smoke:** `TELEGRAM_BOT_TOKEN` (свой), `OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`. `DATABASE_URL` для portfolio уже подходит.

**Если не получилось:** нет `.env.example` — вы не в корне репозитория.

---

### B.3 Telegram-бот (BotFather)

1. Telegram → [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Задайте имя и **@username** бота.
3. Скопируйте токен `123456789:AAH...` в `.env` → `TELEGRAM_BOT_TOKEN=...`.

**Что это даёт:** свой бот; в репозитории **нет** общего demo-бота.

**Ожидаемый результат:** токен с двоеточием `:` внутри.

**Если не получилось:** оставлен плейсхолдер `your_telegram_bot_token` — polling не стартует (это нормально до замены токена).

Подробное использование бота — [USER_GUIDE.md](USER_GUIDE.md).

---

## C. Первый запуск (пошагово)

Общая команда compose (запомните префикс):

```bash
export DC="docker compose -p portfolio-test -f docker-compose.portfolio.yml"
```

### Шаг 1 — Сборка и старт

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

**Что делает команда:** собирает образы и поднимает 6 сервисов в фоне (`-d`). `-p portfolio-test` — имя проекта (отдельный стек). `COMPOSE_BAKE=false` — без лишнего bake в некоторых окружениях.

**Ожидаемый результат:** через 1–15 мин (первый раз) `docker compose ... ps` показывает контейнеры `Up`, postgres — `healthy`.

**Если не получилось:** «port already allocated» — заняты 8080/8600/5433/…; остановите другой compose или смените порты в compose (тогда обновите документацию).

---

### Шаг 2 — Admin API health

```bash
curl -sS http://localhost:8600/api/health
```

**Что делает команда:** запрос к HTTP API с вашего компьютера (порт **8600** проброшен из контейнера `admin-api`).

**Ожидаемый результат:** JSON; `"status":"ok"` или `"degraded"` с полями `postgres`, `chroma`, `rag`.

**Если не получилось:** `Connection refused` — подождите 30–60 с; `docker compose ... logs admin-api`.

---

### Шаг 3 — Admin UI

Откройте в браузере: `http://localhost:8080`

**Что это:** веб-консоль оператора (статика React + запросы к API на :8600).

**Ожидаемый результат:** меню слева (Обзор, RAG, Документы, …).

**Если не получилось:** «Failed to fetch» — API не доступен или CORS; в `.env`: `ADMIN_API_CORS_ORIGINS=http://localhost:8080`.

---

### Шаг 4 — PostgreSQL

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml exec postgres \
  psql -U assistant -d assistant_flow -c '\dt' | head -20
```

**Что делает команда:** заходит в контейнер Postgres и показывает список таблиц.

**Ожидаемый результат:** есть `documents`, `processing_logs`, `chat_sessions`, …

**Если таблиц нет:** старый Docker-volume без init — [§D](#d-postgresql-при-первом-запуске) или [database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md).

---

### Шаг 5 — Chroma / Weaviate (опционально)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/v2/heartbeat
curl -sS http://localhost:8089/v1/.well-known/ready
```

**Ожидаемый результат:** HTTP 200 / JSON ready.

---

### Шаг 6 — Telegram polling

После **реального** токена в `.env`:

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml restart assistant-flow
docker compose -p portfolio-test -f docker-compose.portfolio.yml logs -f assistant-flow
```

**Ожидаемый результат:** `starting infinity_polling...`

**Smoke:** в Telegram `/start` — ответ бота. Режимы и примеры — [USER_GUIDE.md](USER_GUIDE.md).

**Если не получилось:** placeholder-токен; бот не перезапущен; нет доступа к api.telegram.org.

---

## D. PostgreSQL при первом запуске

**При первом** создании тома `portfolio_pg_data` Docker **сам** выполняет:

1. `database/schema.sql` (целевая схема, включая объекты миграций 005/006);
2. `database/migrations/004_async_jobs_foundation.sql` — таблица `async_jobs` (в schema её нет).

**Проверка:** [§C.4](#шаг-4--postgresql).

**Старый volume** (таблиц не хватает): ручной `psql` с 005/006 — одна строка в [docs/OPERATIONS.md](docs/OPERATIONS.md) § PostgreSQL; полная цепочка SQL — [database/POSTGRES_SETUP.md](database/POSTGRES_SETUP.md).

**Пересоздать БД с нуля:** `docker compose ... down` → `docker volume rm portfolio-test_portfolio_pg_data` → снова §C.1 (**потеря данных**).

---

## E. Docker (кратко)

| | |
|---|---|
| Compose-файл | `docker-compose.portfolio.yml` |
| Имя проекта | `portfolio-test` (всегда `-p portfolio-test`) |
| Топология | [docs/OPERATIONS.md](docs/OPERATIONS.md) § Operational topology |

Не запускайте второй `docker compose up` без `-p portfolio-test` на той же машине.

---

## F. Проверка сервисов

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml ps
```

| Сервис | Как проверить с хоста |
|--------|------------------------|
| admin-ui | браузер `:8080` |
| admin-api | `curl :8600/api/health` |
| postgres | §C.4 |
| chroma | `:8001` |
| weaviate | `:8089` |
| assistant-flow | логи + `/start` в Telegram |

---

## G. Telegram — smoke (развёртывание)

1. Токен в `.env` + `restart assistant-flow` (§C.6).
2. В Telegram: `/start` → есть ответ.

Дальше — только проверка. Команды `/mode`, OCR, RAG, примеры: **[USER_GUIDE.md](USER_GUIDE.md)**.

---

## H. OCR smoke

1. `OPENAI_API_KEY` в `.env`.
2. Telegram: `/mode ocr` → фото с печатным текстом.
3. **Успех:** `Распознанный текст:...`
4. Admin UI → **Логи** — route `vision_ocr`.

Подробности и ограничения — [USER_GUIDE.md](USER_GUIDE.md) §8.

---

## I. RAG smoke

1. Admin UI → **Документы** → загрузить файл → дождаться `chunk_count` > 0.
2. Telegram: `/mode rag` → вопрос по документу.
3. **Успех:** ответ + источники; в UI **RAG** — чанки.

Подробности — [USER_GUIDE.md](USER_GUIDE.md) §7, [docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md).

---

## L. Остановка и перезапуск

### Остановить стек

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml down
```

**Что делает:** останавливает контейнеры; **volumes сохраняются** (БД и Chroma остаются).

### Перезапустить после смены `.env`

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d
docker compose -p portfolio-test -f docker-compose.portfolio.yml restart assistant-flow
```

**Когда нужно:** новый `TELEGRAM_BOT_TOKEN`, смена ключей API.

**Если не получилось:** `docker compose ... logs <service>`.

---

## J. SSH tunnel (удалённый сервер)

```bash
ssh -N \
  -L 8080:127.0.0.1:8080 \
  -L 8600:127.0.0.1:8600 \
  -L 8001:127.0.0.1:8001 \
  -L 5433:127.0.0.1:5433 \
  user@your-server
```

**Что делает:** порты сервера доступны на вашем `localhost` (браузер и `curl` как при локальном запуске).

**Проверка:** `curl http://localhost:8600/api/health` при открытом SSH.

Подробнее — [docs/OPERATIONS.md](docs/OPERATIONS.md) § SSH.

---

## K. Типовые проблемы

| Симптом | Действие |
|---------|----------|
| Занят порт | `docker ps`, освободить или сменить compose |
| UI не грузится | health :8600, CORS в `.env` |
| Нет таблиц PG | §D, POSTGRES_SETUP |
| Бот молчит | реальный токен + restart |
| Пустой RAG | документ не проиндексирован |
| OCR error | OPENAI_API_KEY, `/mode ocr` |

---

## Server-контур (не portfolio)

`docker-compose.assistant.yml` — отдельная топология; не смешивать с `portfolio-test` без необходимости. См. конец [docs/OPERATIONS.md](docs/OPERATIONS.md).

---

## Связанные документы

- [USER_GUIDE.md](USER_GUIDE.md) — использование после запуска
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — справочник
- [docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md) — демо-чеклист
