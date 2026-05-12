# Engineering log: preprocessing pipeline (Lesson 3) — Phase 1

## Workspace snapshot (start)

- `git status`: modified `PROJECT_STATE.md`; untracked `storage/` (ignored for code changes).
- Branch: `main` (ahead of origin).

## Planned touchpoints

| Area | Files (planned) |
|------|-----------------|
| New package | `services/preprocessing/**` |
| Ingestion | `services/admin_service.py` (`save_uploaded_*`, `upload_*_and_index`, logging) |
| API | `admin_api/routes/documents.py` (upload accept types, list enrichment) |
| Deps | `requirements.txt` (`beautifulsoup4`) |
| Admin UI | `frontend/admin-ui/src/pages/DocumentsPage.tsx`, `frontend/admin-ui/src/api/client.ts` (minimal) |
| Tests | `scripts/test_preprocessing_phase1_smoke.py` (optional smoke) |

## Architectural decisions

1. **Raw immutable:** raw bytes always `AssetRepository.save_bytes(..., namespace="documents")` unchanged.
2. **Canonical RAG path:** cleaned UTF-8 written to `rag_documents_dir / {stem}.txt` (always `.txt` for indexer); raw may be `.html`.
3. **Processed artifact:** `namespace="processed_documents"`, filename `{stem}.cleaned.txt` (content-type `text/plain`).
4. **No DB migration:** preprocessing diagnostics live in `processing_logs.details` and optional `item.preprocessing` on `/api/documents` via log merge (filename / indexed_target keys).
5. **Alternatives rejected:** LangChain loaders (explicit avoid); async workers (out of scope Phase 1); new SQL tables (out of scope).

## Regression risks

- Upload previously `.txt` only → now `.html` allowed; `.txt` path still works (passthrough + normalize).
- Indexer still receives a `.txt` path; `load_and_split_file` unchanged.
- Log `details.filename` compatibility: add `indexed_target_filename` + keep `filename` as original where useful for timeline.

## Post-implementation checklist

See final section after code lands: changed files, lifecycle diagram, Phase 2 notes.

---

## Workspace snapshot (end of Phase 1 wiring)

- `git status`: modified `PROJECT_STATE.md`, `admin_api/routes/documents.py`, `frontend/admin-ui/src/api/client.ts`, `DocumentsPage.tsx`, `globals.css`, `requirements.txt`, `services/admin_service.py`; untracked `docs/cursor_sessions/…engineering-log.md`, `scripts/test_preprocessing_phase1_smoke.py`, `services/preprocessing/`, `storage/` (runtime, not committed).

## Execution summary

### Ingestion / lifecycle (canonical)

1. **Upload** (`POST /api/documents/upload` → `AdminService.upload_txt_and_index` → `save_uploaded_document`).
2. **Raw asset:** `AssetRepository.save_bytes(..., namespace="documents", filename=<original>)` — bytes unchanged.
3. **Preprocessing:** `PreprocessingService.run(raw_bytes, original_filename=…)`  
   - `.txt`: `TxtExtractor` → `clean_extracted_text` → `normalize_text`  
   - `.html`/`.htm`: `HtmlExtractor` (BeautifulSoup, strip `script`/`style`/`nav`/`footer`/`header`) → `clean_html_extracted_text` → `normalize_text`
4. **Processed artifact:** `AssetRepository.save_bytes(..., namespace="processed_documents", filename="{stem}.cleaned.txt")`.
5. **Canonical RAG file:** `{rag_documents_dir}/{stem}.txt` — same UTF-8 as cleaned artifact; **indexer / chunking read this path only** (not raw HTML).
6. **Indexing:** `AdminKnowledgeIndexer.index_single_file(dest)` unchanged in contract (still a `.txt` path).
7. **Observability:** `processing_logs` row `stage=admin_document_uploaded` with `details` containing `preprocessing` (from `PreprocessingDiagnostics.to_log_dict()`), `size_bytes`, `cleaned_size_bytes`, `indexed_target_filename`, `original_upload_filename`, asset refs, compatibility path.

**Retrieval flow change:** chunking source is explicitly the **cleaned** UTF-8 at `RAG_DOCUMENTS_DIR/{stem}.txt`, not the raw upload. Vector metadata / DB rows still refer to indexed filename (`{stem}.txt`); raw name is only in logs + UI merge.

### List API enrichment (`GET /api/documents`)

- `timeline_by_file` keys on both `indexed_target_filename` and legacy `filename` in log `details`.
- `preprocess_by_indexed` merges the **newest** matching `admin_document_uploaded` row per key (logs are `ORDER BY created_at DESC`, first write wins).
- `_preprocessing_public_from_upload` exposes a small, UI-safe dict: `status`, formats, byte sizes, `removed_line_count`, optional previews, error.

### Admin UI (minimal)

- File input accepts `.txt`, `.html`, `.htm`.
- List rows: preprocessing line (status, format, raw→cleaned sizes, removed-line heuristic); separate line when `original_upload_filename` ≠ indexed `filename`.
- Document summary: indexed filename, optional original upload name, preprocessing status, sizes, optional before/after preview blocks (from logs).
- Upload success hint includes raw→cleaned sizes when the API returns them.

### New / touched files (code)

| Path | Role |
|------|------|
| `services/preprocessing/__init__.py` | Exports `PreprocessingService`, `run_preprocessing` |
| `services/preprocessing/preprocessing_service.py` | Pipeline orchestration + `PreprocessingDiagnostics` |
| `services/preprocessing/extractors/{base,txt,html}_extractor.py` | TXT passthrough; HTML via BS4 |
| `services/preprocessing/cleaners/{text,html}_cleaner.py` | Conservative line/whitespace cleanup |
| `services/preprocessing/normalizers/text_normalizer.py` | NFC, LF, paragraph spacing, trim |
| `services/admin_service.py` | `save_uploaded_document`, wrappers, upload log shape |
| `admin_api/routes/documents.py` | List merge + `_preprocessing_public_from_upload` |
| `requirements.txt` | `beautifulsoup4>=4.12.0` |
| `scripts/test_preprocessing_phase1_smoke.py` | Offline smoke (HTML noise removed, TXT path) |
| `frontend/admin-ui/src/api/client.ts` | `DocumentPreprocessingPublic`, `DocumentItem.preprocessing`, `UploadDocumentResponse` |
| `frontend/admin-ui/src/pages/DocumentsPage.tsx` | Accept types, list + summary + previews |
| `frontend/admin-ui/src/styles/globals.css` | Compact preprocessing preview grid |

`PROJECT_STATE.md` was already dirty before this session; not rewritten as part of Phase 1 code.

### Example: raw HTML → cleaned (conceptual)

**Raw fragment:** `<nav>Home</nav><p>Policy text.</p><footer>© 2026 ACME</footer>`  
**After extract:** newlines + “Policy text.” body text without nav/footer tags.  
**After clean/normalize:** repeated junk lines removed conservatively; stable spacing; NFC unicode.

### Phase 1 limitations

- **Formats:** only `.txt`, `.html`, `.htm` — no PDF/DOCX/OCR.
- **Encoding:** HTML decoded as UTF-8 with `errors="replace"` (no charset sniffing).
- **`removed_line_count`:** coarse metric (line count delta extract → final), not a precise “deleted junk lines” counter.
- **Reindex:** `reindex_document_file` still reads the on-disk path from DB / `RAG_DOCUMENTS_DIR`; it does **not** re-run preprocessing from raw assets (Phase 2 could add “rebuild cleaned from raw”).
- **No async workers** for preprocessing; upload request does full pipeline synchronously (extra latency vs raw-only upload).

### Regression / operational notes

- **Latency:** upload + index does decode, BS4, I/O to two asset namespaces + compatibility `.txt` write — expect slightly higher p95 vs old “save bytes → index”.
- **Storage:** each upload adds raw + cleaned artifact + duplicate bytes in `rag_documents_dir` (by design for compatibility).
- **Retrieval quality:** HTML RAG no longer embeds boilerplate from stripped tags; risk of over-aggressive `text_cleaner` remains mitigated by conservative patterns only.

### Phase 2 recommendations

1. **Charset / encoding detection** for HTML and non‑UTF8 `.txt`.
2. **PDF/DOCX** extractors behind the same `PreprocessingService` façade.
3. **Re-preprocess from raw** on reindex or version bump (read `documents` asset by ref from metadata).
4. **Structured preprocessing metadata** in DB (still optional) if log merge becomes too heavy.
5. **Async job** for large files + progress UI.
6. **Golden-file tests** for `text_cleaner` / HTML samples to guard regression on retrieval-critical corpora.

---

## Legacy audit: `legacy/PEr03_source` vs `services/preprocessing` (alignment)

**Scope:** Сравнение учебного дерева `legacy/PEr03_source` (Lesson 3 demo: `loader/*.py`, `ingest.py`) с продакшен-слоем AF. Проверено содержимое файлов, не только структура каталогов.

**Интеграция в AF:** Ни один модуль под `services/` или `admin_api/` **не импортирует** `PEr03_source` (`rg` по репозиторию). Параллельного ingestion pipeline в рантайме нет — legacy остаётся архивом для аудита.

### 1. Что найдено в legacy

| Модуль | Поведение (суть) |
|--------|------------------|
| `loader/html_loader.py` | BS4 `html.parser`; удаляет только `script`, `style`; `soup.get_text()` **без** separator → сильнее «склеивает» блоки; `clean_html_text`: построчный strip, удаление **всех** пустых строк, затем глобально `re.sub(r' +', ' ', text)` и `\n{3,}` → `\n\n`. |
| `loader/txt_loader.py` | UTF-8 read; `clean_text`: сначала глобальный `r' +'` и `\n{3,}` на всём тексте, потом strip строк и удаление пустых строк. |
| `loader/chunker.py` | Два режима: `chunk_text` (скользящее окно по символам, default 500/100) и `chunk_text_smart` (иерархия разделителей `\n\n`, `\n`, `. `, … с рекурсией); `create_chunks_with_metadata` добавляет `chunk_id`, `total_chunks`, `char_count`, `type`. |
| `html_loader.extract_metadata_from_html` | `title`, `meta name=description` — отдельно от основного текста. |
| `ingest.py` | Склейка load → chunk → Chroma в одном скрипте (учебная точка входа). |

### 2. Comparison matrix

| Component | Legacy (`PEr03_source`) | Current (`services/preprocessing` + indexing) | Recommendation |
|-----------|------------------------|-------------------------------------------------|----------------|
| **HTML extractor** | BS4; только `script`/`style`; `get_text()` без разделителя | BS4; `script`/`style`/`nav`/`footer`/`header`; `get_text("\n")` для сохранения абзацев | **Keep current.** Legacy слабее по boilerplate и хуже сохраняет структуру. |
| **TXT “loader”** | Файл + `clean_text` в одном шаге | `TxtExtractor` decode + line cleaner + `normalize_text` | **Keep current contract** (bytes in / str out для pipeline). |
| **Whitespace / blank lines** | Глобальный `re.sub(r' +', ' ', text)` после склейки строк; все пустые строки убраны | Построчно: табы→пробел, дубликаты строк, junk-line regex; `normalize_text`: rstrip строк, NFC, `\n{3,}`→`\n\n` | **Keep current.** Глобальный collapse пробелов в legacy расходится с retrieval-oriented «сохранить абзацы» и с консервативностью AF. |
| **Junk / footer heuristics** | Нет отдельных паттернов (кроме удаления тегов) | `_JUNK_LINE_RES` + короткие nav-crumbs в `text_cleaner.py` | **Keep current;** не переносить «тихий» legacy без эвристик — иначе регресс по шуму в HTML. |
| **Unicode normalization** | Нет NFC | NFC в `normalize_text` | **Keep current.** |
| **Metadata extraction** | `title`, `meta description` из HTML | Нет в Phase 1 preprocessing | **Optional later:** при необходимости вынести в отдельный helper (только metadata в лог/JSON), не смешивать с очисткой текста для RAG. |
| **Chunkers** | `loader/chunker.py`: фиксированные 500/100, separator-smart | `services/chunking/smart_chunker.py`: `AppConfig` (`rag_chunk_size` / overlap), paragraph units `\n\s*\n+`, предложения, overlap на границах чанков | **Single canonical chunker = SmartChunker.** Legacy chunker **не дублируется в коде** AF; идея «paragraph-first» уже осознанно переработана (см. комментарий в `smart_chunker.py` про PEr03/PEr08). |
| **Ingestion entry** | `ingest.py` monolith | `AdminService` + `AdminKnowledgeIndexer` + AssetRepository | **Do not revive** legacy entrypoint внутри AF. |

### 3. Что совпадает / что дублируется концептуально

- **Совпадает по смыслу:** оба стека используют BeautifulSoup для HTML; оба нормализуют множественные переводы строк (legacy `\n{3,}`; AF то же в `normalize_text` после более богатой постобработки).
- **Дублирование кода:** **нет** общих копий между `legacy/PEr03_source` и `services/preprocessing`. Единственное «двойное место» в AF — **разные пути чтения файла до чанков**: admin upload → уже очищенный `.txt` → `SmartChunker`; для **PDF** по-прежнему `rag_document_loader.load_and_split_file` (PyPDFLoader + тот же `SmartChunker`) **без** preprocessing-слоя — это не конфликт нормализации с HTML-pipeline, а **разный формат**, до выравнивания PDF в Phase 2.

### 4. Что переиспользовано ранее (идеи, не копипаста)

- В `smart_chunker.py` зафиксировано: идеи paragraph-aware chunking **адаптированы** из legacy PEr03/PEr08 без переноса монолитов — это и есть контролируемое reuse.

### 5. Что намеренно НЕ переносится

- `soup.get_text()` без аргумента-separator (ухудшение для RAG).
- Глобальный `re.sub(r' +', ' ', text)` на целом документе после извлечения (ломает предсказуемость относительно построчных эвристик AF).
- Удаление только `script`/`style` без `nav`/`footer`/`header`.
- `loader/chunker.py` как второй chunker в проде (двойная семантика границ чанков).
- Склейка ingest «load+chunk+vector» в стиле `ingest.py` — противоречит AssetRepository + lifecycle + observability AF.

### 6. Canonical preprocessing contracts (AF)

1. **Граница слоя:** до чанкинга; на вход chunker всегда **строка** в каноническом виде UTF-8 NFC для путей, идущих через upload-preprocess.
2. **HTML:** извлечение с сохранением переводов строк между блоками; структурный шум (`script`, `style`, `nav`, `footer`, `header`) вырезается в DOM, не regex’ом по сырому HTML.
3. **Очистка текста:** построчные операции + консервативные full-line regex; без lowercasing всего документа.
4. **Чанкинг:** только `SmartChunker` + параметры из `AppConfig`; legacy separator-tree **не** является альтернативным стандартом.

### 7. Риски скрытой divergence (mitigation)

| Риск | Статус |
|------|--------|
| Два chunker в проде | **Снят:** второй chunker только в `legacy/`, не wired. |
| Две нормализации пробелов | **Разведены:** preprocessing (строки + NFC) vs chunker (`text.strip()` перед `_build_raw_chunks` — только in-memory перед нарезкой, без записи на диск). |
| Разный HTML text | **Ожидаемо:** upload HTML проходит AF pipeline; сырой HTML с диска в corpus без preprocess не поддерживается как `.html` в indexer (канон — `.txt`). |

### 8. Вывод

Legacy Lesson 3 полезен как **исторический эталон учебной простоты**, но **не** как drop-in замена текущего preprocessing: текущий слой **строже по структуре HTML**, **богаче по очистке шума** и **явно отделён** от chunking (`SmartChunker`). Массовый rewrite не требуется; единственный осмысленный перенос на будущее — **опциональный** helper извлечения HTML metadata (title/description) в metadata JSON **без** изменения cleaned-текста для эмбеддингов.

---

## Corrective pass: compatibility path + upload pipeline observability

### Root cause (отсутствие ``/app/data/documents/*.txt``)

1. **Конфиг vs mount:** `RAG_DOCUMENTS_DIR` по умолчанию относительный (`data/documents`); в Docker `WORKDIR=/app` → запись в ``/app/data/documents`` **если** только этот путь смонтирован на хост (см. `docker-compose.portfolio.yml`: `./data/documents:/app/data/documents`).
2. **Расхождение путей:** если в `.env` задан **другой** абсолютный или относительный `RAG_DOCUMENTS_DIR` (не тот том, что смотрит оператор в ``/app/data/documents``), cleaned ``.txt`` оказывался **вне** ожидаемого bind-mount — в UI «файла нет», хотя индексация могла читать корректный `dest` внутри контейнера admin-api.
3. **Исправление:** после записи в primary `_resolve_dir(config.rag_documents_dir)` добавлена **зеркальная** запись того же байтов в дополнительные корни:
   - каталог из ``RAG_DOCUMENTS_COMPATIBILITY_DIR`` (если задан и отличается от primary);
   - ``/app/data/documents``, если он существует и отличается от primary.

### Фактические пути (контракт)

| Компонент | Путь |
|-----------|------|
| **admin-api / assistant-flow** (Python) | `RAG_DOCUMENTS_DIR` → `_resolve_dir` = `_PROJECT_ROOT / data/documents` в контейнере обычно ``/app/data/documents`` при дефолтном env. |
| **Indexer** (`AdminKnowledgeIndexer`) | Читает тот же `dest`, который возвращает `save_uploaded_document` (primary под `rag_documents_dir`). |
| **Assets** | `ASSET_STORAGE_DIR` / `storage/assets/documents/*` (raw), `.../processed_documents/*.cleaned.txt`. |
| **Compatibility mirror** | Список путей в логе ``document_compatibility_file_written`` → ``compatibility_paths_written``. |

### Новые machine stages (processing_logs)

| Stage | Когда |
|-------|--------|
| `admin_document_uploaded_raw` | После сохранения raw в AssetRepository |
| `document_preprocessing_started` | Перед `PreprocessingService.run` |
| `document_preprocessing_done` / `document_preprocessing_error` | Успех / исключение preprocessing |
| `document_processed_artifact_saved` | После `processed_documents/{stem}.cleaned.txt` |
| `document_compatibility_file_written` | После записи primary + mirror ``{stem}.txt`` |
| `document_indexing_started` | Перед `index_single_file` |
| `document_indexing_done` / `document_indexing_error` | Результат индексации |
| `document_upload_pipeline_done` | Финал pipeline (success или error), полный snapshot в `details` |

Устаревший одиночный лог `admin_document_uploaded` **больше не пишется** новым кодом; UI/API мержат preprocessing из `document_upload_pipeline_done` с fallback на старые строки в БД.

### Общие поля `details`

`upload_id` / `execution_id`, `original_upload_filename`, `indexed_target_filename`, `filename` / `source_filename` (для SQL timeline), `raw_asset_ref`, `processed_asset_ref` / `cleaned_asset_ref`, `compatibility_path`, `compatibility_paths_written`, `preprocessing` (включая `status`), `original_size_bytes`, `cleaned_size_bytes`, `extractor`, `cleaner`, `normalizer`, `rag_documents_dir_resolved`.

### Changed files (corrective pass)

- `services/admin_service.py` — mirror write helpers, пошаговые логи, `upload_txt_and_index` индексация-логи, `SUMMARY_LIFECYCLE_STAGE_ORDER`
- `repositories/processing_logs_repository.py` — расширен поиск timeline по `indexed_target_filename` / `original_upload_filename`
- `admin_api/routes/documents.py` — timeline stages, preprocess merge с `document_upload_pipeline_done`, `cleaned_bytes` fallback
- `services/preprocessing/preprocessing_service.py` — поле `status` в `to_log_dict`
- `frontend/admin-ui/src/utils/operationalLabels.ts` — RU-подписи стадий
- `frontend/admin-ui/src/pages/TextPage.tsx` — фильтр modality для `document_*` pipeline
- `frontend/admin-ui/src/pages/SummaryPage.tsx` — счётчик загрузок по новому stage
- `frontend/admin-ui/src/api/client.ts` — поля ответа upload
- `admin_ui/app.py` — RU-лейблы и badge-логика для новых стадий
- `.env.example` — комментарий `RAG_DOCUMENTS_COMPATIBILITY_DIR`

### Test commands

```bash
cd /opt/assistant-flow
python3 -m py_compile services/admin_service.py admin_api/routes/documents.py repositories/processing_logs_repository.py
python3 scripts/test_preprocessing_phase1_smoke.py
```

### Manual verification checklist

1. Upload `.html` / `.txt` через Admin UI или `POST /api/documents/upload`.
2. В контейнере admin-api: `ls -la /app/data/documents/*.txt` — появился `{stem}.txt` (или см. `compatibility_paths_written` в логе `document_compatibility_file_written`).
3. `ls storage/assets/documents/*` и `storage/assets/processed_documents/*.cleaned.txt` на хосте.
4. Documents UI: preprocessing, размеры, превью (если есть в логе).
5. Logs / lifecycle: видны стадии от raw до `document_upload_pipeline_done`, без «безымянного» одного шага.

---

## Corrective pass: Summary «Этапы обработки» + Logs modality «Документ»

### Root cause — Summary

Блок **C. Этапы обработки** строится только из стадий, перечисленных в `SUMMARY_LIFECYCLE_STAGE_ORDER`: для каждой стадии берётся счётчик из `get_dashboard_stats().by_stage` (агрегат `count_by_stage_since`). В список попали только `admin_document_uploaded` и `document_upload_pipeline_done`; **промежуточные** `document_*` / `admin_document_uploaded_raw` **не были в tuple** — их счётчики не отображались. Плюс в UI в `<dt>` выводился **сырой** machine `stage`, без `stageToActionRu`.

### Root cause — Logs «Прочие»

`infer_modality_route` в `admin_api/deps.py` не знал про document pipeline и возвращал `"other"`, пока в `pickRoute` (LogsPage) не сработал fallback по `details.route`. У событий upload/preprocess поле `route` пустое → сессия попадала в **«прочее»**.

### Исправления

1. **`SUMMARY_LIFECYCLE_STAGE_ORDER`** — добавлены все перечисленные пользователем document stages (в хронологическом порядке вокруг pipeline), плюс legacy `admin_document_uploaded`.
2. **`count_routes_since`** — в SQL `CASE` добавлен bucket `'document'` для `stage LIKE 'admin_document%'` и `stage ~ '^document_(upload|preprocessing|processed|compatibility|indexing)_'`.
3. **`get_dashboard_stats` / `get_summary_payload`** — ключ `by_route.document`, в ответе summary `routes.documents`; `other_unknown` уменьшается за счёт document-сессий.
4. **`infer_modality_route` / `infer_modality`** — ранний возврат `"document"` для admin/document lifecycle stages; `modality` для логов = `document`.
5. **React:** `SummaryPage` — русские подписи этапов через `stageToActionRu`, строка **«Документ»** в блоке маршрутов; `LogsPage` — фильтр `document`, `pickRoute` / `pickRouteKey`; `operationalLabels` — `ROUTE_LABEL_RU.document`, `NormalizedRouteKey`, алиас `documents` → `document`; `client.ts` — `SummaryRoutesBlock.documents`, комментарий modality.

### Changed files (UI/Summary modality pass)

- `services/admin_service.py` — расширен `SUMMARY_LIFECYCLE_STAGE_ORDER`, `by_route` / `routes.documents` / `other_unknown`
- `repositories/processing_logs_repository.py` — `count_routes_since` bucket `document`
- `admin_api/deps.py` — `_is_document_lifecycle_stage`, `infer_modality_route`, `infer_modality`
- `frontend/admin-ui/src/pages/SummaryPage.tsx`, `LogsPage.tsx`, `utils/operationalLabels.ts`, `api/client.ts`

### Проверка вручную

1. `/api/summary` — в `lifecycle_events` есть ненулевые строки для `document_preprocessing_*` и т.д. после upload; блок C показывает **русские** названия.
2. Logs — фильтр «документ», карточка сессии с pipeline показывает **ДОКУМЕНТ**, не «Прочее».
3. Summary B — строка «Документ» с числом сессий в document bucket.
