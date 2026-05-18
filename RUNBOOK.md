# Assistant Flow Operational Runbook v1

> Статус: документ в разработке.  
> Эта версия фиксирует минимальный порядок запуска и диагностики проекта для GitHub v2.0.

---

## 1. Назначение документа

RUNBOOK описывает эксплуатационные процедуры Assistant Flow:

- запуск portfolio-контура;
- проверку состояния сервисов;
- базовую диагностику;
- безопасные команды Docker Compose;
- будущие процедуры восстановления.

Цель документа — дать другому инженеру возможность развернуть проект и выполнить первичную проверку без чтения всей внутренней документации.

---

## 2. Канонический контур запуска

Для GitHub/demo используется portfolio-контур:

```bash
cp .env.example .env
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

Важно: для portfolio-контура используется project name `portfolio-test`.

---

## 3. Проверка состояния

### Контейнеры

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Admin API

```bash
curl -sS http://localhost:8600/api/health
```

### Admin UI

Открыть в браузере:

```text
http://localhost:8080
```

---

## 4. Базовый smoke-порядок

После запуска проверить:

1. Admin UI открывается.
2. Admin API отвечает на `/api/health`.
3. PostgreSQL контейнер запущен.
4. Chroma контейнер запущен.
5. RAG-раздел открывается в административной консоли.
6. Документы доступны в разделе «Документы».

---

## 5. Работа с документами и RAG

Базовый порядок:

1. Загрузить документы через Admin UI.
2. Запустить или дождаться индексации.
3. Проверить, что документы появились в списке.
4. Выполнить RAG-запрос.
5. Проверить найденные чанки и диагностические панели в RAG-консоли.

---

## 6. SSH tunnel / удалённый доступ

Если сервисы на удалённом хосте, а браузер и CLI — локально:

```bash
ssh -L 8080:127.0.0.1:8080 -L 8600:127.0.0.1:8600 -L 8001:127.0.0.1:8001 user@remote-host
```

- Admin UI: `http://localhost:8080`
- Admin API: `http://localhost:8600`
- Chroma с хоста: `127.0.0.1:8001` (`CHROMA_HOST`, `CHROMA_PORT` в локальном `.env`)

Бот, CLI и UI должны указывать на **один** backend и коллекцию. При смене IP/портов контейнеров обновите проброс и `.env`.

---

## 7. Типовые проблемы

### Параллельный compose-контур

Запуск без `-p portfolio-test` может поднять второй стек с конфликтом портов.

### Потеря Chroma / Weaviate / FAISS

Удаление volume (`portfolio_chroma_data`, `portfolio_weaviate_data`, каталог FAISS в `storage/`) требует **полной переиндексации**.

### Telegram-бот без polling

Плейсхолдер `TELEGRAM_BOT_TOKEN` в `.env.example`: контейнер `assistant-flow` **не падает**, polling ждёт реальный токен (`123456:AA...`).

### Ошибка env / ключей

Проверить `OPENAI_API_KEY` (OCR/RAG), `GIGACHAT_*` (текст), соответствие `RAG_BACKEND` и доступности Chroma/Weaviate.

---

## 8. Server-контур (production)

Для развёртывания вне portfolio-демо используется отдельный compose-файл `docker-compose.assistant.yml`:

- внешние сети (n8n, Traefik);
- Traefik / HTTPS на периметре;
- переменные окружения обычно в `.env.server`.

**Не смешивать** portfolio-команду (`-p portfolio-test`, `docker-compose.portfolio.yml`) с server-контуром без понимания имён контейнеров и сетей — возможны конфликты портов и дублирование сервисов.

---

## 9. Статус документа

Следующие версии RUNBOOK должны дополнить:

- SSH tunnel;
- reindex/rebuild процедуры;
- диагностику retrieval-кэша;
- действия при деградации Chroma / Weaviate / FAISS;
- резервное копирование;
- восстановление после ошибок.
