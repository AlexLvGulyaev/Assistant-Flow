# Session: Retrieval cache operational UI simplification (2026-05-17)

## Prompt (полная копия задачи)

# PEr07 — Retrieval Cache Operational UI Simplification Pass

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Если Auto явно не справляется с reasoning по нескольким React/TypeScript файлам — только тогда предложи оператору переключение.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Предыдущий pass успешно выполнил:
- runtime audit;
- duplicate audit;
- ownership model;
- source-of-truth analysis;
- partial cleanup Retrieval Settings.

Но сейчас Retrieval Settings всё ещё выглядит как инженерный diagnostic/config dump.

Для оператора и владельца системы по-прежнему неочевидно:

- какие параметры реально важны;
- что именно они меняют;
- что runtime;
- что diagnostics;
- что infrastructure-only;
- что future feature;
- что editable/non-editable;
- что влияет на HIT/MISS behavior;
- что влияет на invalidation.

То есть:
архитектурно стало лучше,
но operator UX всё ещё недостаточно понятен.

---

# Главная цель

Сделать Retrieval Cache panel:
- понятной;
- operational-first;
- explainable;
- пригодной для ручного управления и понимания поведения системы.

Не для разработчика retrieval backend.
А для владельца/оператора AF.

---

# Важно

Это НЕ backend pass.

НЕ:
- redesign cache architecture;
- новый runtime;
- Redis;
- PostgreSQL migration;
- новый diagnostics layer.

Это:
- operational UI simplification;
- information architecture cleanup;
- operator-oriented semantics pass.

---

# Обязательно прочитать

1. docs/cursor_sessions/2026-05-17_cache_config_audit_and_unification.md

2. docs/architecture/cache_layer_design.md

3. frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx

4. frontend/admin-ui/src/components/RetrievalCacheSettingsPanel.tsx

5. frontend/admin-ui/src/pages/RagPage.tsx

6. frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx

---

# Основная проблема

Сейчас UI всё ещё смешивает:

- runtime state;
- diagnostics;
- infrastructure;
- env/config;
- future features;
- implementation details.

В результате:
оператор вынужден “декодировать” panel semantics.

Это противоречит operational-first philosophy AF.

---

# Что нужно сделать

Нужна новая структура панели.

Не косметическая.

А semantic/operator-oriented.

---

# Целевая структура Retrieval Cache panel

## Блок 1. Статус retrieval cache

Максимально простой и человеческий.

Примерно:

### Retrieval cache

Ускоряет повторные retrieval-запросы.
Повторный запрос может выполняться значительно быстрее без повторного поиска в vector DB.

---

Статус:
- включён / выключен

Срок хранения:
- 24 часа

Storage:
- SQLite local cache

Инвалидация:
- reindex
- смена backend
- изменение retrieval settings

---

Важно:
если retrieval space изменился,
старый cache автоматически перестаёт использоваться.

---

Никаких:
- fingerprint;
- generation;
- env variable names;
- technical noise.

Это operator summary.

---

## Блок 2. Что влияет на cache

Новый explicit operator section.

Например:

### Что влияет на retrieval cache

Изменение следующих параметров создаёт новый retrieval fingerprint:

- retrieval backend;
- top_k;
- retrieval generation;
- embedding model.

После изменения этих параметров:
старые cache entries перестают использоваться.

---

Это очень важно для понимания HIT/MISS.

Сейчас UI это объясняет слишком неявно.

---

## Блок 3. Диагностика

Отдельный collapsible block.

Только здесь:
- generation;
- fingerprint basis;
- effective runtime values;
- namespace;
- cache path;
- read-only infrastructure values.

Название:
### Техническая диагностика retrieval cache

Сразу пометить:
"Раздел предназначен для диагностики и backend troubleshooting."

---

## Блок 4. Future features

ENABLE_ANSWER_CACHE сейчас выглядит как operational feature,
хотя фактически это future stub.

Нужно явно отделить.

Например:

### Будущие возможности

Answer cache:
- не используется в текущем runtime;
- зарезервировано для будущих optimization passes.

---

# Что нельзя делать

Нельзя:
- показывать raw env dump как основной UI;
- смешивать diagnostics и operator controls;
- использовать термины без объяснения;
- дублировать runtime state;
- показывать implementation details как primary information;
- превращать Retrieval Settings в engineering console.

---

# Что особенно важно

Оператор должен понимать:

1.
Что cache делает.

2.
Почему:
- MISS;
- HIT;
- invalidation.

3.
Что изменится при:
- смене top_k;
- reindex;
- смене backend.

4.
Что cache НЕ является source of truth.

5.
Что SQLite — acceleration layer.

---

# Дополнительная UX-задача

Проверить весь Retrieval Settings page на consistency.

Если рядом с Retrieval Cache есть другие overly-technical blocks:
- слегка упростить wording;
- но НЕ уходить в broad redesign.

Только consistency cleanup.

---

# Acceptance criteria

Pass считается успешным, если:

1. Retrieval Cache panel стала понятна оператору без чтения engineering docs.
2. Runtime / diagnostics / infrastructure visually separated.
3. ENABLE_ANSWER_CACHE больше не выглядит как active feature.
4. HIT/MISS semantics объяснимы через UI.
5. Retrieval invalidation semantics объяснимы через UI.
6. Нет duplicate information blocks.
7. Frontend build проходит.
8. Existing RAG diagnostics не сломаны.

---

# Session log

Создать:

docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_operational_ui_simplification.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. operator UX problems identified;
2. previous vs new structure;
3. removed technical noise;
4. runtime vs diagnostics separation;
5. explanation strategy;
6. future-feature handling;
7. screenshots/description if possible;
8. frontend build result;
9. git status.

---

# Operator commands

Добавить:
- frontend build;
- точечный rebuild admin-ui;
- UI acceptance checklist.

Использовать только:

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...

---

# Ответ в чат Cursor

В ответе предоставить только:

1. changed files;
2. new UI structure summary;
3. removed operator confusion points;
4. answer-cache handling result;
5. frontend build result;
6. remaining UX limitations;
7. git status.

Commit НЕ выполнять.

---

## Engineering log

### 1. Operator UX problems identified

- Смешение runtime, env dump, fingerprint и answer cache в одном визуальном уровне.
- Термины generation, fingerprint, `ENABLE_*`, AppConfig — требовали «декодирования».
- Answer cache выглядел как активная operational feature.
- HIT/MISS объяснялись только через технические bullet points.

### 2. Previous vs new structure

| Было | Стало |
|------|--------|
| SoT banner + «Операционное состояние» с generation/fingerprint/path | **Блок 1:** человеческий статус (вкл/выкл, TTL, SQLite, инвалидация) |
| Инвалидация с `namespace`, env names | **Блок 2:** «Что влияет» + HIT/MISS plain language |
| «Расширенная конфигурация (env)» наверху по смыслу | **Блок 3:** collapsible «Техническая диагностика» |
| Answer cache в runtime dl | **Блок 4:** «Будущие возможности» с badge «не в runtime» |

### 3. Removed technical noise (primary UI)

- `Source of truth` / AppConfig banner из primary view.
- generation, fingerprint, env keys, file path — только в diagnostics `<details>`.
- Answer cache убран из operational status row.

### 4. Runtime vs diagnostics separation

- Секции 1–2: operator-facing, без raw env.
- Секция 3: явная пометка troubleshooting; env mirror внутри.
- Секция 4: future stub isolated.

### 5. Explanation strategy

- Lead paragraph: что делает кэш и что он **не** SoT.
- TTL через `formatTtlHuman` (например «24 часа»).
- Факторы с текущими значениями backend/top_k где доступны из overview.
- HIT/MISS в выделенном callout.

### 6. Future-feature handling

- Answer cache: badge «не в runtime», пояснение про foundation; предупреждение если env flag true.

### 7. Screenshots / description

Скриншоты не снимались (headless). Визуально: 4 секции с разделителями, статус зелёный/серый, diagnostics collapsed by default.

### 8. Frontend build result

`npm run build` — OK (2026-05-17).

### 9. Git status

См. раздел Operator commands.

**Consistency:** `RetrievalSettingsPage` — описание SectionCard cache; блок «Системные пути» — русский summary (без redesign backend matrix).

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

### UI acceptance checklist

- [ ] Retrieval Settings → один блок «Retrieval cache», без generation/env наверху
- [ ] Статус: включён/выключен, TTL человекочитаемый, SQLite без пути в блоке 1
- [ ] «Что влияет» + HIT/MISS понятны без docs
- [ ] Diagnostics collapsed; env только внутри
- [ ] Answer cache в «Будущие возможности», не как active feature
- [ ] RAG diagnostics (badges/panel) без регрессии

### Git status

```bash
cd /opt/assistant-flow && git status --short
```
