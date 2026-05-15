# Memory UI — targeted polish (AF operational standard)

Session date (from `date +%F`): **2026-05-14**

## Full prompt (verbatim)

Cursor, небольшой targeted UI polishing pass для Memory.

НЕ переписывать страницу.
НЕ трогать backend/API.
НЕ менять структуру данных.
Только доведение Memory до фактического AF operational UI standard.

Создать engineering log:

docs/cursor_sessions/YYYY-MM-DD_memory-ui-polish-pass.md

Дата:

date +%F

Commit НЕ выполнять.

==================================================
1. Top panels: исправить вертикальное растяжение контента
==================================================

Сейчас панели:

- Параметры сессии
- Runtime memory context
- Memory policy / limits

имеют одинаковую высоту — это правильно.

НО внутри панели строки растянуты по вертикали через space-between/flex-grow и выглядят распределёнными по высоте панели.

Это НЕ то, что нужно.

Правило:

панели одинаковой высоты,
но текст внутри панели идёт плотным естественным списком сверху вниз.

Как в RAG и Logs.

Нужно:

- убрать распределение строк по высоте;
- убрать flex-grow/flex:1 у dl/content, если он используется для растяжения;
- сохранить одинаковую высоту контейнеров;
- сохранить компактные интервалы между строками;
- допустимо пустое место внизу панели.

Цель:

верхний ряд выглядит как RAG:
плотный контент + ровный нижний край.

==================================================
2. Timeline JSON/details вернуть к стандарту Logs
==================================================

Сейчас:

JSON-preview уехал в центр строки,
серые подписи дублируют часть JSON.

Это выбивается из стандарта.

Нужно как в Logs:

Строка 1:

timestamp + marker + stage + статус + latency

Строка 2:

слева под стадией:
синяя строка details/json preview

Без серых промежуточных дублей.

Убрать:

route=...
loaded=...
trimmed=...
и подобные серые подписи.

Оставить:

одну компактную синюю строку preview/details
строго под стадией процесса.

Позиционирование:
слева.

Не по центру.

Не отдельно в колонке.

В раскрытии:
полный JSON как сейчас.

==================================================
3. Нижний отступ страницы привести к Logs
==================================================

Сейчас у Memory огромная пустота внизу.

Сравнить:

LogsPage
MemoryPage

Memory должна иметь такой же нижний rhythm/layout.

Проверить:

- min-height
- padding-bottom
- container spacing
- flex-grow
- page wrapper

Убрать лишнюю пустоту.

Не ломать скролл.

==================================================
4. Проверка
==================================================

cd frontend/admin-ui && npm run build

Проверить вручную:

1.
верхние панели:
ровная высота + плотный текст

2.
таймлайн:
синяя preview/details слева под стадией

3.
нет серых дублей

4.
нижний отступ как в Logs

В конце:

## Changed files

## What was fixed

## Operator commands / next verification commands

Commit НЕ выполнять.

## Changed files

- `frontend/admin-ui/src/pages/MemoryPage.tsx`
- `frontend/admin-ui/src/styles/globals.css`
- `docs/cursor_sessions/2026-05-14_memory-ui-polish-pass.md` (this file)

## What was fixed

1. **Top panels (triple row)**  
   Удалены `display: flex` / `flex-direction: column` у панелей и **`flex: 1` у `dl`**, из‑за которых блок KV растягивался по высоте ячейки. Сетка по‑прежнему **`align-items: stretch`** — одинаковая высота карточек, контент **плотным блоком сверху**, пустота только внизу панели.

2. **Timeline**  
   Разметка как в **Logs**: после `logs-stage__top` сразу **`logs-stage__details`** с `log-details__summary` (accent preview через `memoryLifecyclePreviewSummary`) и полным JSON в `<pre>`. Убраны серая строка метрик (`loaded=` / `route=` / …) и flex-«вторая строка» с колонками. Иконка + заголовок этапа в одном `logs-stage__label` через **`memory-pipeline-stage__label`**.

3. **Нижний rhythm / скролл**  
   - Убран внешний **`memory-right-detail-scroll`** (двойной скролл с `logs-detail`): правая колонка как у Logs — один **`logs-detail`** с `flex: 1` и `overflow-y: auto`.  
   - **`.memory-logs-console`**: те же **`height: min(82vh, 980px)`**, **`min-height: 0`**, **`overflow: hidden`**, что у **`.logs-console`**.  
   - **`.memory-console-page .rag-page__lead`**: `margin-bottom: 0.5rem` как у **`.logs-lead`**.

## Build result

`cd frontend/admin-ui && npm run build` — **успешно** (`tsc -b` + `vite build`).

## Operator commands / next verification commands

```bash
cd frontend/admin-ui && npm run build
```

Ручная проверка Memory:

1. Три верхние панели: одинаковая высота, строки KV **сверху плотно**, без «разъезда» по высоте.  
2. Таймлайн: строка 1 — время, этап, статус, latency; строка 2 — **одна** синяя строка summary (preview), под ней раскрытие с полным JSON.  
3. Нет серой строки `loaded=…` / `route=…` над details.  
4. Нижний отступ и высота консоли визуально ближе к **Logs** (один скролл справа, без лишней пустоты от вложенного scroll-wrapper).

**Коммит не выполнялся.**
