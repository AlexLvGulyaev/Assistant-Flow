# Memory — консольный layout (split list / detail)

**Дата:** 2026-05-14 (`date +%F`)

---

## Исходный промпт

Архитектурный шаг: привести Memory к базовому паттерну AF-консолей.

Контекст: сейчас список → Inspect modal; нужно список слева → постоянная рабочая область справа (как RAG, Text, OCR).

Ограничения: backend не трогать, API не менять, логику memory не менять, только UI architecture. Session log с полным отчётом. Commit не выполнять.

Требования:

1. Убрать Inspect modal — выбор сессии обновляет правую панель.
2. Правая панель: сверху «СВОДКА MEMORY-СЕССИИ» + карточки (mode, active, msgs, turns, budget, trimmed); ниже Runtime memory context; Conversation preview; Lifecycle timeline; Advanced diagnostics (collapse).
3. Conversation preview: bubbles, 3–6 последних turn, ограничение высоты, внутренний scroll.
4. Lifecycle: сохранить timeline v2 (не карточки, не raw log).
5. Пустое состояние: «Memory session not selected» / «Выберите сессию слева» в стиле AF.
6. Проверить визуальное единство с RAG/Text.

Файл: `docs/cursor_sessions/YYYY-MM-DD_memory-console-layout.md`, в конце operator commands.

---

## Результаты работы

### Сделано

1. **Удалён модальный Inspect** — вместо `memory-modal-backdrop` используется сетка **`logs-console`** (как у RAG/Text): **`logs-left card`** (список) + **`logs-right card`** (деталь).

2. **Список слева** — строки как **`button.logs-item`** с выделением **`logs-item--selected`**, клик задаёт `selectedSessionId`. Фильтры и refresh перенесены в **`logs-filters`** (липкая шапка левой колонки). Бейдж `mem`, метаданные в стиле `logs-item__preview` / `logs-item__meta`. При скрытии synthetic, если текущая сессия выпала из списка, выбор **сбрасывается** (`useEffect` + `selectedStillVisible`).

3. **Правая панель** — обёртка **`memory-right-detail-scroll`** (`overflow-y: auto`) с **`logs-detail rag-modality-detail`**:
   - заголовок **«СВОДКА MEMORY-СЕССИИ»** + статус-бейдж (`TEST` / `ACTIVE` / `INACTIVE`);
   - сетка **`memory-session-kpi-grid`** из шести **`MemoryOpCard`**: session mode, active, msgs, turns~, budget (load/cap), trimmed;
   - блок **Runtime memory context** (прежняя сетка полей + RAG/Meta + пары лимита);
   - **Conversation preview** (bubbles, до 6 реплик, **`memory-preview-scroll--panel`** с `max-height`);
   - **Lifecycle** — компактный timeline v2 без изменения формата строк метрик;
   - **Advanced diagnostics** в `<details>` внизу панели.

4. **Глобальная сводка** — блок **`SectionCard` «Сводка»** остаётся **над** split-консолью (как операционный контекст до списка сессий).

5. **Пустое состояние** — `EmptyState` с `title="Memory session not selected"` и `message="Выберите сессию слева"`.

### Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `frontend/admin-ui/src/pages/MemoryPage.tsx` | Переход на `logs-page` + `logs-console`; состояние `selectedSessionId`; загрузка детали без модалки; новый `MemorySessionDetailPanel` (вертикальный стек вместо двух колонок внутри модалки); сброс выбора при фильтре. |
| `frontend/admin-ui/src/styles/globals.css` | Классы `.memory-logs-console`, `.memory-right-detail-scroll`, `.memory-session-kpi-grid`, `.memory-detail-panel*`, `.memory-preview-scroll--panel`, `.memory-timeline-section--panel`, вспомогательные для левого списка. |

### Не менялось

- Backend, маршруты API, контракты `fetchMemory*` без изменений.

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

Ручная проверка: открыть **Memory / Sessions** и сравнить с **RAG** и **Text** — двухколоночная консоль, выбор в списке, скролл детали справа; убедиться, что без выбора сессии показывается пустое состояние на английском заголовке из ТЗ.
