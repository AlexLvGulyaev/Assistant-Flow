# Сессия: OCR / vision route в operational observability и Admin UI

Дата: 2026-05-11

## Prompt

OCR route уже работает в Telegram: фото → `vision_ocr` → распознанный текст → ответ.
Нужно исправить UX/observability в Admin UI/операционных логах:
- stage имена не должны быть «Нестандартный этап»;
- корректные подписи в execution summary;
- заполнить карточки «Что спросил пользователь» и «Что ответила система» (не пусто/N/A);
- OCR должен отображаться в modality «Текст»;
- зафиксировать русские соглашения по lifecycle stage names в `PROJECT_STATE.md`.

## Что было найдено в текущих OCR logs

1. В lifecycle/processing_logs этапы OCR (`image_received`, `ocr_started`, `ocr_done`, `ocr_error`, `processing_done`) не имели маппинга stage→RU в Admin UI → поэтому отображались fallback’ом.
2. `intake_received` и `processing_done` события для OCR не содержали ключи, которые Admin UI использует для:
   - пользовательского инпута (`user_text` / `query_preview`);
   - системного output (`answer_text` / `output_text` / `answer_preview`).
   Поэтому «Что спросил пользователь» был пустой/«—», а «Что ответила система» было N/A.
3. В React Text modality фильтрация считала `image_received` чужим этапом (через `stage`-префикс `image_`), из-за чего OCR с текстовым output не попадал в страницу Text.

## Изменённые machine stage names (реальные)

- `image_received`
- `ocr_started`
- `ocr_done`
- `ocr_error`
- `ocr_response_sent` (добавлен)
- `processing_done` (спец-лейбл для `route=vision_ocr`)

## Changed files

- `interfaces/telegram_bot.py` — payload hygiene для OCR:
  - `user_text`, `query_preview`, `answer_text` (preview), `recognized_text_preview`, `recognized_text_length`,
  - `route/downstream_route/mode` + `latency_ms`,
  - добавлен stage `ocr_response_sent`.
- `frontend/admin-ui/src/utils/operationalLabels.ts` — маппинг OCR stage→RU, alias `vision_ocr` → `text`, спец-лейбл `processing_done` для OCR.
- `frontend/admin-ui/src/pages/TextPage.tsx` — OCR включён в Text modality:
  - разрешён `image_received` stage для OCR,
  - `vision_ocr` / `ocr` добавлены как explicit text route/mode.
- `admin_ui/app.py` — Streamlit admin labels:
  - маппинг OCR stage→RU,
  - alias `vision_ocr` → `text`,
  - спец-лейбл `processing_done` для OCR.
- `PROJECT_STATE.md` — добавлен §40 с OCR observability conventions (append-only).
- `scripts/test_ocr_route_smoke.py` не менялся в этом шаге (эвристики + опциональный vision).

## Tests

Команды (после rebuild):

```bash
docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec -it portfolio-test-assistant-flow-1 python scripts/test_ocr_route_smoke.py
docker exec -it portfolio-test-assistant-flow-1 python scripts/test_orchestrator_pipeline.py
```

Результат:
- `scripts/test_ocr_route_smoke.py` → exit code `0` (без `-it`), vision part was `vision_api_skipped` из-за ошибки `image_parse_error` на minimal PNG fixture (эвристики OK, script устойчив к ошибке vision).
- `scripts/test_orchestrator_pipeline.py` → exit code `0` (успешные smoke сценарии text + image generation).

## Manual check instructions (обязательно)

1. Telegram: режим `/mode ocr`.
2. Отправить фото с печатным текстом (или скрин).
3. Проверить:
   - в Telegram есть ответ с распознанным текстом;
   - в Logs execution route=vision_ocr status=success;
   - в pipeline timeline stage labels OCR теперь отображаются по-русски, не «Нестандартный этап»;
   - блоки:
     - «Что спросил пользователь» показывает “Изображение для OCR …”
     - «Что ответила система» показывает preview распознанного текста;
   - Text modality page содержит эту OCR execution.

## Deferred

- OCR → RAG integration (на этом шаге не делаем).
- Автогенерация PNG fixture в тестах (не тащим OCR libs; smoke остаётся service-level).

---

## Corrective pass (2026-05-11) — React/FastAPI contour

### Root cause (почему прошлый фикс «не дотянул» до UI)

1. **Маршрутизация и агрегаты шли мимо `vision_ocr`**: в SQL `count_routes_since` не было ветки `vision_ocr` / `mode=ocr` → bucket `text`, из‑за чего summary/dashboard undervalued «текст» для OCR. На фронте `pickRoute` в **Logs** раньше не классифицировал `vision_ocr` как text family (частично компенсировалось только в Streamlit).
2. **Summary lifecycle whitelist**: `SUMMARY_LIFECYCLE_STAGE_ORDER` не содержал OCR stages → блок «Этапы» в summary не показывал OCR, даже если `by_stage` в БД их считал.
3. **Truncation API**: `_PRESERVED_DETAIL_KEYS` в `admin_api/deps.py` не сохранял `list_user_preview`, `recognized_text_preview`, `intake_image_asset_ref` и др. при slimming больших `details` → React получал урезанный payload без полей для карточек.
4. **Telegram payload**: `user_text`/`query_preview` тащили mime/size в одну строку — это попадало в list preview; **не было** сохранения intake в assets → в React нельзя было стабильно показать **image preview** через `/api/assets/preview`.
5. **CORS**: dev admin-ui на **:8080** не был в `_DEFAULT_DEV_ORIGINS` FastAPI → cross-origin `<img src="…8600/api/assets/preview">` мог блокироваться браузером.

### Legacy / irrelevant для primary contour

- Точечные правки только в **`admin_ui/app.py`** (Streamlit) **не заменяют** operational UI на React; primary trace: **`frontend/admin-ui/src/pages/*.tsx`** → **`admin_api/deps.log_row_to_entry` / routes** → **`services/admin_service.py`** → **`repositories/processing_logs_repository.py`** → JSON **`details`** из **`interfaces/telegram_bot.py`** / orchestrator.

### Фактически затронутые файлы (corrective pass)

- `interfaces/telegram_bot.py` — компактный preview, `ocr_input_diagnostics`, сохранение intake в `AssetRepository`, `ocr_ui_base` на всех OCR stages.
- `repositories/processing_logs_repository.py` — `vision_ocr` / `mode ocr` → text bucket.
- `services/admin_service.py` — расширение `SUMMARY_LIFECYCLE_STAGE_ORDER`.
- `admin_api/deps.py` — preserved keys + slim для OCR.
- `admin_api/app.py` — CORS origins `:8080`.
- `frontend/admin-ui/src/pages/LogsPage.tsx`, `TextPage.tsx` — previews, `asset_ref` query, diagnostics key `ocr_input_diagnostics`.
- `PROJECT_STATE.md` — §41 (этот проход).

### Ручная проверка (checklist)

1. `docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build`
2. Telegram: `/mode ocr` → фото с текстом → ответ в Telegram.
3. Admin UI (React): **Logs** — session в фильтре **Текст**; слева компактная строка (`Изображение для OCR` или `OCR: …`); timeline без «Нестандартный этап» для known OCR stages.
4. **Text** modality — та же execution; «Что спросил» — **картинка** + краткий текст; «Технические параметры» — mime/size в `<details>`.
5. **Summary** — в lifecycle block видны счётчики по OCR stages (если были события в окне).
6. В контейнере: `docker exec portfolio-test-assistant-flow-1 python scripts/test_ocr_route_smoke.py` и `…/scripts/test_orchestrator_pipeline.py` (без `-it` при необходимости).

---

## Modality + timeline corrective (2026-05-11)

### Root cause (почему summary = text, а Logs/Text filter = «Прочее» / нет на Text)

- **Summary** использует SQL `count_routes_since` по сырому JSON в БД — маршрут OCR там уже мапился в **text**.
- **Logs** строили `pickRoute` только из **`route`/`mode`** в строках ответа API; при **усечённом `details`** и/или широком **`includes("image")`** сессия могла уходить в **`other`/`image`** → **`routeLabelRu` → «Прочее»** (через `unknown`), фильтр «Текст» отсекал execution.
- **Text page** (`isTextExecutionSession`) в основном смотрел на **объект** `details` / `row.route`; если `details` в ответе не объект или неполный, а **`row.route`** не приходил ожидаемо на клиенте, OCR-сессия отфильтровывалась.

### «Нестандартный этап» в таймлайне

- Компоненты **Logs/Text/…** уже вызывают **`stageToActionRu(row.stage, row.details)`** из `operationalLabels.ts`.
- Если в БД/JSON в поле **`stage`** попадали **невидимые символы** или **пробелы**, ключ не совпадал с **`OCR_STAGE_LABEL_RU`** / **`EVENT_TYPE_RU`** → срабатывал fallback **«Нестандартный этап»**.
- Исправление: **`normalizeMachineStage`** + использование его в **`stageToActionRu`** / **`normalizeEventType`**.

### Реальные machine stage names (OCR contour)

- `intake_received`, `image_received`, `ocr_started`, `ocr_done`, `ocr_error`, `ocr_response_sent`, `processing_done` (спец-лейбл при `route=vision_ocr`).

### Изменённые файлы (этот шаг)

- `admin_api/deps.py` — `infer_modality_route`, `infer_modality`, поля **`modality`**, **`modality_route`** в `log_row_to_entry`; `_PRESERVED_DETAIL_KEYS`: `modality`.
- `interfaces/telegram_bot.py` — в OCR `details`: **`modality: "text"`**.
- `frontend/admin-ui/src/api/client.ts` — тип **`LogItem`** расширен.
- `frontend/admin-ui/src/pages/LogsPage.tsx` — **`pickRoute`**: сначала `modality_route`, затем эвристика без широкого `includes("image")`.
- `frontend/admin-ui/src/pages/TextPage.tsx` — **`sessionHasBackendTextModality`**.
- `frontend/admin-ui/src/utils/operationalLabels.ts` — **`normalizeMachineStage`**.
- `PROJECT_STATE.md` — §42.

### Ручная проверка

1. Rebuild stack / admin-ui (`docker compose … --build` или `npm run build` в `frontend/admin-ui`).
2. Telegram `/mode ocr` → фото с текстом.
3. Logs: фильтр **Текст** показывает сессию; категория **ТЕКСТ**, не «Прочее»; таймлайн — русские OCR-этапы.
4. Text page: та же execution в списке.
5. При подозрении на stale bundle — **clean** `frontend/admin-ui/node_modules/.vite` + rebuild (заметка для оператора).

---

## OCR telemetry + incoming asset persistence (2026-05-11)

### Root cause

- **Токены / «Задержка ответа» = н/с**: `OpenAIChatProvider.extract_text_from_image` уже выставлял `_last_usage`, но **`run_telegram_ocr_flow`** не читал `get_last_llm_usage_for_log()` и не писал **`response_latency_ms` / `input_tokens` / `prompt_tokens`** в `details` стадий, которые смотрит Text page (`pickAggregatedTokens`, `pickResponseLatencyMs`, `TEXT_LATENCY_STAGES` включает `ocr_done`, но там не было latency/token полей).
- **Картинка как asset**: байты уже сохранялись через `AssetRepository`, но namespace был **`telegram/ocr_input`**, в payload не было полного набора **`input_asset_*`** (filename, sha256, …) как у audio **`_asset_dict`**; часть метаданных жила только в free-form diagnostics.

### Эталон audio

- `services/audio_pipeline_service.py` — **`_asset_dict`**: `asset_ref`, `filename`, `content_type`, `size_bytes`, `sha256`, `namespace`; входной звук пишется в lifecycle через **`save_input_audio`**.

### Изменённые файлы

- `interfaces/telegram_bot.py` — `_ocr_input_asset_fields`, `_ocr_vision_telemetry`, namespace **`incoming_images`**, телеметрия на **`ocr_done` / `ocr_response_sent` / `processing_done`**.
- `admin_api/deps.py` — **`_PRESERVED_DETAIL_KEYS`**: OCR asset + latency + `usage_not_returned_by_provider_wrapper`, **`model`/`provider`**.
- `frontend/admin-ui/src/pages/TextPage.tsx` — токены из **`prompt_tokens`/`completion_tokens`**, стадия **`ocr_done`** в агрегаторе токенов, **`input_asset_ref`** для preview, UX **«не вернул провайдер»**, флаг **`usage_not_returned_by_provider_wrapper`**.
- `services/vision_ocr_service.py` — docstring про persistence.
- `scripts/test_ocr_route_smoke.py` — asset save + payload sanity (no base64).
- `PROJECT_STATE.md` — §43.

### Tests

- `python scripts/test_ocr_route_smoke.py` — incoming asset + optional vision.

### Manual checklist

1. `/mode ocr` → фото с текстом.
2. Text page: **Задержка ответа** заполнена; токены — числа или «не вернул провайдер».
3. Preview изображения; в diagnostics — **content_type, size, sha256, filename**; в JSON логов нет raw base64.

