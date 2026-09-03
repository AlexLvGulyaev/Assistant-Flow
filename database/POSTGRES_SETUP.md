# 🗄️ PostgreSQL: применение схемы Assistant Flow

**SQL-level справочник.** Первый запуск в Docker, проверка таблиц и smoke — [RUNBOOK.md](../RUNBOOK.md) §D. Краткие факты compose — [docs/OPERATIONS.md](../docs/OPERATIONS.md) § PostgreSQL.

Документ описывает создание БД **вне** portfolio-compose и цепочку `schema.sql` / `database/migrations/`. Контракт полей — `database/db_contract.md`. Прикладной код использует **`DATABASE_URL`**.

## Требования

- PostgreSQL **14+** рекомендуется (в скрипте используются `gen_random_uuid()` и синтаксис триггеров `EXECUTE FUNCTION`; при необходимости уточните версию для вашей инсталляции).

## 1. Создать роль и базу

Пример через `psql` под суперпользователем:

```sql
CREATE USER assistant_flow WITH PASSWORD 'your_secure_password';
CREATE DATABASE assistant_flow OWNER assistant_flow;
GRANT ALL PRIVILEGES ON DATABASE assistant_flow TO assistant_flow;
```

Подключитесь к **новой** базе и выдайте права на схему `public` (если нужно):

```sql
\c assistant_flow
GRANT ALL ON SCHEMA public TO assistant_flow;
```

## 2. Применение миграций и schema.sql

Файл **`database/schema.sql`** описывает **итоговую** схему БД (снимок включает объекты миграций `002`–`008`; `004_async_jobs_foundation.sql` в снимок не входит).  
Файлы в **`database/migrations/`** (`002`, `003`, `004`, `005`, `006`, `007`, `008`) нужно применять **по порядку номеров** на уже существующей базе, если она была создана по более старой схеме.

### 2a. Новая БД (с нуля)

Достаточно один раз применить итоговую схему:

```bash
psql "$DATABASE_URL" -f database/schema.sql
```

Либо с явным URI:

```bash
psql "postgresql://assistant_flow:your_secure_password@localhost:5432/assistant_flow" -f database/schema.sql
```

Или интерактивно:

```bash
psql -U assistant_flow -d assistant_flow -h localhost -f database/schema.sql
```

Убедитесь, что команда завершилась без ошибок. Расширение `pgcrypto` должно быть доступно на сервере (`CREATE EXTENSION` в начале файла).

### 2b. Уже существующая БД (апгрейд с v1)

Не применяйте повторно полный `schema.sql` поверх заполненной v1, если не уверены в идемпотентности всех объектов: используйте миграции.

Пример для миграции **002** (runtime / lifecycle):

```bash
psql "$DATABASE_URL" -f database/migrations/002_runtime_lifecycle.sql
```

Полная цепочка (по порядку): `002_runtime_lifecycle` → `003_document_versions_active` → `004_async_jobs_foundation` → `005_platform_settings` → `006_evaluation_p1_lite` → `007_identity_foundation` → `008_admin_audit_extend`.

После успешного прогона миграций структура должна совпадать с актуальным **`database/schema.sql`** (сверка по `db_contract.md`).

**Важно:**

- миграции в `database/migrations/` применяются **последовательно** (001, 002, …), без пропусков;
- **`schema.sql`** — это **снимок целевой схемы**, а не замена цепочки миграций на проде: новые инсталляции поднимают БД через `schema.sql`; существующие — через накат миграций.

## 3. Переменная окружения

В `.env` (на основе `.env.example`) задайте:

```env
DATABASE_URL=postgresql://assistant_flow:your_secure_password@localhost:5432/assistant_flow
```

Формат совместим с драйвером **psycopg** (libpq URI). Для SSL и нестандартных портов добавьте параметры в URI по документации PostgreSQL.

## 4. Проверка подключения (опционально)

После установки зависимостей проекта из корня репозитория:

```bash
python -c "from repositories.connection import check_connection; print(check_connection())"
```

Должно вывести `True`, если `DATABASE_URL` корректен и схема доступна.

## Portfolio Docker Compose

Автоматический bootstrap при **новом** volume — только в [RUNBOOK.md](../RUNBOOK.md) §D (без дублирования здесь).

Ключевые факты:

- initdb: `schema.sql` + `004_async_jobs_foundation.sql`;
- `schema.sql` — snapshot целевой схемы (вкл. объекты 005–008);
- `async_jobs` — только из 004;
- 005–008 — для ручного апгрейда старых БД (см. §2b ниже).

`DATABASE_URL` в compose: `postgresql://assistant:assistant@postgres:5432/assistant_flow`.

---

## Дальнейшие изменения схемы

Любые новые таблицы или поля — только через SQL-миграцию в `database/migrations/`, затем обновление итогового `database/schema.sql` и `database/db_contract.md`, как указано в контракте v2.
