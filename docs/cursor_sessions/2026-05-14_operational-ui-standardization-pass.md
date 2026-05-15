# Operational UI standardization pass (RAG + Memory)

Session date (from `date +%F`): **2026-05-14**

## Full prompt (verbatim)

Cursor, нужен targeted UI standardization pass по RAG и Memory.

НЕ переписывать страницы целиком.
НЕ менять backend/API без необходимости.
Фокус: layout consistency с AF operational console standard.

Создать engineering log:

docs/cursor_sessions/YYYY-MM-DD_operational-ui-standardization-pass.md

Дата через:

date +%F

Commit НЕ выполнять.

==================================================
1. RAG: перекомпоновка верхних панелей карточки
==================================================

Проблема:
в RAG detail card верхняя зона сейчас нерациональна:
- слева высокая панель "Параметры сессии";
- справа сверху маленькая "Качество";
- ниже справа высокая "Retrieval";
- под "Параметры сессии" остаётся пустота;
- высокая Retrieval-панель провоцирует лишний vertical scroll.

Нужно:
скомпоновать top panels так:

Левый столбец:
- "Параметры сессии"
- под ней "Качество"

Правый столбец:
- "Retrieval" на высоту двух левых панелей

Цель:
- меньше пустоты;
- меньше вертикального скроллинга;
- RAG top area компактнее;
- без потери данных.

==================================================
2. Memory: одинаковая высота панелей в одном ряду
==================================================

Ввести UI rule:
панели, размещенные в одном horizontal row, должны быть одинаковой высоты.

Для Memory top panels:
- "Параметры сессии"
- "Runtime memory context"
- "Memory policy / limits"

Нужно:
- выровнять высоту всех трёх панелей по самой высокой;
- пустое место в нижней части более коротких панелей допустимо;
- не сжимать содержимое до нечитаемости;
- сохранить compact grouped operational panels.

Это должно стать паттерном для будущих modality consoles.

==================================================
3. Memory timeline: привести к стандарту остальных консолей
==================================================

Проблема:
Memory timeline сейчас визуально в 3 строки:
- time + marker + stage
- metrics
- JSON/details

В остальных консолях timeline компактнее и ближе к 2-строчному виду.

Нужно:
сделать Memory timeline в 2 строки:

Строка 1:
timestamp + marker/icon + stage label + status + latency

Строка 2:
key metrics + раскрываемый details/json

Важно:
- не писать просто "JSON / details" как отдельную синюю ссылку без контента;
- раскрываемая строка должна вести себя как в других консолях;
- если в других консолях показывается содержимое JSON/preview в раскрытии — сделать так же;
- если есть причина оставить особый формат для Memory, в отчёте аргументировать, почему Memory timeline должен отличаться от стандарта.

Цель:
timeline memory pipeline должен выглядеть частью общей AF timeline-системы.

==================================================
4. Memory filters: привести к стандарту RAG/Text/Logs
==================================================

Проблема:
текущие фильтры Memory недостаточно каноничны:
- нет главного time window filter;
- значения "все" недостаточно содержательны;
- checkbox "скрыть synthetic" стоит в основной строке фильтров и сбивает смысл;
- нижний meta/footer блок слишком большой.

Нужно:

Строка фильтров Memory:

[24h / 48h / 7d] [все режимы] [все статусы]

Где:
- time window — первый фильтр;
- режимы: все режимы / rag / text / other;
- статусы: все статусы / активные / неактивные.

Поиск:
- второй строкой, как в RAG/Text.

Synthetic:
- перенести ниже или сделать отдельной компактной опцией вне основной filter row;
- label сделать понятным:
  "скрыть тестовые/synthetic-сессии"
  или короче, но понятно.

Count/meta/pagination:
- привести к RAG-standard:
  компактная строка:
  "Страница X из Y · сессий: N · показано: M"
- кнопки Previous / Next / Reset компактно;
- source/API info не должен превращаться в огромный нижний колонтитул;
- если source нужен — сделать muted micro-line.

==================================================
5. Проверить keyboard/pagination после изменения фильтров
==================================================

Убедиться:
- ArrowUp/ArrowDown продолжают менять selected session;
- правая панель синхронизируется;
- pagination выбирает первый item новой страницы;
- time window filter сбрасывает/пересчитывает страницы корректно;
- поиск работает вместе с mode/status/time/synthetic filters.

==================================================
6. PROJECT_STATE note для будущего патча
==================================================

В отчёте дать готовый текст для будущего PROJECT_STATE:

Operational UI row-height convention:
Panels in the same grouped operational row should share equal height, aligned by the tallest panel. Empty lower space is preferable to uneven visual rhythm.

Operational filter convention:
Row 1 = time/status/mode/specific filters.
Row 2 = search.
Row 3 = compact pagination/count/source metadata.

НЕ редактировать PROJECT_STATE сейчас.

==================================================
7. Проверки
==================================================

Обязательно:

cd frontend/admin-ui && npm run build

Вручную проверить:
- RAG top panels стали компактнее;
- Memory top panels одной высоты;
- Memory timeline двухстрочный и с details/json как в других консолях;
- Memory filters: 24h/48h/7d, все режимы, все статусы;
- synthetic toggle не мешает основной строке фильтров;
- footer/meta compact;
- keyboard navigation не сломана.

В конце engineering log обязательно:

## Operator commands / next verification commands

## Changed files

- `frontend/admin-ui/src/pages/RagPage.tsx`
- `frontend/admin-ui/src/pages/MemoryPage.tsx`
- `frontend/admin-ui/src/styles/globals.css`
- `docs/cursor_sessions/2026-05-14_operational-ui-standardization-pass.md` (this file)

## What was fixed

### RAG detail top panels

- Заменена сетка `modality-ops-panels--rag-split` на **`modality-ops-panels--rag-balanced`**.
- **Левый столбец:** «Параметры сессии», под ними «Качество».
- **Правый столбец:** одна панель **Retrieval** с классом `modality-ops-panel--rag-retrieval-tall`, растянута по высоте левого столбца; длинный KV прокручивается внутри панели.
- Цель: убрать пустоту под «Параметрами» и снизить ощущение «ломаных» высот; данные не выкидывались.

### Memory top panels (равная высота)

- Для `memory-memory-top-panels--triple`: **`align-items: stretch`**, панели как **flex-column**, **`dl` с `flex: 1`** — три панели в ряду выравниваются по самой высокой.

### Memory timeline (2 строки, как Logs)

- **Строка 1:** `logs-stage__top` — время (или `timestamp: n/a`), иконка + заголовок этапа, статус, latency.
- **Строка 2:** метрики + `<details>` в одной flex-строке; **summary** показывает **превью JSON `details`** (аналог `previewSummary` в `LogsPage`), развёрнутый блок — полный JSON события (`stage`, `created_at`, `status`, `details`), как `log-details__json` в логах.
- Отдельная подпись «JSON / details» без превью убрана — поведение как у операционных таймлайнов.

### Memory filters

- **Строка 1:** `24h` / `48h` / `7d` (клиентский фильтр по **`updated_at`** после загрузки списка), затем режим (подписи: все режимы / RAG / текст / прочие), затем статусы (все статусы / активные / неактивные). Backend не менялся: по-прежнему `fetchMemorySessionsList` с `active_only` только для фильтра «активные».
- **Строка 2:** поиск.
- **Synthetic:** отдельная компактная строка под поиском, текст **«скрыть тестовые / synthetic-сессии»**.
- **Meta:** `Страница X из Y · сессий: N · показано: M` + refresh (как RAG/Text).
- **Source:** одна **muted micro-line** (`memory-api-micro`).

### Keyboard / pagination

- Логика списка не переписывалась: стрелки и пагинация по-прежнему завязаны на **`filtered`**; добавлены зависимости **`windowLabel`** в сброс страницы и в **`filtered`**, чтобы смена окна пересчитывала страницы и выбор.

## Build result

```bash
cd frontend/admin-ui && npm run build
```

- **Exit code:** 0 (`tsc -b` + `vite build`).

## Known limitations

- **Окно по времени** применяется на клиенте к уже загруженным до `LIST_FETCH_LIMIT` сессиям; без `updated_at` или с невалидной датой строка **не попадает** в выборку по окну (строгое поведение).
- **Неактивные** сессии видны только если API вернул их при `active_only: false` (как и раньше).

## Memory timeline vs общий стандарт (аргументация)

Отличий от Logs по смыслу данных нет: тот же паттерн **`logs-stage` + summary с превью объекта + `<pre>` с полным JSON**. Для Memory в JSON вкороченно передаётся обёртка `{ stage, created_at, status, details }`, чтобы оператор видел и сырой `details`, и контекст этапа без дублирования полного lifecycle-массива в каждой строке.

## Ready text for future `PROJECT_STATE` (do not apply in this patch)

Operational UI row-height convention:

Panels in the same grouped operational row should share equal height, aligned by the tallest panel. Empty lower space is preferable to uneven visual rhythm.

Operational filter convention:

Row 1 = time/status/mode/specific filters.

Row 2 = search.

Row 3 = compact pagination/count/source metadata.

## Operator commands / next verification commands

```bash
cd frontend/admin-ui && npm run build
```

Ручная проверка:

1. **RAG:** открыть сессию — сверху слева «Параметры» + «Качество», справа одна высокая «Retrieval», без пустоты слева под параметрами; при узком экране колонки складываются в одну (CSS breakpoint 900px).
2. **Memory:** три верхние панели одной высоты в ряд (на широкой вёрстке).
3. **Memory timeline:** две визуальные строки на событие; в summary — превью `details`; внутри — полный JSON.
4. **Memory filters:** первая строка — окно, режим, статус; вторая — поиск; synthetic отдельной строкой; meta компактная; source — мелкая строка внизу.
5. **Клавиатура:** ArrowUp/ArrowDown вне полей ввода; смена окна времени сбрасывает страницу и не ломает выбор.

**Коммит не выполнялся.**
