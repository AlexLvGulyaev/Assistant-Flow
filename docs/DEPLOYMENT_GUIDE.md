# 🚀 DEPLOYMENT_GUIDE.md — Assistant Flow

**Статус:** актуально на 2026-09-15.

Полная процедура развёртывания с нуля на чистой машине. Документ — Source of Truth
воспроизводимости проекта: по нему должен разворачиваться работающий стек, не используя
никаких знаний, кроме публичного репозитория.

Развёртывание validated запуском: см. [DEPLOYMENT_VALIDATION_REPORT.md](DEPLOYMENT_VALIDATION_REPORT.md)
(Guide ≠ Evidence — инструкция и отчёт о проверке инструкции — разные документы).

---

## 🧰 1. Требования к окружению

| Требование | Значение |
|------------|----------|
| ОС | Linux или macOS (Windows — через WSL2) |
| Docker | Docker Engine **24+**, Docker Compose v2 (`docker compose`, плагин) |
| RAM | 4 ГБ свободных минимум (полный стек ~1 ГБ + индексация) |
| Порты на хосте | свободны: **5433** (PostgreSQL), **8001** (Chroma), **8089** (Weaviate), **8600** (Admin API), **8080** (Admin UI) |
| Прочее | `curl` — для проверок (§6); `git` |

Проверить версию Docker:

```bash
docker --version
docker compose version
```

---

## 📥 2. Получение репозитория

```bash
git clone https://github.com/AlexLvGulyaev/Assistant-Flow.git
cd Assistant-Flow
```

Все последующие команды выполняются из корня репозитория.

---

## 🌐 3. Сеть Docker (n8n_default)

`docker-compose.portfolio.yml` подключает контейнеры к внешней сети `n8n_default`
(в ней же работает reverse-proxy для публичного поддомена). Если сети нет, Compose
упадёт с ошибкой `network n8n_default declared as external, but could not be found`.

Проверить и при отсутствии создать:

```bash
docker network ls | grep n8n_default || docker network create n8n_default
```

Локальное создание сети безвредно: без reverse-proxy она просто не используется.

---

## 🔧 4. Переменные окружения

```bash
cp .env.example .env
```

Минимум для работоспособного запуска (заполните в `.env`):

| Переменная | Что задать |
|------------|-----------|
| `TELEGRAM_BOT_TOKEN` | Токен своего бота из [@BotFather](https://t.me/BotFather) (создайте бота через `/newbot`, скопируйте токен вида `123456:ABC-...`) |
| `OPENAI_API_KEY` **или** `GIGACHAT_AUTH_KEY` **или** `PROXY_API_KEY` | Ключ одного из AI-провайдеров (chat + embeddings). По умолчанию `IMAGE_PROVIDER=proxy`, image-генерация использует `PROXY_API_KEY` |
| `DATABASE_URL` | Менять не нужно: `postgresql://assistant:assistant@postgres:5432/assistant_flow` уже указывает на сервис `postgres` в compose |

Доступ к операционной консоли (опционально, но рекомендуется для любой машины,
открытой за пределами localhost):

| Переменная | Роль | Поведение |
|------------|------|-----------|
| `AF_ADMIN_TOKEN` | admin | Полный доступ к Admin API. **Задан → консоль защищена** (Bearer-токен) |
| `AF_ADMIN_DEMO_TOKEN` | demo (read-only) | Витринный вход «Войти в демо-режиме»; запекается в сборку UI (`VITE_OPS_DEMO_TOKEN`) — **смена значения требует пересборки admin-ui** |

- Оба не заданы → консоль открыта без авторизации (локальный режим разработки).
- Значения — произвольные длинные случайные строки; реальные токены не коммитить.
- Расширенные auth-параметры (`AF_AUTH_MIDDLEWARE_MODE`, `AF_SESSION_SECRET`,
  `INITIAL_ADMIN_*`, Basic auth) описаны в [SECURITY_NOTES.md](SECURITY_NOTES.md).

Опциональные подсистемы (по умолчанию выключены): retrieval cache
(`ENABLE_RETRIEVAL_CACHE`), RAGAS-оценка (`ENABLE_RAGAS_EVALUATION`), аудио
(`AUDIO_ENABLED=true` при `STT_PROVIDER`/`TTS_PROVIDER=disabled` — голос не работает).
Полный список переменных с комментариями — `.env.example`.

---

## ▶️ 5. Первый запуск

```bash
COMPOSE_BAKE=false docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

Первый запуск занимает несколько минут (сборка multi-stage образов admin-api и admin-ui).

**Инициализация БД.** При первом создании volume `portfolio_pg_data` PostgreSQL
автоматически применяет `database/schema.sql` + `database/migrations/004_async_jobs_foundation.sql`
(смонтированы в `docker-entrypoint-initdb.d`). Ничего вручную выполнять не нужно.
Апгрейд существующей базы со старой схемой — [database/POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md).

**Telegram.** При placeholder-токене из `.env.example` контейнер `assistant-flow`
не падает — он ждёт реальный токен. Admin API/UI работают и без бота.

---

## ✅ 6. Проверка успешного запуска

### 6.1 Состояние контейнеров

```bash
docker compose -f docker-compose.portfolio.yml ps
```

Ожидание: `postgres` — healthy; `admin-api` — healthy; `weaviate` — healthy;
`chroma`, `assistant-flow`, `admin-ui` — Up.

### 6.2 Health Admin API

```bash
curl -sS http://localhost:8600/api/health
```

Ожидание: HTTP 200, `"status": "ok"` (или осознанный `"degraded"` — например, при
пустом корпусе RAG — с понятными причинами в теле). В теле — поля зависимостей
(`postgres`, `chroma`, `rag` и др.). При наличии `jq` ответ удобно
форматировать: `curl -sS http://localhost:8600/api/health | jq .`.

### 6.3 PostgreSQL

```bash
docker exec assistant-flow-postgres-1 psql -U assistant -d assistant_flow -c "\dt"
```

Ожидание: таблицы `app_users`, `documents`, `chat_sessions`, `processing_logs`,
`intake_events`, `platform_settings`, `async_jobs` и др. присутствуют.

### 6.4 Векторные хранилища

```bash
curl -sS http://localhost:8001/api/v2/heartbeat            # Chroma → {"nanoseconds":...}
curl -sS http://localhost:8089/v1/.well-known/ready        # Weaviate → 200 (пустой ответ)
```

### 6.5 Admin UI

Открыть `http://localhost:8080` — экран «Обзор» консоли загружается, данные health
видны (API — same-origin `/api` через nginx контейнера admin-ui; CORS к
`localhost:8600` из браузера не требуется).

Вход: если `AF_ADMIN_TOKEN`/`AF_ADMIN_DEMO_TOKEN` заданы — экран входа
(токен или «Войти в демо-режиме»); если не заданы — консоль открыта.

---

## 🤖 7. Проверка Telegram-бота

1. Откройте бота в Telegram по имени из BotFather → **/start**.
2. `/help` — справка по режимам.
3. `/mode text` → вопрос («объясни простыми словами, что такое инфляция») →
   текстовый ответ.
4. `/stats` — число чанков индекса (после индексации, §8).

Если бот не отвечает: `docker logs assistant-flow-assistant-flow-1 --tail 50`
— при placeholder-токене будет сообщение об ожидании реального токена.

---

## 📚 8. Загрузка базы знаний и RAG

Операторская операция — Admin UI:

1. `http://localhost:8080/documents` → загрузить файл (PDF/TXT/MD, лимит
   `ADMIN_UPLOAD_MAX_MB`, default 25 МБ).
2. Дождаться pipeline индексации (документ в списке, `chunk_count` > 0).
3. Telegram `/mode rag` → вопрос по содержимому файла → ответ + блок «Источники».

Подробности и CLI-альтернатива: [ADMIN_INDEXING.md](ADMIN_INDEXING.md).
Быстрая проверка RAG без Telegram: [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md).

---

## 🔄 9. Остановка, перезапуск, обновление

```bash
# Остановка (данные volumes сохраняются)
docker compose -f docker-compose.portfolio.yml down

# Перезапуск без пересборки
COMPOSE_BAKE=false docker compose -f docker-compose.portfolio.yml up -d

# Обновление после изменения кода
COMPOSE_BAKE=false docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

**Внимание:** `down -v` или удаление volume `portfolio_chroma_data` =
полная потеря векторов (требуется reindex из `data/documents/`). Volume
`portfolio_pg_data` без init-файлов не переинициализируется — см.
[OPERATIONS.md](OPERATIONS.md).

---

## 🧩 10. Альтернативный контур (server, продвинутый)

`docker-compose.assistant.yml` — server-контур: внешние сети, Traefik,
`.env.server`. Не предназначен для клона репозитория; канонический путь
демо/разработки — portfolio-compose выше. Описание — [OPERATIONS.md](OPERATIONS.md).

---

## 🧯 11. Типовые проблемы

| Симптом | Причина | Действие |
|---------|---------|----------|
| `network n8n_default declared as external, but could not be found` | сеть не создана | §3: `docker network create n8n_default` |
| Порт занят (`bind: address already in use`) | на хосте занят 5433/8001/8089/8600/8080 | освободить порт или изменить маппинг в `docker-compose.portfolio.yml` (левую часть `"хост:контейнер"`) |
| Бот «молчит» | placeholder-токен | задать реальный `TELEGRAM_BOT_TOKEN`, пересоздать контейнер |
| `documents`-таблиц нет, UI Документы пустой | volume БД создан до init-файлов | удалить volume `portfolio_pg_data` (чистый стенд) или применить SQL вручную ([POSTGRES_SETUP.md](../database/POSTGRES_SETUP.md)) |
| RAG отвечает без источников | корпус не индексирован | §8 (загрузка + индексация) |
| Деградация при тяжёлой индексации | heavy RAG на малом VPS | не совмещать reindex с параллельным RAG; лимит `ADMIN_UPLOAD_MAX_MB` |

---

## 📚 Связанные документы

- [OPERATIONS.md](OPERATIONS.md) — эксплуатация и справочник операций
- [SECURITY_NOTES.md](SECURITY_NOTES.md) — доступ, роли, аудит
- [ADMIN_INDEXING.md](ADMIN_INDEXING.md) — индексация базы знаний
- [DEMO_ROUTE.md](DEMO_ROUTE.md) — маршрут проверки демо
- [DEPLOYMENT_VALIDATION_REPORT.md](DEPLOYMENT_VALIDATION_REPORT.md) — доказательство воспроизводимости гайда