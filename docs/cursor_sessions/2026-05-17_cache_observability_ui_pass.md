# Промпт для Cursor: Cache Observability UI Pass / PEr07

Рекомендуемый режим Cursor: Auto.

Если Auto явно не справляется с multi-file reasoning или TypeScript/React refactor, только тогда переключиться на Codex/Sonnet вручную. По умолчанию НЕ фиксировать frontier-модель, чтобы не расходовать API pool без необходимости.

Прочитай и выполни. Общаемся, комментарии и отчёты пишем строго на русском языке.

Продолжаем subsystem-scoped sprint:
PEr07 / Cache Layer / Retrieval Optimization для Assistant Flow.

Контекст:
уже выполнены:
1. architecture/design pass cache layer;
2. retrieval cache operationalization backend pass;
3. design pass cache observability console.

Теперь нужен первый bounded UI implementation pass.

ВАЖНО:
это НЕ новая большая страница и НЕ broad redesign.
Нужно реализовать минимальный operator-facing контур наблюдаемости cache в существующих Admin UI страницах.

==================================================
ЦЕЛЬ
==================================================

Сделать cache behavior видимым оператору в Admin UI:

- cache HIT / MISS / N/A;
- cache latency;
- retrieval generation;
- backend/fingerprint/key prefix;
- evaluation bypass policy;
- missing telemetry markers.

Идеальная проверка оператором после реализации:

1. задать RAG-запрос;
2. увидеть cache MISS;
3. повторить тот же запрос;
4. увидеть cache HIT;
5. изменить top_k/backend/reindex;
6. увидеть новый fingerprint/MISS;
7. открыть Evaluation/RAGAS и увидеть cache bypass.

==================================================
ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ
==================================================

1. PROJECT_STATE.md

2. docs/architecture/cache_layer_design.md

3. docs/architecture/cache_observability_console_design.md

4. docs/cursor_sessions/2026-05-17_retrieval_cache_operationalization_pass.md

5. docs/cursor_sessions/2026-05-17_cache_observability_console_design.md

6. Current frontend:
- frontend/admin-ui/src/pages/RagPage.tsx
- frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx
- frontend/admin-ui/src/pages/EvaluationPage.tsx
- frontend/admin-ui/src/pages/LogsPage.tsx
- frontend/admin-ui/src/api/client.ts
- frontend/admin-ui/src/styles/globals.css
- existing shared badges/components if present

7. Current backend/API:
- admin_api/routes/logs.py
- admin_api/routes/retrieval.py
- admin_api/routes/evaluation.py
- admin_api/deps.py
- services/rag_types.py
- services/evaluation_admin_service.py

==================================================
SCOPE
==================================================

Работаем только в пределах pass-1:

1. Retrieval Settings:
   добавить компактный cache status summary.

2. RAG page:
   добавить cache diagnostics mode/section:
   - badges в списке RAG-сессий;
   - detail block в выбранной RAG-сессии;
   - latency / backend / generation / key prefix;
   - N/A markers для старых логов без telemetry.

3. Evaluation page:
   добавить явный cache bypass indicator:
   - evaluation_cache_bypass;
   - evaluation_cache_policy;
   - объяснение: "кэш отключён для воспроизводимости оценки".

4. API/data:
   использовать существующие endpoints, если данных достаточно.
   Минимальные enrichments разрешены, но без schema migration.

==================================================
ЧАСТЬ 1. RETRIEVAL SETTINGS CACHE SUMMARY
==================================================

В Retrieval Settings добавить компактный блок:

Название:
"Кэш retrieval"

Поля:
- статус: включён / выключен / неизвестно;
- generation / revision;
- TTL, если доступен;
- backend/fingerprint basis, если доступен;
- короткая подсказка:
  "Кэш ускоряет повторный retrieval, но сбрасывается при изменении retrieval space."

Не делать:
- большой dashboard;
- графики;
- отдельную analytics систему.

Если часть полей недоступна:
показывать "нет данных" / "не собирается", а не скрывать поле.

==================================================
ЧАСТЬ 2. RAG PAGE CACHE DIAGNOSTICS
==================================================

В списке RAG-сессий добавить компактный cache badge:

Варианты:
- HIT
- MISS
- BYPASS
- N/A

Русская подпись рядом/tooltip:
- "кэш: hit"
- "кэш: miss"
- "кэш: bypass"
- "кэш: нет данных"

В detail выбранной RAG-сессии добавить блок:

"Диагностика кэша"

Поля:
- cache state;
- cache layer;
- cache latency ms;
- retrieval cache generation;
- retrieval cache backend;
- key hash prefix;
- fingerprint backend;
- skipped retrieval, если есть;
- invalidation reason, если есть.

Если поля отсутствуют:
показывать "нет данных в логе".

Важно:
cache block должен быть compact operational panel, не огромный JSON.

Raw JSON оставить collapsed.

==================================================
ЧАСТЬ 3. COMPARISON PANEL
==================================================

Если безопасно и без чрезмерного refactor:

Добавить в RAG detail компактный блок:

"Сравнение с похожим запросом"

Идея:
- найти предыдущую сессию в загруженном окне с тем же normalized/retrieval query или близким query text;
- показать:
  - previous cache state;
  - current cache state;
  - previous latency;
  - current latency;
  - delta.

Если такого совпадения нет:
показать "совпадающий предыдущий запрос не найден в текущем окне".

Если реализация требует сложного поиска или API:
не делать в этом pass, описать как next step.

==================================================
ЧАСТЬ 4. EVALUATION BYPASS INDICATOR
==================================================

В Evaluation page добавить явный indicator:

"Политика кэша: bypass"

Если evaluation_cache_bypass=true:
показывать:
"Кэш retrieval отключён для воспроизводимости оценки."

Если policy отсутствует:
показывать:
"Политика кэша не зафиксирована в данных."

Важно:
это должно быть видно оператору на detail уровне выбранного run/item, не только в raw JSON.

==================================================
ЧАСТЬ 5. UI STYLE
==================================================

Соблюдать existing AF operational UI:

- compact panels;
- no giant KPI bricks;
- no dashboard glam;
- dense operator console;
- consistent badges;
- Russian UI labels;
- technical keys не переводить, если это identifiers:
  - HIT/MISS можно оставить как badges;
  - execution_id;
  - top_k;
  - retrieval_cache_key_hash_prefix;
  - backend names.

==================================================
ЧАСТЬ 6. ACCEPTANCE CRITERIA
==================================================

Pass считается успешным, если:

1. В Retrieval Settings виден компактный статус retrieval cache.
2. В RAG list видны cache badges.
3. В RAG detail есть блок "Диагностика кэша".
4. Старые логи без cache telemetry явно показывают N/A / нет данных.
5. В Evaluation виден cache bypass indicator.
6. Frontend build проходит.
7. Backend не сломан.
8. Нет schema migration.
9. Нет broad redesign.
10. Session log создан и содержит этот prompt полностью.

==================================================
НЕ ДЕЛАТЬ
==================================================

НЕ делать:
- новую отдельную страницу Optimization;
- Redis;
- distributed cache;
- final answer cache;
- embedding cache;
- schema migration;
- broad UI redesign;
- новый analytics backend;
- heavy charts;
- unrelated cleanup.

==================================================
DELIVERABLES
==================================================

Создать session log:

docs/cursor_sessions/YYYY-MM-DD_cache_observability_ui_pass.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

В конец session log добавить:

1. changed files;
2. implemented UI changes;
3. API/data changes, если были;
4. cache fields displayed;
5. evaluation bypass UI result;
6. frontend build result;
7. warnings/limitations;
8. git status.

==================================================
ОТВЕТ
==================================================

В ответе предоставить только:

1. changed files;
2. implemented UI changes;
3. whether API changes were needed;
4. frontend build result;
5. remaining limitations;
6. git status.

Commit НЕ выполнять.

---

## changed files

- `frontend/admin-ui/src/utils/cacheObservability.ts` (new)
- `frontend/admin-ui/src/components/CacheObservabilityBadge.tsx` (new)
- `frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx` (new)
- `frontend/admin-ui/src/components/EvaluationCachePolicyPanel.tsx` (new)
- `frontend/admin-ui/src/pages/RagPage.tsx`
- `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx`
- `frontend/admin-ui/src/pages/EvaluationPage.tsx`
- `frontend/admin-ui/src/styles/globals.css`
- `admin_api/deps.py` (minimal: preserve evaluation_cache_* in log details)

## implemented UI changes

1. **Retrieval Settings** — блок «Кэш retrieval»: статус вкл/выкл, generation, TTL, backend fingerprint basis, подсказка про invalidation, ссылка на RAG.
2. **RAG** — badge HIT/MISS/BYPASS/N/A в списке сессий; панель «Диагностика кэша» в detail; блок «Сравнение с похожим запросом» по загруженному окну.
3. **Evaluation** — панель «Политика кэша» в detail turn и forensic item (bypass + policy или «не зафиксирована»).

## API/data changes, если были

- Минимально: `evaluation_cache_bypass` и `evaluation_cache_policy` добавлены в `_PRESERVED_DETAIL_KEYS` (`admin_api/deps.py`) для сохранения в `/api/logs/recent` при наличии в details.
- Новых endpoint и schema migration нет; UI читает `processing_logs.details` и evaluation `retrieval_diag`.

## cache fields displayed

- `retrieval_cache_hit` / `retrieval_cache_miss` → HIT/MISS/N/A
- `cache_layer`, `cache_latency_ms`
- `retrieval_cache_generation`, `retrieval_cache_backend`
- `retrieval_cache_key_hash_prefix`, `retrieval_cache_fingerprint_backend`
- `skipped_retrieval`, `cache_invalidation_reason` (с «нет данных в логе» при отсутствии)
- `evaluation_cache_bypass`, `evaluation_cache_policy` (Evaluation)

## evaluation bypass UI result

- При `evaluation_cache_bypass=true`: badge BYPASS + текст «Кэш retrieval отключён для воспроизводимости оценки» + policy key при наличии.
- Иначе: «Политика кэша не зафиксирована в данных» (production RAG turns без eval import).

## frontend build result

- `npm run build` в `frontend/admin-ui`: **успешно** (`tsc -b && vite build`).

## warnings/limitations

- Сравнение запросов ограничено сессиями в текущем окне загрузки (24h/48h/7d).
- Старые логи без cache telemetry показывают N/A / «нет данных в логе».
- `skipped_retrieval` и `cache_invalidation_reason` в `rag_answer_done` часто отсутствуют — отображаются как gap.
- Production RAG sessions не показывают BYPASS (только evaluation import path).

## git status

```
 M PROJECT_STATE.md
 M admin_api/deps.py
 M frontend/admin-ui/src/pages/EvaluationPage.tsx
 M frontend/admin-ui/src/pages/RagPage.tsx
 M frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
 ... (backend pass files from prior tasks)
?? docs/architecture/cache_observability_console_design.md
?? docs/cursor_sessions/2026-05-17_cache_observability_ui_pass.md
?? frontend/admin-ui/src/components/CacheObservabilityBadge.tsx
?? frontend/admin-ui/src/components/EvaluationCachePolicyPanel.tsx
?? frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx
?? frontend/admin-ui/src/utils/cacheObservability.ts
```
