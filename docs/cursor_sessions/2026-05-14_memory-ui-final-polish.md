# Memory UI — final operational polish

Session date (from `date +%F`): **2026-05-14**

## Full prompt (verbatim)

Cursor, нужен точечный polish Memory UI после проверки живого экрана.

НЕ переписывать страницу. Backend/API менять только если без этого невозможно. Основной фокус — layout и поведение.

Контекст:
Memory уже приведён к AF modality console pattern. Сейчас требуется довести до консистентного operational UX.

1. Верхние панели карточки Memory-сессии

Сейчас справа Runtime и Memory policy стоят вертикально, из-за чего верх карточки занимает лишнюю высоту.

Нужно:
внутри "СВОДКА MEMORY-СЕССИИ" сделать верхний ряд из 3 compact panels:

[Параметры сессии] [Runtime memory context] [Memory policy / limits]

Все три панели в одну строку, как compact grouped operational panels.
Уместить существующие поля без потери информации.
Не делать KPI tiles.
Не делать dashboard.
Если ширины мало — уменьшить внутренние отступы/шрифт/ширину kv labels, но сохранить читаемость.

Цель:
освободить вертикальное место для главной сущности — "Диалог сессии".

2. Timeline memory pipeline

Сейчас timeline стал визуально интересным, но после удаления timestamp перестал быть настоящим timeline.

Нужно привести к стандарту AF timeline:

Каждое событие:
- цветной маркер / icon допускается;
- stage label;
- timestamp обязательно;
- status;
- latency_ms если есть;
- key metrics: loaded, saved, trimmed, intent, etc.
- раскрывающийся JSON/details по каждому событию.

Формат должен быть похож на существующие timeline blocks в RAG/Text/Logs, но можно сохранить цветные маркеры как улучшение.

Важно:
если timestamp отсутствует в текущем объекте — проверить, есть ли он в lifecycle payload.
Если нет — явно показать "timestamp: n/a", но не скрывать поле молча.

3. Left list filters

Сейчас есть поиск, active only, hide synthetic, pagination.
Нужно оценить и привести к канону RAG/Text/Logs:

- поиск должен быть первой строкой;
- ниже filters row;
- фильтр по mode: all / rag / text / other если данные позволяют;
- фильтр по статусу active: all / active / inactive вместо одного checkbox, если проще и ближе к канону;
- hide synthetic можно оставить checkbox, так как это специфично для Memory;
- count string сохранить.

Не перегружать.

4. Keyboard / arrow navigation

Сейчас при нажатии стрелок выбор айтема не меняется ожидаемо:
- визуально список/scrollbar двигается;
- selected session остаётся прежней.

Нужно реализовать нормальную навигацию по списку:

- ArrowDown выбирает следующую видимую session;
- ArrowUp выбирает предыдущую видимую session;
- при переходе selection должен обновлять правую панель;
- список должен scrollIntoView для selected item;
- Enter по item не нужен, если выбор происходит сразу;
- не ломать mouse click.

Если фокус сейчас уходит на scroll container — исправить tabindex / keydown handler.

Важно:
навигация должна работать по текущему filtered/paginated visible list.

5. Pagination behavior

Проверить:
- Previous / Next меняют страницу списка;
- selection после смены страницы:
  предпочтительно выбирает первый item новой страницы,
  чтобы слева и справа были синхронны.
- Не оставлять справа сессию, которой нет на текущей странице, если это визуально сбивает.

6. Создать engineering log:

docs/cursor_sessions/YYYY-MM-DD_memory-ui-final-polish.md

Дата через:

date +%F

В log включить:
- полный текст prompt;
- changed files;
- what fixed;
- build result;
- known limitations;
- operator commands.

В конце обязательно:

## Operator commands / next verification commands

Commit НЕ выполнять.

Проверка:
cd frontend/admin-ui && npm run build
ручная проверка Memory:
- 3 верхние панели в один ряд;
- диалог занимает больше вертикального пространства;
- timeline содержит timestamp;
- JSON/details раскрываются по событию;
- ArrowUp/ArrowDown реально меняют selected item и правую карточку;
- pagination синхронизирует список и detail.


7. Привести порядок Filter/Search к стандарту AF

Сейчас в Memory поиск расположен выше фильтров. Это нарушает уже сложившийся operational pattern Assistant Flow.

Канонический порядок для AF-консолей (RAG / Text / Images / Logs):

строка 1:
[time window] [status] [mode/specific filters] [actions]

строка 2:
[search]

строка 3:
pagination / count / service info

Memory должна использовать тот же порядок.

Поэтому:

- поиск переносится НИЖЕ фильтров;
- структура визуально повторяет RAG/Text;
- порядок controls не менять произвольно;
- цель — одинаковая мышечная память оператора между всеми operational консолями.

Это не вкусовщина, а UI convention проекта.

## Changed files

- `frontend/admin-ui/src/pages/MemoryPage.tsx`
- `frontend/admin-ui/src/styles/globals.css`
- `docs/cursor_sessions/2026-05-14_memory-ui-final-polish.md` (this file)

## What was fixed

- **Сводка MEMORY-СЕССИИ:** три блока «Параметры сессии», «Runtime memory context», «Memory policy / limits» в одной сетке (`memory-memory-top-panels--triple`), без вертикального стека runtime/policy; компактные отступы и KV на узких экранах.
- **Таймлайн pipeline:** строки в стиле `logs-timeline` / `logs-stage` — время (МСК или явное `timestamp: n/a` с fallback из `details`), этап с иконкой, `StatusBadge`, `latency_ms`, строка метрик (loaded/saved/trimmed/route/intent), раскрывающийся JSON по событию.
- **Левая колонка:** порядок как у Text/RAG — строка фильтров (режим, активность, synthetic), затем поиск, затем meta (count) + refresh, затем пагинация и source; добавлены селекты **режим** (all/rag/text/other) и **активность** (all/active/inactive).
- **Клавиатура:** глобальный `keydown` для ArrowUp/ArrowDown по полному **отфильтрованному** списку с синхронизацией страницы; `scrollIntoView` и фокус строки через `data-memory-session-id` и `pendingListFocusRef` (как на RAG).
- **Пагинация:** Prev/Next переводят на соседнюю страницу и выбирают **первую** сессию на новой странице; если выбранная сессия не на текущей странице — автосброс на первую строку страницы.

## Build result

```text
cd frontend/admin-ui && npm run build
```

- **Exit code:** 0  
- **Steps:** `tsc -b` + `vite build` completed successfully.

## Known limitations

- **Режим «inactive»** и полный список неактивных зависят от того, что API отдаёт при `activeOnly: false`; при `activeOnly: true` (фильтр «активные») неактивные на клиенте не появятся.
- **Режимы rag/text/other** — эвристика по строке `mode` (как в запросе); произвольные режимы попадают в «прочие».
- **Тройная панель сводки:** при ширине viewport меньше 960px сетка переходит в одну колонку (вертикальный стек), чтобы не ломать читаемость.
- Стрелки не обрабатываются, когда фокус в `input` / `textarea` / `select` (намеренно, как на RAG).

## Operator commands / next verification commands

Ручная проверка в UI (Memory):

1. Убедиться, что на широкой вёрстке три верхние панели в **один ряд**, диалог ниже занимает больше полезной высоты.
2. Раскрыть «Таймлайн memory pipeline»: у каждого события есть **время или `timestamp: n/a`**, статус, при наличии — **latency**, метрики; блок **JSON / details** раскрывается по строке.
3. Слева: **сначала** фильтры (режим, активность, synthetic), **потом** поиск; meta со счётчиком и refresh; пагинация под ними.
4. **ArrowUp / ArrowDown** без фокуса в полях ввода: меняется выделенная сессия, обновляется правая панель, строка прокручивается в видимую область.
5. **Prev / Next:** первая сессия на новой странице выбрана, справа соответствующий detail.

Повторная сборка:

```bash
cd frontend/admin-ui && npm run build
```

**Коммит не выполнялся** (по требованию).
