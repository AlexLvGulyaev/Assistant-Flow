# Engineering log: Documents — детализация чанка (layout) и audit metadata (2026-05-11)

## Цель

- Компактный UI модалки чанка (две колонки параметров, меньше вертикали у meta/header, больше места под текст).
- Выяснить, почему в консоли отображался `metadata` как `{}`, и не теряется ли поле на пути API.
- Не показывать пустой JSON как «полезные данные»; при непустом — JSON в свёрнутом `<details>`.

## Цепочка данных (аудит)

1. **PostgreSQL `document_chunks`** — колонка **`metadata`** (JSONB), не `chunk_metadata` / не `vector_metadata`.
2. **`repositories/document_repository.py`** — `insert_document_chunk(..., metadata=...)`; `list_chunks_for_version` делает `SELECT ... metadata ...` — маппинг корректен.
3. **Admin indexer** — `services/admin_knowledge_indexer.py`, `_postgres_insert_chunk_rows` → `insert_document_chunk`.
4. **Admin API** — маршруты документов отдают bundle детали; фронт читает `chunks[].metadata`.

## Root cause пустого `{}` в UI

**Причина не в UI и не в SELECT репозитория.** Индексатор при вставке строк чанка в PostgreSQL всегда передавал **`metadata={}`**, хотя у LangChain `Document` после `_attach_chroma_metadata` в `chunk.metadata` уже есть полезные ключи (document_id, version_id, source, chroma_id и т.д.).

В векторном бэкенде метаданные чанка по-прежнему пишутся; **расхождение было только между векторным хранилищем и снимком в `document_chunks.metadata`.**

## Исправление (без миграции БД, без SmartChunker / retrieval)

- В **`services/admin_knowledge_indexer.py`**: при вставке чанков в PG передаётся снимок `Document.metadata` через **`_chunk_metadata_snapshot_for_pg`** (JSON-совместимые скаляры/строки, длинные значения усечены).
- **Существующие строки** в `document_chunks` с уже записанным `{}` **не меняются сами** — нужна **переиндексация** документа (или полная), чтобы в БД появился непустой snapshot.

## UI (после правок)

- Параметры чанка: **две колонки** (`.docs-chunk-detail-kv`), пары label/value компактнее; пустые поля не рендерятся.
- Заголовок модалки: номер чанка; имя файла — в строке **Source** (меньше высоты header).
- Если `metadata` — пустой объект: одна строка **«Metadata отсутствуют (в БД пустой объект).»** с `title` пояснением про старые строки и переиндексацию; **нет** раскрываемого блока с `{}`.
- Если `metadata` непустая: **`<details>`** (по умолчанию свёрнуто) с JSON.

## Изменённые файлы (сессия)

- `frontend/admin-ui/src/pages/DocumentsPage.tsx` — сетка параметров, `ChunkDetailPair`, `isChunkMetadataEmpty`, условный metadata.
- `frontend/admin-ui/src/styles/globals.css` — стили `.docs-chunk-detail-kv*`, компактнее `.rag-chunk-modal--chunk-detail` head/title, `.docs-chunk-meta-empty`.
- `services/admin_knowledge_indexer.py` — запись непустого snapshot в `document_chunks.metadata` (см. root cause выше).

## TODO / Phase next (вне текущего scope)

- Опционально: отдельный endpoint или флаг «полный текст из vector store» для отладки (сейчас в PG preview до ~4000 символов — уже отражено в UI).
- Массовая «дозапись» metadata для старых строк без полного reindex **не делалась** (требовало бы миграции/скрипта и согласования).

## Чеклист ручной проверки

1. `cd frontend/admin-ui && npm run build`.
2. `python -m py_compile services/admin_knowledge_indexer.py`.
3. Открыть Documents → документ с чанками → детали чанка: две колонки, нет лишних пустых строк.
4. Для **старой** версии без переиндексации: строка «Metadata отсутствуют…», без `<details>` с `{}`.
5. Выполнить **переиндексацию** одного документа → открыть тот же чанк: при наличии полей в LangChain metadata — **свёрнутый** блок «Metadata (JSON)» с непустым содержимым.
