# Memory UI — modality console contract alignment

**Дата:** 2026-05-14 (`date +%F`)

---

## Исходный промпт (суть)

Привести Memory к паттерну AF modality-console: как RAG — HEADER → summary/status, TOP PANELS (session / modality telemetry / quality), основной объект модальности, timeline, diagnostics. Без giant KPI/dashboard.

Требования:

1. Внутри «СВОДКА MEMORY-СЕССИИ» верхний ряд compact grouped panels: слева «Параметры сессии», справа «Runtime memory context», опционально третья «Memory policy / limits»; не KPI tiles.
2. Главная зона — «Диалог сессии»: две колонки с заголовками один раз («Что спросил пользователь» / «Что ответила система»), табличные пары turn, полная история в пределах API, внутренний скролл, не чат.
3. Левая колонка как RAG/Text/Logs: фильтры, поиск, checkbox active / hide synthetic, пагинация Предыдущая/Следующая/Сброс, строка счёта; при входе авто-выбор первой видимой сессии; пустая правая панель только если список пуст.
4. Таймлайн и JSON — collapsible, как сейчас.
5. В отчёте — готовый текст для будущего PROJECT_STATE (не редактировать PROJECT_STATE сейчас).
6. Session log файл, operator commands, commit не делать.

---

## Результаты работы

### Правая карточка

- После **СВОДКА MEMORY-СЕССИИ** один блок **`modality-ops-panels modality-ops-panels--rag-split memory-memory-top-panels`**:
  - **Слева** (`rag-col--session`): панель **«Параметры сессии»** — `session_id`, пользователь, режим, активна, сообщений, turns~, обновлена (trimmed и `memory_source` перенесены в policy).
  - **Справа** (stack): **«Runtime memory context»** — загружено из PG, после trim, в LLM, budget, RAG/META; ниже **«Memory policy / limits»** — limit pairs, cap messages, trimmed, source (PostgreSQL / fallback).

### «Диалог сессии»

- Секция **«Диалог сессии»** с таблицей **`memory-dialog-table`**: заголовки колонок один раз; строки из **`pairDialogRows`** (пары user→assistant, непарный user — пустая ячейка справа).
- Внутренний скролл у **`memory-dialog-table-wrap`** (`max-height`), не растягивание страницы.
- Подсказка, если **`dialog_messages_in_session` > числа реплик в `recent_turns`** (ограничение выборки).

### Левая колонка

- **`logs-search`**: поиск по `session_id`, `user_label`, `mode`, `telegram_user_id` (клиентский фильтр по пакету до **200** сессий с API).
- Чекбоксы **только активные** / **скрыть synthetic**; **`logs-page-controls`**: Предыдущая / Следующая / Сброс (сброс снимает поиск и фильтры synthetic, снимает active-only).
- Строка метаданных: **`Страница X из Y · в выборке N · показано M`**.
- **Автовыбор**: при загрузке и при смене фильтра/поиска, если текущая сессия не входит в отфильтрованный список — выбирается первая сессия **текущей страницы** (или первая в выборке). При **смене только страницы** выбор **сохраняется**, если сессия всё ещё в фильтре (даже если строка не на текущей странице списка).

### Пустые состояния

- Если **нет строк после фильтров** — слева и справа **EmptyState** согласованный текст; иначе правая панель не остаётся в режиме «ничего не выбрано» при наличии данных.

### Backend (деталь сессии для полной истории в разумных пределах)

Файл `services/memory_observability_service.py`:

- `list_messages_for_session` для детали: **limit 500** (раньше 80).
- Превью текста сообщения для админ-детали: **`_preview_text(..., 4000)`** вместо 120.
- В ответ API: **`recent_turns`** — полная выборка из загруженных сообщений **без обрезки `[-24:]`**.

Контракт JSON полей не меняется; расширяется только длина массива и длина строк превью.

### Стили

`globals.css`: **`memory-memory-top-panels`**, **`memory-dialog-panel*`**, **`memory-dialog-table*`**, строка поиска **`memory-logs-filter-row`**.

---

## Текст для будущего PROJECT_STATE (не правили файл)

```text
AF modality console header contract:
left panel = session/general operational parameters;
right panel(s) = modality-specific telemetry;
body = primary modality object;
timeline/diagnostics = collapsible.
```

---

## Operator commands / next verification commands

```bash
date +%F
```

```bash
cd frontend/admin-ui && npm run build
```

Ручная проверка: Memory — верхние три панели, таблица диалога со скроллом, смена страницы с сохранением выбора если сессия вне текущей страницы списка, поиск и сброс; сравнить с RAG по структуре блоков.

### Commit

**Не выполнялся.**
