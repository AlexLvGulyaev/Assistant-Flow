# Engineering log: Preprocessing Phase 2 — PDF ingestion (2026-05-13)

## Цель

Встроить поддержку **`.pdf`** в существующий preprocessing lifecycle (raw asset → extract → clean → normalize → `.cleaned.txt` → canonical `.txt` в RAG/compatibility → тот же **SmartChunker** и индексация по **тексту**), без отдельного PDF-pipeline, без OCR и без прямого чанкинга PDF.

## Выбор экстрактора: PyMuPDF (fitz)

| Критерий | Обоснование |
|----------|-------------|
| Стабильность и скорость | Зрелая нативная библиотека, широко используется в продакшене |
| Макет | `get_text("text")` даёт поток текста с учётом порядка чтения лучше, чем «сырой» парсинг без слоя извлечения |
| Контракт | Реализован отдельный класс **`PdfExtractor`** в `services/preprocessing/extractors/`, общий контракт **`BaseExtractor.extract(bytes) -> str`** |

**Не используется** в этом этапе: LangChain loaders для PDF в upload-пути (индексатор по-прежнему читает итоговый **`.txt`** через существующий путь).

## Контракт извлечения

- **Вход:** `raw: bytes`, имя файла с суффиксом `.pdf`.
- **Выход:** одна UTF-8 строка: страницы объединены разделителем `\n\n---\n\n`, внутри страницы — постраничный текст после лёгкой очистки.
- **Границы страниц:** явный разделитель между страницами; не один монолит без маркеров.
- **Дальше:** те же **`clean_extracted_text`** и **`normalize_text`**, что и для TXT (HTML-поток не затронут).

### Поля observability (`PreprocessingDiagnostics.to_log_dict()` / блок `preprocessing` в логах)

- `extractor`: **`pdf_pymupdf`** (только для PDF).
- `page_count`: число страниц документа.
- `extracted_characters`: длина строки после извлечения (до финальной нормализации; дублирует смысл `extracted_char_len`).
- `cleaned_size_bytes`: размер финальной UTF-8 строки после pipeline (байты).

Плюс уже существующие поля: `original_format`, `original_bytes`, `cleaned_char_len`, `removed_line_count`, превью и т.д.

## Ограничения PDF (известные)

- Текст только **встроенный** в PDF; отсканированные страницы без текстового слоя дадут пустой или неполный текст (**OCR вне scope**).
- Сложные макеты (колонки, таблицы) могут давать нелинейный порядок строк относительно «человеческого» чтения.
- Разделитель `---` между страницами попадает в индексируемый текст (намеренно, как маркер границы).

## Риски

- Зависимость **PyMuPDF** обязательна в окружении API/воркеров, иначе при upload `.pdf` будет ошибка с понятным сообщением.
- Лёгкие эвристики удаления строк вида «Page N / M» могут в теории удалить редкую легитимную строку; правила намеренно узкие.

## Влияние на retrieval

- В векторный индекс попадает **нормализованный текст**, как и для TXT/HTML upload.
- Чанкер и embedding не менялись; меняется только источник текста до canonical `.txt`.
- Семантика RAG: качество ответов по PDF зависит от качества извлечённого текста (см. ограничения выше).

## Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `requirements.txt` | Зависимость `PyMuPDF>=1.24.0` |
| `services/preprocessing/extractors/pdf_extractor.py` | **Новый** экстрактор PyMuPDF + минимальная постраничная очистка |
| `services/preprocessing/preprocessing_service.py` | Ветка `.pdf`, расширен `Format`, диагностика + `to_log_dict()` |
| `services/admin_service.py` | Upload `.pdf`, MIME, имена компонентов пайплайна, `failure_diag` для `pdf` |
| `admin_api/routes/documents.py` | Проброс в публичный preprocessing: `extractor`, `page_count`, `extracted_characters` |
| `frontend/admin-ui/src/pages/DocumentsPage.tsx` | `accept` + краткий вывод страниц/экстрактора |
| `frontend/admin-ui/src/api/client.ts` | Поля в `DocumentPreprocessingPublic` |
| `scripts/test_preprocessing_phase2_pdf_smoke.py` | **Новый** smoke (extract + файл `.txt` + SmartChunker) |
| `scripts/test_preprocessing_phase1_smoke.py` | Проверка `cleaned_size_bytes` |

## Чеклист проверки

1. `pip install -r requirements.txt` (в т.ч. PyMuPDF).
2. `python3 scripts/test_preprocessing_phase1_smoke.py` — регресс TXT/HTML.
3. `python3 scripts/test_preprocessing_phase2_pdf_smoke.py` — PDF + chunking.
4. Admin UI: загрузка `.pdf`, в логах стадии `document_preprocessing_*` с `extractor=pdf_pymupdf`, `page_count`, `cleaned_size_bytes`.
5. Индексация: в каталоге RAG появляется `{stem}.txt`; поиск по содержимому PDF-smoke (при поднятом бэкенде).

## Намеренно не сделано

- Отдельный PDF-only pipeline, прямой чанкинг PDF, embedding сырых PDF.
- OCR, LangChain PDF loader в upload-цепочке, миграции БД, переписывание архитектуры preprocessing.
