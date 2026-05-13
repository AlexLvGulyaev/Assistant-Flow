# Engineering log: Document Editing v1 (canonical indexed text)

**Дата:** 2026-05-12  
**Область:** Assistant Flow — operational правка текста для retrieval после preprocessing.

## Архитектурное решение

Редактируется **итоговый canonical indexed текст** (файл `.txt` / `.md` на диске, тот же поток, что идёт в chunking и индекс), а не:

- сырой upload (assets);
- промежуточные артефакты preprocessing (raw / cleaned pipeline stages).

Обоснование:

- Агрессивный автоматический cleanup рискует повредить **семантику retrieval**; часть шума (footer, навигация, артефакты вёрстки PDF) лучше убирать **контролируемо** оператором.
- Источник истины для embedding/chunking — именно canonical файл после pipeline; правка на этом уровне гарантирует согласованность «что видит чанкер» и «что правит человек».

## Retrieval и версионирование

- После сохранения: `_write_cleaned_rag_txt_everywhere` обновляет canonical и compatibility-копии; `reindex_document_file(..., reindex_log_kind="document")` пересобирает индекс.
- Новая строка в `document_versions` создаётся внутри существующего indexer-потока при смене hash (архитектура versioning **не переписывалась**).
- Старые версии остаются в истории; retrieval использует активную версию после успешной индексации.

## Наблюдаемость (lifecycle)

Стадии:

- `document_edit_started` / `document_edit_saved`
- `document_reindex_started` / `document_reindex_done` / `document_reindex_error`

В `details` (где применимо): `previous_version`, `new_version` / `expected_new_version`, `editor_source`, `edited_characters`, `diff_size`, плюс идентификаторы файла/документа.

Префиксы учтены в `admin_api/deps.py`, whitelist таймлайна документов, SQL bucket `document` в `processing_logs_repository`, подписи в `operationalLabels.ts` и зеркально в `admin_ui/app.py`.

## API и UI

- `GET /api/documents/{id}/detail?full_canonical_text=true` — опционально возвращает `canonical_text_full` для редактора (лимит размера согласован с сохранением).
- `POST /api/documents/{id}/edit-text` — тело `{ "text", "editor_source" }` → `save_canonical_document_text_edit`.
- Documents (React): кнопка «Редактировать» только при **активной выбранной версии** и наличии предпросмотра; компактная высота блока предпросмотра **не увеличивалась**; textarea + «Сохранить как новую версию» / «Отмена».

## PDF cleanup (дополнительный консервативный pass)

В `pdf_cleaner.py`: построчные эвристики для header/footer boilerplate, расширенные крошки, декоративные строки — без lowercasing документа и без semantic rewrite.

## Изменённые файлы

- `services/admin_service.py` — `include_full_canonical_text`, поле `canonical_text_full` в bundle.
- `admin_api/routes/documents.py` — query `full_canonical_text`, `POST .../edit-text`, код ответа 413 для слишком большого файла.
- `frontend/admin-ui/src/api/client.ts` — опции `fetchDocumentDetail`, `postDocumentTextEdit`, типы.
- `frontend/admin-ui/src/pages/DocumentsPage.tsx` — UI редактирования.
- `frontend/admin-ui/src/styles/globals.css` — layout предпросмотра/textarea.
- `frontend/admin-ui/src/utils/operationalLabels.ts`, `admin_ui/app.py` — подписи стадий.
- `frontend/admin-ui/src/pages/TextPage.tsx`, `repositories/processing_logs_repository.py` — маршрутизация/агрегация `document_edit_*` / `document_reindex_*`.
- `services/preprocessing/cleaners/pdf_cleaner.py`, `scripts/test_preprocessing_phase2_pdf_smoke.py`.

## Чеклист ручной проверки

1. Документ в статусе indexed, активная версия выбрана в UI — виден предпросмотр, кнопка «Редактировать» доступна.
2. При просмотре **неактивной** версии кнопка не показывается (правка только canonical на диске = активный поток).
3. «Редактировать» подгружает полный текст (для файла > лимита предпросмотра — полный объём через query).
4. «Сохранить как новую версию» → в логах появляются `document_edit_*` и `document_reindex_*`, растёт номер версии, обновляются чанки.
5. «Отмена» возвращает компактный detail без удержания полного текста в состоянии после повторной загрузки.
6. Ошибка reindex отражается как `document_reindex_error`; текст на диске уже перезаписан — оператор проверяет целостность и при необходимости откатывает из истории версий вне scope этой задачи.

## Ограничения (намеренно не делалось)

Collaborative editing, markdown/WYSIWYG, правка чанков напрямую, правка raw assets, миграции БД, смена контрактов SmartChunker, смена архитектуры retrieval backend.
