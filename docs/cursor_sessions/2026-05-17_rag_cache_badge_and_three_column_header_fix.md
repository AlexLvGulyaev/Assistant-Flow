# Session: RAG cache badge and three-column header fix v2 (2026-05-17)

# PEr07 — Corrective Fix v2: RAG Header Grid by AF UI Contract + OFF Badge

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Задача точечная: исправить невыполненные acceptance criteria предыдущего pass.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Предыдущая попытка исправления RAG-card layout снова была рискованной, потому что не была жёстко привязана к уже зафиксированному UI contract Assistant Flow.

Перед правками ОБЯЗАТЕЛЬНО прочитать:

1. `docs/architecture/2026-05-14_operational-console-ui-contract.md`
   или фактический файл с этим содержанием, если он лежит в другом каталоге;
2. `PROJECT_STATE.md`, раздел `UI / Operational Console Standards`;
3. `frontend/admin-ui/src/pages/RagPage.tsx`;
4. `frontend/admin-ui/src/styles/globals.css`;
5. `frontend/admin-ui/src/utils/operationalConsoleUi.ts`.

Если файл `2026-05-14_operational-console-ui-contract.md` отсутствует в `docs/architecture`, найти его по репозиторию:

```bash
find . -iname '*operational-console-ui-contract*' -o -iname '*ui-contract*'
```

Без прочтения UI contract правки НЕ начинать.

---

# Ключевые правила из UI contract, которые нельзя нарушать

1. Правая часть operational console — это постоянная карточка выбранного айтема.
2. Верх карточки — информационные панели с layout-математикой.
3. Для RAG действует принцип row balancing:
   - старый стандарт: `P1 + P2 = P3`;
   - новый случай с cache должен расширить этот принцип без увеличения высоты верхней зоны.
4. Внутри панелей:
   - НЕ использовать `justify-content: space-between`;
   - НЕ растягивать текст по высоте;
   - KV-list идёт сверху вниз;
   - пустое место допустимо снизу.
5. После верхних панелей главным визуальным фокусом должны быть:
   - вопрос пользователя;
   - ответ системы;
   - найденные чанки.
6. Главный контент нельзя вытеснять вниз разросшимися header panels.

---

# Что сейчас неправильно

По текущему UI видно:

1. В RAG list и RAG detail всё ещё показывается `N/A`, хотя retrieval cache выключен.
2. `N/A` в этом случае неверен: это не missing telemetry, а disabled subsystem.
3. Верхняя часть RAG-card скомпонована неверно:
   - фактически осталась старая двухколоночная структура;
   - Retrieval panel стала высокой башней с собственным скроллом;
   - Cache и Comparison выглядят как маленький подвал под Retrieval;
   - это НЕ соответствует задаче оператора.
4. Вопрос/ответ и чанки всё ещё вытеснены вниз.

---

# Часть A. OFF вместо N/A при выключенном retrieval cache

## Требуемая семантика badges

- `HIT` — cache включён, lookup выполнен, запись найдена.
- `MISS` — cache включён, lookup выполнен, запись не найдена.
- `OFF` — retrieval cache выключен и не участвовал в execution.
- `BYPASS` — cache bypass из-за evaluation/RAGAS policy.
- `N/A` — только старые логи или действительно неизвестная telemetry.

## Важно

Если global/effective cache config показывает `enable_retrieval_cache=false`,
то RAG list и RAG detail должны показывать `OFF`, а не `N/A`.

`N/A` нельзя использовать как замену OFF.

## Проверить файлы

- `frontend/admin-ui/src/utils/cacheObservability.ts`
- `frontend/admin-ui/src/components/CacheObservabilityBadge.tsx`
- `frontend/admin-ui/src/pages/RagPage.tsx`

---

# Часть B. Исправить RAG-card header layout строго по 3-колоночной сетке

## Самое важное

Нужен НЕ второй ряд.

Нужна одна верхняя зона карточки, один общий row, три вертикальных столбца.

То есть верхняя зона должна выглядеть логически так:

```text
┌─────────────────────┬─────────────────────┬─────────────────────┐
│ Column 1            │ Column 2            │ Column 3            │
│ Session             │ Retrieval           │ Cache               │
│ Quality             │                     │ Comparison          │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

Это один верхний row из трёх columns.

НЕ делать:

```text
Session + Retrieval
Quality
Cache + Comparison
```

НЕ делать:

```text
Session + Retrieval
Cache + Comparison
```

НЕ делать:

```text
Session + Quality | Retrieval
                  | Cache + Comparison below Retrieval
```

## Layout math

Целевая математика:

```text
Column 1 height = Column 2 height = Column 3 height
Column 1 = Session + Quality
Column 2 = Retrieval
Column 3 = Cache + Comparison
```

То есть это развитие старого RAG-принципа `P1 + P2 = P3`, но теперь:

```text
(Session + Quality) = Retrieval = (Cache + Comparison)
```

Все три столбца должны находиться в одном верхнем ряду.

## Вертикальный бюджет

Все пять информационных панелей должны уместиться по вертикали примерно в тот размер, который раньше занимали верхние RAG panels до добавления cache.

Нельзя увеличивать высоту верхней зоны так, чтобы:
- вопрос пользователя;
- ответ системы;
- найденные чанки

уезжали вниз.

---

# Часть C. Как добиться компактности без поломки смысла

Если Retrieval panel слишком длинная:

1. Не делать ей отдельный внутренний scrollbar в верхней зоне.
2. Не растягивать её вниз.
3. Сократить набор полей в верхней Retrieval panel до необходимых.
4. Низкоприоритетные технические поля перенести в existing collapsed technical/session snapshot, а не держать в header.
5. Сохранять dense KV-list.

Пример: в верхней Retrieval panel достаточно оставить ключевые operational values:
- active backend;
- readiness;
- chunks;
- top_k;
- retrieved/context count;
- sources;
- context chars;
- embedding model.

Если есть лишние поля, которые не помещаются, перенести их в collapsed diagnostics ниже.

---

# Часть D. Запреты

НЕ делать:

- второй ряд панелей;
- большой нижний row;
- Cache/Comparison как подвал Retrieval panel;
- Retrieval panel с длинным внутренним скроллом;
- explanatory prose;
- tutorial text;
- broad redesign;
- backend changes;
- API changes;
- changes to Retrieval Settings;
- changes to cache runtime semantics.

Это corrective frontend layout pass.

---

# Acceptance criteria

Pass считается успешным только если:

1. В RAG list при выключенном retrieval cache отображается `OFF`.
2. В RAG detail при выключенном retrieval cache отображается `OFF`.
3. `N/A` остаётся только для old/missing telemetry.
4. Верхняя зона RAG-card — один row из трёх columns.
5. Column 1 содержит Session + Quality.
6. Column 2 содержит Retrieval.
7. Column 3 содержит Cache + Comparison.
8. Column heights визуально сбалансированы.
9. Cache/Comparison не являются подвалом Retrieval.
10. Retrieval panel не превращается в высокую башню.
11. Вопрос пользователя и ответ системы видны сразу под header area.
12. Найденные чанки поднялись ближе к привычному месту.
13. Нет explanatory prose.
14. Frontend build OK.

---

# Обязательно проверить перед ответом

После правок Cursor должен сам визуально оценить DOM/layout по коду:

- есть ли ровно 3 колонки в header grid;
- нет ли второго row;
- не вложены ли Cache/Comparison внутрь Retrieval column;
- нет ли внутреннего скролла на Retrieval panel, если его раньше не было по стандарту;
- не уехали ли Question/Answer ниже из-за header height.

---

# Session log

Создать:

`docs/cursor_sessions/YYYY-MM-DD_rag_cache_badge_and_three_column_header_fix.md`

Дата:
`date +%F`

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. Подтверждение, что прочитан Operational Console UI contract.
2. Какие правила contract применены.
3. Root cause: почему OFF не показывался.
4. Root cause: почему layout был неверным.
5. Changed files.
6. Final badge mapping.
7. Final 3-column header structure.
8. Какие поля оставлены в верхней Retrieval panel.
9. Какие поля перенесены/оставлены в collapsed diagnostics, если применимо.
10. Frontend build result.
11. Git status.

---

# Operator commands / next verification commands

Добавить:

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
cd /opt/assistant-flow
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui
git status --short
```

---

# Ответ в чат Cursor

В ответе предоставить только:

1. UI contract read confirmation;
2. root cause OFF badge;
3. root cause layout;
4. changed files;
5. final badge mapping;
6. final 3-column header structure;
7. frontend build result;
8. remaining limitations;
9. git status.

Commit НЕ выполнять.

---

## Engineering log

### 1. UI contract

Прочитан `docs/architecture/2026-05-14_operational-console-ui-contract.md`: row balancing, KV сверху вниз, без space-between, главный контент ниже header.

### 2. Правила contract

- Один верхний row, равные колонки по высоте.
- RAG: (Session+Quality) = Retrieval = (Cache+Comparison).
- Без внутреннего scroll в header panels.
- Фокус на Q/A/chunks.

### 3. Root cause OFF

`cacheStateFromDetailsPool` → `na` без `retrieval_cache_disabled` в старых логах; global `enable_retrieval_cache=false` не учитывался.

### 4. Root cause layout

Использовался `rag-balanced` (2 col): слева Session+Quality, справа Retrieval + cache row снизу — нарушение 3-column contract.

### 5. Changed files

- `cacheObservability.ts`, `RagPage.tsx`, `RagCacheDiagnosticsPanel.tsx`, `globals.css`, session log.

### 6. Badge mapping

| Условие | Badge |
|---------|--------|
| bypass | BYPASS |
| retrieval_cache_disabled / global off / no wrapper | OFF |
| hit | HIT |
| miss | MISS |
| unknown old log | N/A |

### 7. 3-column structure

`modality-ops-panels--rag-header-grid`: col1 Session+Quality, col2 Retrieval, col3 Cache+Compare (stack).

### 8. Retrieval header fields

backend, readiness, collection count, top_k, found, in context, sources, context chars, embedding model.

### 9. Collapsed extras

`Retrieval / cache (доп.)`: filtered, history, follow-up, trimming, collection, fingerprint_backend.

### 10. Frontend build

`npm run build` — OK.

### 11. Git status

`git status --short` в Operator commands.

---

## Operator commands

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui
git status --short
```
