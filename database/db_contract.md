# Database Contract v2

## Общий принцип

PostgreSQL — **source of truth** для прикладных данных Assistant Flow / Career Knowledge Assistant.

**Разделение хранения:**

- **ChromaDB** хранит векторные представления (эмбеддинги) для RAG и идентификаторы чанков в коллекциях.
- **PostgreSQL** хранит пользователей, документы и **версии** документов, **метаданные и статусы** индексации, чанки как **строки метаданных** (связь с Chroma), диалоги, логи запросов и ошибок, **жизненный цикл обработки** (intake → processing → outbox / ошибки), аудит админки и агрегированные метрики.

Векторный поиск выполняется в ChromaDB; согласованность с документами обеспечивается полями вроде `document_chunks.chroma_collection` / `chroma_id` и статусами в PostgreSQL.

## execution_id

**`execution_id`** — строковый идентификатор **сквозной трассировки** одного логического запроса или задачи от входа до ответа (или ошибки).

Его следует проставлять в:

- `intake_events.execution_id` (уникально на событие);
- `processing_logs.execution_id`;
- `chat_messages.execution_id`;
- `request_logs.execution_id`;
- `error_logs.execution_id`;
- `indexing_jobs.execution_id`;
- `outbox.execution_id`;
- `generated_assets.execution_id`;
- при необходимости — `admin_audit_log.execution_id`.

Связь с конкретной записью входа: **`intake_event_id`** (UUID) в сообщениях, логах, outbox и assets.

## Lifecycle обработки

Логическая цепочка (упрощённо):

```text
intake_events
  → processing_logs
  → request_logs
  → error_logs (при сбоях)
  → outbox
  → generated_assets (при генерации файлов / медиа)
```

- **intake_events** — фиксация входящего события (канал, тип, сырой payload, статус обработки).
- **processing_logs** — структурированные стадии пайплайна (`stage`, `status`, `details`); вспомогательная функция `log_processing_event(...)`.
- **request_logs** — вызовы моделей/провайдеров, латентность, токены, оценка стоимости.
- **error_logs** — ошибки с уровнем серьёзности и опциональным разрешением.
- **outbox** — исходящие сообщения в каналы (например Telegram) до доставки.
- **generated_assets** — сгенерированные артефакты (изображения, аудио и т.д.) с привязкой к исполнению.

`request_logs` и `error_logs` не обязаны идти строго после `processing_logs` по времени; все узлы связываются через **`execution_id`** и при необходимости **`intake_event_id`**.

## Правила для кода

1. Не создавать новые таблицы и поля без изменения `database/schema.sql` и миграции в `database/migrations/`.
2. Все изменения схемы — через SQL (миграции + актуализация итогового `schema.sql`).
3. Не обращаться к PostgreSQL напрямую из handlers.
4. Доступ к БД — через слой repositories/services.
5. Telegram `user_id` — внешний идентификатор; в БД пользователь представлен в `app_users`.
6. Роли: legacy-поля `role` (`user`, `admin`) сохранены для совместимости; с миграции **007** действуют `platform_role` (`end_user`, `employee`, `operator`, `admin`, `auditor`, `superadmin`) и `retrieval_role` (`guest`, `employee`, `admin`). RBAC консоли оперирует `platform_role` — [SECURITY_NOTES.md](../docs/SECURITY_NOTES.md) §4.
7. Обычный пользователь не меняет базу знаний и индексацию; админ — может, с фиксацией в `admin_audit_log`.

## Объекты миграций 004–008

Snapshot `schema.sql` включает объекты миграций 002–008 (таблица `async_jobs` — из отдельного init-скрипта 02).

### async_jobs (004)

Очередь фоновых задач (reindex и др.): тип задачи, параметры (`payload`), статус (`queued`/`running`/`done`/`failed`/`cancelled`), попытки и ошибки; воркер — поток в admin-api.

### platform_settings (005)

Runtime-настройки платформы (ключ → значение): retrieval backend, retrieval cache, параметры безопасности; редактируются из консоли.

### Оценка качества (006)

`evaluation_dataset`, `evaluation_dataset_item`, `evaluation_run`, `evaluation_item`, `evaluation_metric_fact` — датасеты, прогоны оценки RAG (RAGAS), метрики по элементам.

### Identity (007)

`app_users` расширен: `email`, `password_hash`, `display_name`, `status`, **`platform_role`**, **`retrieval_role`**, `last_login_at`; legacy `role` сохранён. Новые таблицы: `user_channel_identities` (связка платформенный пользователь ↔ канал, например Telegram `user_id`), `auth_login_events` (события входов: способ, статус, IP-hash).

### admin_audit_log (008)

Расширение журнала аудита: `event_type`, `principal_email`, `platform_role`, `status`, `reason`, `request_path`, `request_method`, `ip_hash`, `user_agent` — записи не только о действиях администратора, но и об обращениях к Admin API (в т.ч. отказы 401/403).

## Таблицы (существующие, расширенные в v2)

### app_users

Пользователи Telegram и роли. С миграции **007** — также platform-пользователи: `email` + `password_hash` (legacy-вход), `display_name`, `status`, `platform_role`, `retrieval_role`, `last_login_at`; `telegram_user_id` допускает NULL. Связка с каналами — `user_channel_identities`.

### documents

Карточки документов. Расширение: статус **`deleted`** (мягкое удаление) в дополнение к `uploaded`, `indexing`, `indexed`, `failed`, `archived`.

### document_versions

Версии файлов и счётчик чанков. Контракт как в v1.

### indexing_jobs

Задачи индексации. Добавлены:

- `execution_id`, `triggered_by`, `job_type`, `stats` (JSONB);
- статусы: **`cancelled`**;
- типы задач: `index`, `reindex`, `delete_from_index`, `sync`.

### chat_sessions

Сессии. Режимы расширены: **`career`**, **`hr_screening`** (в дополнение к `text`, `rag`, `voice`, `image`). Поле **`user_id`** по-прежнему обязательно.

### chat_messages

История сообщений. Добавлены **`execution_id`**, **`intake_event_id`**.

### request_logs

Логи запросов. Добавлены **`execution_id`**, **`estimated_cost`**, **`metadata`**, **`intake_event_id`**; расширен перечень **`request_type`** (RAG по шагам, embedding, STT/TTS, `telegram_send`, `indexing` и др.).

### error_logs

Ошибки. Добавлены **`execution_id`**, **`severity`**, **`is_recoverable`**, **`resolved_at`**, **`intake_event_id`**.

## Новые таблицы v2

### user_preferences

Настройки пользователя (режим по умолчанию, голос, изображения, язык, произвольный `metadata`). Одна строка на пользователя (`user_id` UNIQUE).

### intake_events

Входящие события с **`execution_id`**, каналом (`source`), типом события и входа, опциональными Telegram-полями, `raw_payload`, статусом жизненного цикла. Уникальность входа для Telegram при заданных `telegram_chat_id` и `external_message_id` (частичный уникальный индекс).

### document_chunks

Метаданные чанков версии документа: индекс, превью текста, токены, **`chroma_collection`**, **`chroma_id`**, `metadata`. Уникальность `(document_version_id, chunk_index)` и `(chroma_collection, chroma_id)`.

### processing_logs

События стадий обработки по **`execution_id`** и опционально **`intake_event_id`**: `stage`, `status`, `details`, `error_text`, `attempt`.

### outbox

Исходящие сообщения: канал, получатель, тип сообщения, тело, статус доставки, попытки, ошибки.

### generated_assets

Сгенерированные ресурсы (тип, провайдер, модель, путь/URL, статус, `metadata`).

### admin_audit_log

Действия администратора: `action`, цель (`target_type`, `target_id`), `details`, опционально **`execution_id`**.

### usage_metrics

Агрегаты по дате и имени метрики с измерениями `dimensions` (JSONB); уникальность `(metric_date, metric_name, dimensions)`.

## Функции

- **`set_updated_at()`** — триггерное обновление `updated_at` для `app_users`, `documents`, `chat_sessions`, `user_preferences`.
- **`log_processing_event(...)`** — вставка строки в `processing_logs`.

## Правило изменения схемы

1. Добавить SQL-миграцию в `database/migrations/` (последовательно по номеру).
2. Обновить итоговый **`database/schema.sql`** под состояние после всех миграций.
3. Обновить **`database/db_contract.md`**.
4. Затем менять прикладной код.

## Конфиденциальность

В контракте и документации не приводятся реальные ключи API, пароли и персональные данные пользователей.
