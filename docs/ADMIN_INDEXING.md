# Индексация базы знаний

Пользователи **не** загружают документы через Telegram. Корпус пополняет **оператор** через Admin UI или CLI.

PostgreSQL должна быть инициализирована (portfolio: [RUNBOOK.md](../RUNBOOK.md) §D, [OPERATIONS.md](OPERATIONS.md)). Без `DATABASE_URL` метаданные документов в Postgres не пишутся.

---

## Admin UI (основной путь)

1. Открыть **Документы** (`http://localhost:8080/documents` в portfolio).
2. Загрузить файлы (PDF, TXT, MD и поддерживаемые форматы — см. код preprocessing).
3. Дождаться pipeline: preprocessing → индексация → запись в векторный backend и PostgreSQL.
4. При необходимости — **Reindex** для документа (события `document_reindex_*` в lifecycle).

В списке документов отображаются (при настроенном Postgres):

- активный backend и версия документа;
- `chunk_count`, статусы индексации;
- последние события reindex / upload (из `processing_logs`).

Связь: **PostgreSQL** — метаданные и lifecycle; **Chroma / FAISS / Weaviate** — векторы. Рассинхрон возможен при ошибке после записи в векторное хранилище — см. предупреждения в логах.

### Активный backend

Переключение **Retrieval Settings** (`/retrieval`): `chroma`, `faiss`, `weaviate`. После смены может потребоваться reindex для выбранного backend.

---

## CLI (альтернатива и автоматизация)

```bash
# из корня репозитория
python scripts/admin_index_documents.py --reindex
```

| Аргумент | Назначение |
|----------|------------|
| `--reindex` | Полная пересборка коллекции (режим зависит от HTTP/local Chroma) |
| `--no-postgres` | Только векторное хранилище, без Postgres |
| `--documents-dir PATH` | Каталог вместо `RAG_DOCUMENTS_DIR` |

Поведение:

- файлы `.pdf`, `.txt`, `.md` из `data/documents/` (рекурсивно);
- без `--reindex` — **добавление** чанков (риск дубликатов при повторе тех же файлов);
- с `--reindex` — сброс коллекции Chroma (HTTP: `delete_collection`) или каталога persist (local).

### PostgreSQL

При `DATABASE_URL` создаются/обновляются `documents`, `document_versions`, `indexing_jobs`. Ошибка после успешной записи векторов, но до финализации Postgres — индекс уже содержит чанки, метаданные БД проверить вручную.

---

## Chroma: HTTP и локальный persist

Один backend используют CLI, бот (RAG) и Admin API.

| Режим | Переменные |
|--------|------------|
| HTTP | `CHROMA_USE_HTTP=true`, `CHROMA_HOST`, `CHROMA_PORT` — portfolio: `chroma:8000` внутри compose, **8001** на хосте |
| Local persist | `CHROMA_USE_HTTP=false`, `CHROMA_PERSIST_DIR` |

На Windows локальный `PersistentClient` при массовом `add()` может быть нестабилен — предпочтителен HTTP к серверной Chroma.

Удаление volume `portfolio_chroma_data` (**portfolio**) = **полная потеря** векторов до reindex.

---

## Предупреждения

- **Дубликаты чанков** — повторная индексация без `--reindex` / без очистки коллекции.
- **Потеря тома Chroma/Weaviate** — только reindex из исходных файлов в `data/documents/`.
- **Разные `CHROMA_*` у бота и CLI** — бот не увидит индекс, построенный другим клиентом.

---

## Связь с ботом

После индексации: Telegram `/mode rag` (или соответствующий режим в UI). Убедитесь, что `RAG_BACKEND` и параметры Chroma/Weaviate/FAISS согласованы между bot, Admin API и CLI.

См. также: [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md), [OPERATIONS.md](OPERATIONS.md).
