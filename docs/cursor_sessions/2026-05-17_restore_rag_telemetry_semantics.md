# PEr07 — Corrective Fix v3: Restore Telemetry Semantics Without Breaking 3-Column Layout

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Предыдущий pass частично исправил:
- OFF badge;
- 3-column header layout.

Но при этом была допущена серьёзная архитектурная ошибка:

compact layout был достигнут за счёт удаления operational telemetry.

Это НЕ соответствует UI contract Assistant Flow.

---

# Обязательно перечитать перед работой

1. docs/architecture/*operational-console-ui-contract*
2. PROJECT_STATE.md — UI / Operational Console Standards
3. frontend/admin-ui/src/pages/RagPage.tsx
4. frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx
5. frontend/admin-ui/src/styles/globals.css

---

# Главная проблема текущей версии

Cursor перепутал:

compactness != telemetry reduction

Задача была:
- сохранить observability richness;
- уменьшить vertical footprint через grid/layout/density.

Вместо этого:
- были удалены operational fields;
- comparison semantics сломана;
- cache diagnostics превратилась в декоративную заглушку.

---

# Часть A. Вернуть потерянную telemetry

## Retrieval panel

Нельзя было удалять ключевые operational retrieval fields.

Вернуть из прежней версии необходимые и достаточные поля retrieval diagnostics.

Минимально должны снова присутствовать:

- active backend;
- readiness;
- chunks;
- top_k;
- retrieved;
- in context;
- filtered;
- sources;
- context chars;
- embedding model;
- history/follow-up flags, если они раньше были operationally visible.

Главное:
Retrieval panel должна снова быть observability panel, а не short card.

---

# Часть B. Исправить Cache diagnostics semantics

## Сейчас неправильно

Сейчас UI показывает:

- state = OFF
- prev = OFF
- current = OFF
- Δ ms = -315

Это semantically invalid.

Если cache subsystem OFF:
- cache comparison metrics не вычисляются;
- cache latency delta не имеет смысла.

---

# Правильная логика

## Когда cache OFF

Comparison panel должна:

- либо показывать OFF;
- либо "comparison unavailable";
- либо скрывать numeric comparison entirely.

Но НЕ показывать вычисленную delta latency.

## Когда cache ON

Только тогда разрешены:
- prev latency;
- current latency;
- delta;
- HIT/MISS transitions.

---

# Часть C. Не удалять telemetry ради layout

## Важно

3-column layout сохраняем.

Но compactness достигается:

- плотной KV-разметкой;
- grid balancing;
- column sizing;
- typography;
- spacing;
- vertical density.

НЕ:
- удалением параметров;
- урезанием observability;
- превращением panels в пустые заглушки.

---

# Часть D. Как должна выглядеть верхняя зона

Структура сохраняется:

Column 1:
- Session
- Quality

Column 2:
- Retrieval

Column 3:
- Cache
- Comparison

Но:
- Retrieval должен снова содержать meaningful telemetry;
- Cache/Comparison должны быть компактными, но semantic-rich;
- Question/Answer/chunks всё ещё должны оставаться высоко.

---

# Часть E. Что делать с лишними полями

Если реально не хватает места:

1. Не удалять поля silently.
2. Переносить второстепенные diagnostics в collapsed technical details.
3. В верхней зоне оставлять именно operationally valuable telemetry.

---

# Acceptance criteria

Pass считается успешным только если:

1. OFF badge остаётся корректным.
2. 3-column layout сохраняется.
3. Retrieval panel снова содержит полноценную retrieval telemetry.
4. Retrieval больше не выглядит artificially amputated.
5. Cache diagnostics снова meaningful.
6. При OFF cache comparison НЕ показывает numeric delta.
7. OFF-state semantic consistency восстановлена.
8. Нет contradictory states.
9. Question/Answer/chunks остаются высоко.
10. Нет второго ряда panels.
11. Frontend build OK.

---

# Session log

Создать:

docs/cursor_sessions/YYYY-MM-DD_restore_rag_telemetry_semantics.md

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. Какие retrieval fields были возвращены;
2. Почему их удаление было ошибкой;
3. Как исправлена comparison semantics;
4. Как теперь определяется OFF-state;
5. Какие comparison states существуют;
6. Final header structure;
7. Frontend build result;
8. Git status.

---

# Operator commands

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build

cd /opt/assistant-flow

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui

git status --short
```

---

# Ответ в чат Cursor

Только:

1. restored telemetry fields;
2. comparison semantics fix;
3. changed files;
4. final OFF/HIT/MISS logic;
5. frontend build result;
6. remaining limitations;
7. git status.

Commit НЕ выполнять.

---

## Engineering log (2026-05-17)

### 1. Возвращённые retrieval fields

В header panel **Retrieval** (col 2) восстановлены поля, убранные в pass v2:

- Отфильтровано (`filteredCount`)
- Реплик истории (`historyTurnsUsed`)
- Follow-up (`followupDetected`)
- Тримминг истории (`historyTrimmingApplied`)
- Коллекция / метка (`collectionName`)

Ранее уже присутствовали: backend, readiness, chunks, top_k, retrieved, in context, sources, context chars, embedding model.

### 2. Почему удаление было ошибкой

UI contract operational console требует **observability richness** в header: compactness достигается grid/density, а не silent removal полей. Урезание Retrieval до «short card» ломало операторскую диагностику (фильтрация, история, коллекция) без переноса в равноценную видимую зону.

### 3. Comparison semantics

- Добавлены `isCacheLookupActive()` и `isCacheSessionComparisonAllowed()` в `cacheObservability.ts`.
- `RagCacheComparePanel`: Δ retrieval ms вычисляется **только** если обе сессии в окне имеют state `hit` или `miss`.
- При `off` / `bypass` / `na` или смешанных парах: **н/д** вместо числа + footnote «сравнение кэша недоступно (OFF)» или «нет HIT/MISS».

### 4. OFF-state

- Per-session: `retrieval_cache_disabled` / wrapper hints → `off`; `evaluation_cache_bypass` → `bypass`.
- Global: `resolveCacheDisplayState(..., retrievalCacheGloballyEnabled: false)` → badge **OFF** (не N/A).

### 5. Comparison states

| prev | cur | Δ ms | Примечание |
|------|-----|------|------------|
| hit/miss | hit/miss | да | сравнение разрешено |
| off/bypass/na | * | н/д | cache не участвовал |
| * | off/bypass/na | н/д | footnote OFF / нет HIT/MISS |
| — | — | — | «нет пары в окне» |

### 6. Final header structure

Один row `modality-ops-panels--rag-header-grid` (3 col):

1. Session + Quality  
2. Retrieval (полная KV telemetry)  
3. Cache + Comparison (stack)

Q/A/chunks сразу под grid. Collapsed «Retrieval / cache (доп.)» удалён — дубли убраны; cache extras в panel «Кэш».

### 7. Cache panel enrichment

`RagCacheDiagnosticsPanel`: generation, fingerprint_backend, key_hash_prefix, invalidation_reason, skipped_retrieval.

### 8. CSS

`max-height` header grid: `36vh/340px` → `42vh/400px` под расширенный Retrieval без internal scroll KV.

### 9. Frontend build

```
cd frontend/admin-ui && npm run build
→ OK (tsc -b && vite build)
```

Docker compose build/up не запускались в этом pass.

### 10. Changed files (этот pass)

- `frontend/admin-ui/src/pages/RagPage.tsx`
- `frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx`
- `frontend/admin-ui/src/utils/cacheObservability.ts`
- `frontend/admin-ui/src/styles/globals.css`
- `docs/cursor_sessions/2026-05-17_restore_rag_telemetry_semantics.md`

### 11. Git status

См. `git status --short` в ответе чата; commit не выполнялся.
