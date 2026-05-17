# Промпт для Cursor: финальная полировка названий в «Анализе качества RAG»

```text
Используй Codex 5.3.

Прочитай и выполни. Общаемся и пишем комментарии/отчеты строго на русском языке.

Нужно выполнить финальную точечную полировку названий в Admin UI Assistant Flow для раздела «Анализ качества RAG».

Контекст:
Раздел Evaluation уже почти полностью русифицирован и приведен к operational-style UI.
Остались две маленькие несогласованности:
1. пункт главного меню слева всё еще называется `Evaluation`;
2. заголовок карточки выбранного набора показывает только техническое имя набора, например `ui-10-turns`, без поясняющих слов.

==================================================
ЗАДАЧИ
==================================================

1. Пункт главного меню
--------------------------------------------------

Сейчас:
`Evaluation`

Сделать:
`Анализ RAG`

Причина:
- коротко;
- помещается в левое меню;
- соответствует заголовку страницы «Анализ качества RAG»;
- не перегружает боковое меню длинной формулировкой.

==================================================

2. Заголовок карточки выбранного набора анализа
--------------------------------------------------

Сейчас:
`ui-10-turns`
или другое пользовательское/техническое имя набора.

Сделать:
`Анализ набора: <имя набора>`

Примеры:
- `Анализ набора: ui-10-turns`
- `Анализ набора: Weaviate c1000 k3`
- `Анализ набора: Negative-answer кейсы`

Важно:
- само имя набора не менять;
- только добавить понятный префикс в UI;
- если имя отсутствует и используется fallback shortId, префикс также должен применяться.

==================================================
НЕ ТРОГАТЬ
==================================================

Не менять:
- API;
- схемы данных;
- RAGAS logic;
- retrieval logic;
- execution_id;
- top_k;
- fallback;
- метрики;
- логику импорта;
- логику именования наборов в БД.

Только UI-тексты.

==================================================
SESSION LOGGING
==================================================

Создай session log:

`docs/cursor_sessions/2026-05-16_evaluation_final_label_polish.md`

В начало session log полностью помести этот prompt.

В конец добавь:
1. измененные файлы;
2. что переименовано;
3. были ли CSS/API/backend изменения;
4. команды проверки;
5. результат build/typecheck;
6. git status.

Commit НЕ выполнять.

==================================================
ОТВЕТ
==================================================

В ответе предоставить только:
1. список измененных файлов;
2. краткое описание изменений;
3. были ли CSS/API/backend изменения;
4. команды проверки;
5. git status.
```

## Выполнение

### 1) Измененные файлы
- `frontend/admin-ui/src/navigation/routes.ts`
- `frontend/admin-ui/src/pages/EvaluationPage.tsx`
- `docs/cursor_sessions/2026-05-16_evaluation_final_label_polish.md`

### 2) Что переименовано
- Пункт главного меню:
  - `Evaluation` -> `Анализ RAG`
- Заголовок карточки выбранного набора:
  - `{run.name || shortId(run.id)}` -> `Анализ набора: {run.name || shortId(run.id)}`

### 3) Были ли CSS/API/backend изменения
- CSS: нет
- API: нет
- backend: нет

### 4) Команды проверки
- `cd "/opt/assistant-flow/frontend/admin-ui" && npm run build`
- `git status --short`

### 5) Результат build/typecheck
- Build/typecheck успешен:
  - `tsc -b` без ошибок
  - `vite build` успешно (`✓ built in 5.02s`)

### 6) Git status
```text
 M frontend/admin-ui/src/components/StatusBadge.tsx
 M frontend/admin-ui/src/navigation/routes.ts
 M frontend/admin-ui/src/pages/EvaluationPage.tsx
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
?? docs/cursor_sessions/2026-05-15_rag_memory_leakage_diagnostic.md
?? docs/cursor_sessions/2026-05-15_ragas_negative_absence_inconsistency_diagnostic.md
?? docs/cursor_sessions/2026-05-16_evaluation_analysis_final_russification.md
?? docs/cursor_sessions/2026-05-16_evaluation_analysis_run_panel_cleanup.md
?? docs/cursor_sessions/2026-05-16_evaluation_analysis_scroll_and_named_runs.md
?? docs/cursor_sessions/2026-05-16_evaluation_recent_rag_turns_ui_russification.md
```
