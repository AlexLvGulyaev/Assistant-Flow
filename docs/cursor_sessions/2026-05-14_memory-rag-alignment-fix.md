# Memory UI — выравнивание с modality console (RAG/Text)

**Дата:** 2026-05-14 (`date +%F`)

---

## Исходный промпт (суть)

Исправить смешение паттернов: Memory не должен быть dashboard/summary как Overview. Эталон только modality operational console: **Text, RAG, Images, Audio, Logs** — слева список, справа рабочая область; структура: general summary сессии → user/system I/O → modality entities → timeline/diagnostics.

Требования:

1. Удалить верхнюю секцию «Сводка» с KPI (PG memory, runtime source, active sessions, avg turns, clear/reset, trimmed и ряд карточек).
2. Верх страницы как RAG/Text: заголовок **Memory**, лид «операционная консоль runtime memory/session diagnostics», сразу split (фильтры + список | правая панель с **СВОДКА MEMORY-СЕССИИ**).
3. Правая область компактно: session id, режим, active, msgs, turns, status — **не** шесть больших KPI-плиток.
4. Runtime memory context — одна компактная operational panel (строки вида Загружено из PG, После trim, В LLM, RAG/META, budget).
5. Conversation preview — оставить bubbles, подписи «Что спросил пользователь» / «Что ответила система», диагностика не мессенджер.
6. Lifecycle — timeline v2 в **collapse** как в RAG: «Таймлайн memory pipeline».
7. Advanced diagnostics — collapse внизу: «Технический снимок memory session (JSON)».
8–9. Никаких гигантских KPI и dashboard-рядов.
10. Визуально одно семейство с Memory / Text / RAG.

Backend/API не менять. Session log `docs/cursor_sessions/YYYY-MM-DD_memory-rag-alignment-fix.md`, operator commands в конце. Commit не делать.

---

## Результаты работы

### Изменения в UI

1. **Удалена глобальная «Сводка»** — убраны `SectionCard`, `fetchMemoryObservabilitySummary`, состояние/типы summary, сетка `MemoryOpCard` и весь KPI-ряд над split.

2. **Шапка страницы** — как у RAG/Text: `<h1 class="page__title">Memory</h1>` + `<p class="page__lead rag-page__lead muted">Операционная консоль runtime memory/session diagnostics</p>`, затем без промежуточного dashboard — сразу **`logs-console`** (при ошибке списка — `panel panel--error page__mt`, как в Text).

3. **СВОДКА MEMORY-СЕССИИ** — сохранён блок `modality-card__head` + бейдж ACTIVE/INACTIVE/TEST; ниже **одна панель** `modality-ops-panels` / `modality-ops-panel` «Параметры сессии» с **`kv` + `OpsRow`**: `session_id` (mono, перенос), пользователь из списка, режим, активна, сообщений, turns~, trimmed, memory_source, обновлена.

4. **Runtime memory context** — вторая компактная `modality-ops-panel` с строками: Загружено из PG, После trim, В LLM, RAG/META (да/нет), budget `load / cap`.

5. **Превью** — блок `memory-preview-wrap` с заголовком «Ввод пользователя и ответ системы»; подсказки над пузырями: **«Что спросил пользователь»** / **«Что ответила система»**; прежние bubble-стили и внутренний скролл.

6. **Lifecycle** — обёрнут в **`<details class="rag-diagnostics-fold">`** с summary **«Таймлайн memory pipeline (N)»**, внутри компактный timeline v2.

7. **JSON** — отдельный **`<details class="rag-diagnostics-fold">`**, summary **«Технический снимок memory session (JSON)»**; содержимое прежних advanced pre/dl.

8. **CSS** — удалены стили KPI-сетки (`memory-summary-grid`, `memory-op-card*`); добавлены `memory-modality-ops--single` (одна колонка, без max-height панелей), `memory-preview-wrap*`, `memory-timeline--in-fold`, `memory-advanced__body--in-fold`, правка для margin внутри `rag-diagnostics-fold` у memory-timeline.

### Файлы

| Файл | Изменение |
|------|-----------|
| `frontend/admin-ui/src/pages/MemoryPage.tsx` | Только `fetchMemorySessionsList` + detail; шапка modality; `OpsRow`; панели как RAG; два fold; передача `listRow` для отображения пользователя. |
| `frontend/admin-ui/src/styles/globals.css` | Удаление KPI-блока; новые/уточняющие классы для memory + fold. |

### API / backend

Без изменений. Эндпоинт summary больше не вызывается из этой страницы (оператору при необходимости доступен отдельно).

### Проверка

- `npm run build` в `frontend/admin-ui` — успешно.

### Commit

**Не выполнялся.**

---

## Operator commands / next verification commands

```bash
date +%F
```

```bash
cd frontend/admin-ui && npm run build
```

Ручная проверка: открыть **Memory**, **Text**, **RAG** — сравнить шапку (`page__title` + `page__lead`), split `logs-console`, правую колонку с `modality-card__head` и `modality-ops-panel`, сворачиваемые блоки в стиле `rag-diagnostics-fold`.
