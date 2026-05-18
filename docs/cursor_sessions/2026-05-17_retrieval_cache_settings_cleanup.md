# Session: Retrieval cache settings cleanup (2026-05-17)

## Prompt (полная копия задачи)

# PEr07 — Retrieval Cache Settings Cleanup & Operational Discipline Restoration

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Если Auto явно не справляется с reasoning по нескольким React/TypeScript файлам — только тогда предложи оператору переключение.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Предыдущий pass ушёл в documentation-heavy UI и нарушил established visual grammar AF.

Вместо:
- compact operational settings panel;
- parameter/value UI;
- cleanup дублей;

получились:
- большие explanatory text blocks;
- tutorial-style prose;
- excessive vertical space usage;
- documentation inside operational console.

Это НЕ соответствует Retrieval Settings design language.

---

# Главная цель

Вернуть Retrieval Cache panel к operational-console discipline AF.

Нужен:

- compact parameter/value panel;
- только необходимые параметры;
- отсутствие дублей;
- separation editable/runtime vs constants/infrastructure;
- visual consistency с Runtime tuning / Indexing tuning выше на странице.

---

# Критически важные правила

## 1. Retrieval Settings — НЕ documentation page

На панели НЕ должно быть:
- tutorial prose;
- HIT/MISS essays;
- explanatory paragraphs;
- architecture explanations;
- onboarding text;
- “что такое cache”;
- “SQLite acceleration layer” и т.п.

Settings panel:
- не user guide;
- не architecture article;
- не docs surface.

---

## 2. Operational style AF обязателен

Нужен compact operational UI:

parameter → value

в стиле:
- Runtime tuning;
- Indexing tuning;
- Backend settings;
- Logs/RAG operational cards.

---

## 3. Должны остаться только необходимые и достаточные cache-параметры

Не informational noise.
Не duplicate reflections.
Не decorative diagnostics.

Только параметры, реально относящиеся к retrieval cache runtime/control.

---

## 4. Дублей параметров быть не должно

Если параметр уже отображается:
- в diagnostics;
- в infrastructure;
- в system paths;
- в другой cache section,

он НЕ должен повторяться на основной operational panel.

---

## 5. Infrastructure/constants должны быть в collapsed technical area

Если параметр:
- read-only;
- infrastructure-only;
- path;
- namespace;
- backend implementation detail;
- troubleshooting detail,

то ему место:
- в collapsed diagnostics;
- либо в existing technical/system section.

НЕ в primary operational cache panel.

---

# Что должно остаться на основной Retrieval Cache panel

Только compact operational cache settings/state.

Примерный expected density:

- Retrieval cache: enabled/disabled
- TTL
- Retrieval generation
- Answer cache: disabled/reserved
- maybe cache namespace/fingerprint semantics IF действительно operationally important

Но:
- compactly;
- without prose;
- without explanations.

---

# Что должно исчезнуть

Удалить из primary UI:

- большие explanatory blocks;
- HIT/MISS textual explanations;
- “что влияет на retrieval cache” essay;
- SQLite explanations;
- architecture prose;
- repeated runtime semantics;
- repeated infrastructure values;
- duplicate technical reflections.

---

# Диагностика

Diagnostics оставить:
- compact;
- collapsed;
- engineering-oriented.

Без explanatory prose.

Только:
- parameter/value;
- technical state;
- troubleshooting info.

---

# Обязательно проверить

## 1. Нет ли повторного отображения:

- TTL
- generation
- cache path
- backend/fingerprint
- enable flags

между:
- operational panel;
- diagnostics;
- infrastructure sections.

---

## 2. Не дублирует ли diagnostics existing System paths/connectivity sections

---

## 3. Не осталось ли future stubs в primary operational area

ENABLE_ANSWER_CACHE не должен выглядеть как active runtime feature.

---

# Что НЕ делать

Нельзя:
- снова добавлять prose;
- писать explanatory descriptions;
- делать UX redesign;
- менять architecture/runtime;
- менять cache semantics;
- менять SQLite/PostgreSQL model;
- добавлять help texts ради “понятности”.

---

# Acceptance criteria

Pass считается успешным только если:

1. Retrieval Cache panel снова выглядит как часть AF operational console.
2. Нет giant text blocks.
3. Нет tutorial prose.
4. Нет duplicate parameters.
5. Editable/runtime vs constants separated.
6. Infrastructure-only values вынесены из основной панели.
7. Visual density restored.
8. Frontend build проходит.

---

# Обязательно посмотреть перед правками

1. Runtime tuning block
2. Indexing tuning block
3. Existing Logs/RAG cards

Retrieval Cache должен stylistically соответствовать им.

---

# Session log

Создать:

docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_settings_cleanup.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. removed prose blocks;
2. removed duplicate parameters;
3. retained operational parameters;
4. retained diagnostics parameters;
5. infrastructure-only parameters moved out;
6. final panel structure;
7. visual consistency notes;
8. frontend build result;
9. git status.

---

# Operator commands

Добавить:
- frontend build;
- точечный rebuild admin-ui;
- UI verification checklist.

Использовать только:

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...

---

# Ответ в чат Cursor

В ответе предоставить только:

1. changed files;
2. removed duplicate parameters;
3. removed prose sections;
4. retained operational parameters;
5. diagnostics structure;
6. frontend build result;
7. remaining limitations;
8. git status.

Commit НЕ выполнять.

---

## Engineering log

### 1. Removed prose blocks

- Lead paragraph про vector DB / PostgreSQL SoT.
- Секция «Статус retrieval cache» с bullet invalidation.
- Секция «Что влияет на retrieval cache» + HIT/MISS callout.
- Секция «Будущие возможности» с badge и warnings.
- Diagnostics warning prose и generation hint.
- Human-readable TTL (`formatTtlHuman`).

### 2. Removed duplicate parameters

| Параметр | Было | Стало |
|----------|------|--------|
| TTL | operational + diagnostics | operational only |
| generation | operational + diagnostics + env mirror | operational only |
| ENABLE_RETRIEVAL_CACHE | operational + diagnostics | operational only |
| CACHE_DB_PATH | diagnostics + System paths | System paths only |
| top_k | factors + diagnostics | Runtime tuning only |
| backend | factors + diagnostics | Active backend + diagnostics `FINGERPRINT_BACKEND` |

### 3. Retained operational parameters

- `ENABLE_RETRIEVAL_CACHE`
- `RETRIEVAL_CACHE_TTL_SECONDS`
- `RAG_RETRIEVAL_GENERATION`
- `ENABLE_ANSWER_CACHE` (compact: `false · reserved` / `true · not in hot path`)

### 4. Retained diagnostics parameters

- `NAMESPACE` (= retrieval)
- `FINGERPRINT_BACKEND`
- `EDITABLE_VIA_API`

### 5. Infrastructure-only moved out

- `CACHE_DB_PATH` — только в «Системные пути» (не дублируется в cache diagnostics).
- Raw env mirror block удалён из diagnostics.

### 6. Final panel structure

```
dl (4 rows, env chip, read-only inputs)
micro foot: env only · restart · link RAG
<details> Cache diagnostics (3 rows)
```

### 7. Visual consistency notes

- Тот же `retrieval-settings__kv--grid` + `retrieval-settings__ro` + `retrieval-settings__src` env chip, что Runtime/Indexing tuning.
- SectionCard description в стиле tuning cards (короткий English operational note).

### 8. Frontend build result

`npm run build` — OK (2026-05-17).

### 9. Git status

См. Operator commands.

---

## Operator commands / next verification commands

### Frontend build

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
```

### Rebuild admin-ui (portfolio)

```bash
cd /opt/assistant-flow
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui
```

### UI verification checklist

- [ ] Retrieval cache: 4 compact rows, без prose blocks
- [ ] TTL/generation не дублируются в diagnostics
- [ ] CACHE_DB_PATH только в System paths
- [ ] Answer cache value: `reserved` / `not in hot path`
- [ ] RAG diagnostics link в одной micro-строке
- [ ] Visual density ≈ Runtime tuning block

### Git status

```bash
cd /opt/assistant-flow && git status --short
```
