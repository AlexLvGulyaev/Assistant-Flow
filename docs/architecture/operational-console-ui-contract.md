# 🏗️ Operational Console UI contract (Assistant Flow)

Session date (`date +%F`): **2026-05-14**

## 1. Full prompt (verbatim)

Новый шаг. Это НЕ локальный фикс Memory.

Это формализация UI-стандарта всей системы Assistant Flow.

Обязательно:

1. Внести текст промпта в session log.
2. Проверить PROJECT_STATE.
3. Если раздел UI / Operational Console Standards отсутствует — создать.
4. Зафиксировать новые правила.

Нужен не page-fix, а единый operational UI contract.

==================================================
ЦЕЛЬ
====

После нескольких часов доработки Memory фактически стала эталоном operational console.

Теперь нужно:

1. Зафиксировать ОБЩИЙ стандарт.
2. Привести остальные консоли к нему.
3. Вынести повторяемую логику в общие layout helpers.

Речь не про Memory.

Речь про:

RAG
Text
Images
Audio
Logs
Memory
будущие консоли

==================================================
ОБЩИЙ СТАНДАРТ OPERATIONAL CONSOLE
==================================

Любая operational console строится одинаково:

---

1. Левая колонка

---

Структура всегда:

[Фильтры]
[Поиск]
[Дополнительные чекбоксы]
[Пагинация]
[Список айтемов]

Порядок фиксирован.

Не менять.

Фильтры всегда первой строкой.

Поиск всегда ниже.

Чекбоксы ниже поиска.

Пагинация ниже.

Список ниже.

---

2. Правая часть

---

Правая часть:

постоянная карточка выбранного айтема.

Не popup.
Не modal.

Паттерн:

Слева список
Справа detail panel

Как RAG.

==================================================
ВЫБОР АЙТЕМА
============

При открытии консоли:

если список не пуст:

автоматически выбирать первый элемент.

Не показывать:

"ничего не выбрано"

если записи существуют.

==================================================
ПАНЕЛИ ВЕРХНЕЙ ЧАСТИ
====================

Верх карточки:

информационные панели.

Используем layout-математику.

Равенство высот действует внутри row.

Формула:

P1=P2=P3

или

P1+P2=P3

в зависимости от layout.

---

Memory:

P1(1)=P2(2)=P3(3)

---

RAG:

P1(1)+P2(1)=P3(2)

---

Text/Audio/Image/Logs:

P1(1)=P2(2)

==================================================
КОНТЕНТ ПАНЕЛЕЙ
===============

Внутри панели:

НЕ использовать:

justify-content:space-between

НЕ растягивать текст.

НЕ распределять текст по высоте.

Правильно:

KV-list сверху вниз.

Плотный список строк.

Пустое место допустимо снизу.

==================================================
ГЛАВНАЯ ОБЛАСТЬ КАРТОЧКИ
========================

После верхних панелей:

главный контент айтема.

Именно он должен быть визуальным фокусом.

Примеры:

RAG:

запрос
ответ
чанки

Memory:

диалог

Text:

ввод
ответ

Logs:

pipeline trace

Нельзя делать главный контент маленьким.

Он — центр карточки.

==================================================
ТАЙМЛАЙН PIPELINE
=================

Стандарт:

строка 1:

timestamp
иконка
название стадии

справа:

статус
latency

строка 2:

раскрытые JSON details

JSON размещать СЛЕВА.

Как Logs.

Не по центру.

Не использовать серые дублирующие подписи.

==================================================
ЦВЕТНЫЕ ИКОНКИ СТАДИЙ
=====================

Memory показала удачную фичу.

Добавить глобально.

Пример:

success → зелёный

loading → голубой

processing → синий

reset → оранжевый

warning → жёлтый

error → красный

Цвета одинаковы:

Memory
RAG
Logs
Text
Images
Audio

==================================================
BADGE МОДАЛЬНОСТИ
=================

Модальность отображать одинаково:

rag
mem
text
ocr
vision
audio
image
test

Использовать единый badge-style.

Сейчас Memory и RAG уже выглядят лучше.

Сделать стандартом.

==================================================
НИЖНИЙ КОЛОНТИТУЛ
=================

Нижний пустой отступ:

минимальный.

Как RAG.

Не допускать больших пустых зон.

==================================================
ОБЩИЙ HELPER
============

Если существует helper:

вынести:

row balancing

layout patterns

timeline rendering

badge rendering

stage colors

в общие utilities.

Не делать page-specific решения.

==================================================
ОЖИДАЮ В ОТЧЕТЕ
===============

1. Что вынесено в helper
2. Какие экраны мигрированы
3. Какие остались
4. Что записано в PROJECT_STATE
5. Какие правила теперь считаются UI-стандартом AF


Важно:

Memory НЕ является special-case.

Memory стала референсной реализацией operational console.

Новые консоли строить по этому стандарту по умолчанию.

---

## 2. What was extracted into shared helpers

| Artifact | Location |
|----------|----------|
| JSON preview for `<details>` summary | `detailsJsonPreview()` in `src/utils/operationalConsoleUi.ts` |
| Pipeline stage color heuristic | `pipelineStageVariant()` |
| Modality list badge labels + CSS class list | `OPERATIONAL_MODALITY_LABEL`, `operationalModalityBadgeClassList()`, `normalizeOperationalModality()`, `operationalModalityFromRouteKey()` |
| Memory lifecycle human titles | `memoryLifecycleStageLabel()` |
| Canonical layout class string map | `AF_OPERATIONAL_LAYOUT_CLASSES` |
| Modality mini-badge component | `src/components/OperationalModalityBadge.tsx` |
| Colored stage dot | `src/components/OperationalPipelineStageIcon.tsx` + `.af-pipeline-stage-icon--*` in `globals.css` |
| Unified modality badge colors | `.mini-badge--af` + `.mini-badge--af-{modality}` in `globals.css` |

**Row balancing** remains primarily CSS (`modality-ops-panels--rag-balanced`, `memory-memory-top-panels--triple`, `modality-ops-panels--rag-split`); `AF_OPERATIONAL_LAYOUT_CLASSES` documents the names for new pages.

**Global panel content rule:** `.modality-ops-panels__rag-col--session > .modality-ops-panel { flex: 0 0 auto; }` — stops KV from stretching vertically inside split top panels.

---

## 3. Screens migrated in this pass

- **Memory** — timeline uses `OperationalPipelineStageIcon` + `memoryLifecycleStageLabel` + `detailsJsonPreview`; list uses `OperationalModalityBadge`.
- **RAG** — list badge component; timeline icon + `detailsJsonPreview` (removed duplicate `previewSummary`).
- **Logs** — list modality badge from route; timeline stage icon; `detailsJsonPreview` (removed local `previewSummary`).
- **Text** — list `OperationalModalityBadge` + timeline icon + `detailsJsonPreview`.
- **Images** — same pattern + all former `previewSummary` call sites → `detailsJsonPreview`.
- **Audio** — same pattern.

---

## 4. Screens / areas not migrated (follow-up)

- **Documents** lifecycle / list rows — still own timeline copy; should adopt `OperationalPipelineStageIcon` + `detailsJsonPreview` when touched.
- **Summary** — generic `mini-badge`; optional migration to `OperationalModalityBadge` / `test`.
- **Overview** — different IA (not a `logs-console` session list); only align if Overview gains comparable list rows.

---

## 5. PROJECT_STATE

Added subsection **### UI / Operational Console Standards (React `frontend/admin-ui`)** under **## 9. Admin UI**, covering: left column order, right detail card, auto-select first item, panel height math (Memory / RAG / two-column), dense KV inside panels, main body priority, timeline contract, shared file references, minimal footer rhythm, and explicit “still to align” list.

---

## 6. UI standard AF (short reference)

- **Left:** filters → search → optional checkboxes → pagination meta → list.  
- **Right:** persistent detail card; **Memory** is the **reference** implementation, not a code fork.  
- **Timelines:** line 1 = time + colored dot + label + status + latency/delta; line 2 = one accent summary + expandable full JSON; **no** grey duplicate metric lines above JSON.  
- **Badges:** `OperationalModalityBadge` + `mini-badge--af-*` for list rows.  
- **Stage colors:** `OperationalPipelineStageIcon` driven by `pipelineStageVariant()`.

---

## 7. Build

`cd frontend/admin-ui && npm run build` — **success**.

**Commit not performed** (per user instruction in prior related tasks; none requested here explicitly for commit).
