# Engineering log: Documents UI polish — inline actions, viewer, chunk details

**Дата:** 2026-05-13

## Корневая причина перегрузки UX

- В карточке документа использовались **вторичные «кнопки»** (`docs-action-btn--secondary`), визуально конкурирующие с основными операциями консоли.
- **Правый full-height drawer** давал ощущение «пустого» takeover: текстовая зона не заполняла панель, при этом для RAW использовался **усечённый** `preview_raw` из логов, а не полный текст фазы extract.

## Архитектура viewer (итог)

Переход на **тот же паттерн, что и RAG «полный текст»**:

- контейнер: `rag-chunk-modal-backdrop` + модификатор **`rag-chunk-modal-backdrop--light`** (слабое затемнение вместо агрессивного `rgba(0,0,0,0.48)` для сценария Documents);
- панель: `rag-chunk-modal` + **`rag-chunk-modal--document`** (~72vw / 72vh max, не fullscreen);
- редактирование canonical: **`rag-chunk-modal__textarea`** + footer с `rag-chunk-modal__done` и **`inline-action-link`** для «Отмена».

RAG-страница по-прежнему использует исходный backdrop без `--light` — поведение не ломаем.

## Полный RAW text

**Путь данных:**

1. В `processing_logs` в событиях `document_upload_pipeline_done` / `admin_document_uploaded` в `details` есть **`raw_asset_ref`** и **`original_upload_filename`**.
2. Endpoint `GET /api/documents/{id}/detail?full_preprocessing_raw=true` вызывает `get_document_detail_bundle(..., include_full_preprocessing_raw=True)`:
   - поиск последнего подходящего лога в таймлайне (лимит выборки логов по файлу увеличен до **200**);
   - чтение байт через `AssetRepository.read_bytes(relative_path)`;
   - восстановление той же строки, что и для `preview_raw` в diagnostics, но **без усечения**: новый метод **`PreprocessingService.raw_preview_full_text`** (эквивалент фазы перед финальной нормализацией, согласовано с текущим pipeline для txt/html/pdf).

Ограничение размера: **~12M символов**; при превышении — `preprocessing_raw_full_error` в ответе (HTTP 500 с `detail` как у других load_failed, при необходимости можно вынести в 413 аналогично canonical).

## Chunk details в Documents

**Источник данных:** строки `document_chunks` (PostgreSQL), поля из `list_chunks_for_version` + новый **`id`** в SELECT (отдаётся как **`chunk_id`** в JSON для UI).

**Полный текст чанка:** в БД хранится только **`chunk_text_preview`** (при индексации обрезка **до 4000** символов в `admin_knowledge_indexer`). В модалке:

- показывается `chunk_text_preview` как основной текст;
- если длина **≥ 4000**, выводится пояснение, что это preview в Postgres, а не «выдуманный score» и не полный текст из вектора;
- **retrieval score / distance не показываются** (это не результат retrieval).

**Metadata:** JSON в `<details>` (по умолчанию свёрнуто).

## Общий стиль action links

Введён класс **`.inline-action-link`**, стили **объединены** с `.rag-chunk-card__fulltext-cta` (одинаковые hover/focus). В Documents для RAW / canonical / chunk details используются **нижний регистр подписей** («открыть RAW», «показать детали») в духе RAG.

Вспомогательный класс: **`.docs-modal-head-actions`** — выравнивание inline-link + кнопка закрытия в шапке текстового модала.

## Изменённые файлы

- `services/preprocessing/preprocessing_service.py` — `raw_preview_full_text`.
- `services/admin_service.py` — `include_full_preprocessing_raw`, разбор логов, поля ответа, лимит логов 200.
- `repositories/document_repository.py` — `id` в `list_chunks_for_version` → `chunk_id` в сериализации bundle.
- `admin_api/routes/documents.py` — query `full_preprocessing_raw`.
- `frontend/admin-ui/src/api/client.ts` — опции и поля ответа.
- `frontend/admin-ui/src/styles/globals.css` — `inline-action-link`, light backdrop, `--document` / `--chunk-detail` модалки, textarea, исправления CSS, стили chunk meta, `docs-chunk-card__head`.
- `frontend/admin-ui/src/pages/DocumentsPage.tsx` — inline actions, модал вместо drawer, chunk modal, fetch полного RAW.

## Чеклист ручной проверки

1. Карточка: действия выглядят как **ссылки**, без крупных secondary-кнопок.
2. «открыть RAW» → компактный modal, **полный** текст (не 480-символьный preview); при отсутствии `raw_asset_ref` в логах — понятное сообщение в hint.
3. «открыть документ» / «редактировать» → тот же размер modal, полный canonical; сохранение и reindex без регрессий.
4. У чанка «показать детали» → поля meta + текст + collapsible JSON; нет score.
5. RAG: модал полного текста чанка открывается как раньше.
6. Escape: сначала закрывается chunk modal, затем текстовый modal.

## Намеренно не делалось

Миграции БД, правка raw assets, правка чанков в индексе, изменение retrieval backend / SmartChunker / семантики версий.
