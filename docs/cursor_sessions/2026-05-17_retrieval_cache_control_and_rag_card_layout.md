# Session: Retrieval cache control and RAG card layout (2026-05-17)

## Prompt
# PEr07 — Retrieval Cache ON/OFF Control and RAG Card Compact Layout

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Если Auto явно не справляется с React/TypeScript multi-file правками — только тогда предложи оператору переключение.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Продолжаем PEr07 / Retrieval Cache / Optimization sprint.

Текущее состояние:

1. В Retrieval Settings уже есть панель Retrieval Cache.
2. В RAG-консоли уже появились cache badges и cache diagnostics.
3. В текущем runtime `ENABLE_RETRIEVAL_CACHE=false`, поэтому RAG-сессии показывают N/A / нет данных.
4. N/A в данном случае не означает ошибку telemetry. Это означает, что retrieval cache выключен и не участвует в execution.
5. Визуально RAG-карточка после добавления cache telemetry стала перегруженной: верхняя часть съедает пространство, из-за чего вопрос/ответ и чанки уходят вниз.

Нужно сделать следующий bounded pass.

---

# Цели pass

## 1. Retrieval Settings

Сделать `ENABLE_RETRIEVAL_CACHE` управляемым параметром в UI.

Оператор должен иметь возможность включить/выключить retrieval cache через Retrieval Settings.

В UI использовать человекочитаемый toggle/state:

- OFF
- ON

а не raw true/false как основной визуальный язык.

Важно:
- если backend пока требует restart/recreate после изменения — UI должен честно показывать это;
- не делать вид, что изменение применяется live, если это не так;
- если в проекте уже есть platform_settings/runtime settings pattern — использовать его;
- если управляемость требует backend/API change — сделать минимально и аккуратно;
- не делать schema migration без необходимости.

---

## 2. RAG console cache state

Заменить N/A для выключенного retrieval cache на:

- OFF

Семантика:

- HIT = cache включён, lookup выполнен, entry найден;
- MISS = cache включён, lookup выполнен, entry не найден;
- OFF = retrieval cache выключен и не участвовал в execution;
- N/A оставить только для настоящего отсутствия данных / старых логов / unknown telemetry.

Важно:
не подменять OFF на MISS.
MISS и OFF — разные operational states.

---

## 3. RAG card compact layout

Перекомпоновать верхнюю часть RAG-карточки.

Текущая проблема:
- после добавления cache telemetry верхняя часть карточки стала слишком высокой;
- вопрос пользователя, ответ системы и чанки ушли вниз;
- основной смысл RAG-карточки стал хуже виден.

Нужно:
- сохранить пять информационных панелей;
- разместить их внутри примерно того же вертикального бюджета, который сейчас занимают панели 1+2 и 3;
- не добавлять новый высокий этаж;
- использовать горизонтальное перераспределение и компактную сетку;
- вернуть вопрос/ответ и чанки на привычное видимое место.

Операторская формула компоновки:

Было условно:
1(1) + 2(1) = 3(2)

Нужно:
1(1) + 2(1) = 3(2) = 4(3) + 5(3)

Смысл:
все пять информационных панелей должны уместиться по вертикали в тот размер, в котором сейчас находятся верхние панели, чтобы остальные компоненты карточки RAG не были вытеснены вниз.

---

# Важно по UI-стилю

Не добавлять explanatory prose.

Никаких:
- tutorial text;
- explanatory essays;
- help articles;
- “что такое cache”;
- длинных подсказок внутри operational panels.

Только:
- параметр → значение;
- badge;
- компактные подписи;
- существующий visual language AF.

---

# Обязательно прочитать

1. docs/cursor_sessions/2026-05-17_retrieval_cache_settings_cleanup.md

2. docs/cursor_sessions/2026-05-17_retrieval_cache_operational_ui_simplification.md

3. docs/cursor_sessions/2026-05-17_cache_observability_ui_pass.md

4. docs/architecture/cache_layer_design.md

5. frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx

6. frontend/admin-ui/src/components/RetrievalCacheSettingsPanel.tsx

7. frontend/admin-ui/src/pages/RagPage.tsx

8. frontend/admin-ui/src/components/CacheObservabilityBadge.tsx

9. frontend/admin-ui/src/components/RagCacheDiagnosticsPanel.tsx

10. frontend/admin-ui/src/utils/cacheObservability.ts

11. frontend/admin-ui/src/styles/globals.css

12. admin_api/routes/retrieval.py

13. utils/config.py

14. services/retrieval/runtime_manager.py / platform settings related files, если используются для runtime settings

---

# Scope A — Управляемый ENABLE_RETRIEVAL_CACHE

## Нужно выяснить

1. Где сейчас хранится `ENABLE_RETRIEVAL_CACHE`.
2. Есть ли существующий pattern runtime editable settings в Retrieval Settings.
3. Как top_k/backend уже меняются из UI.
4. Можно ли использовать тот же mechanism для retrieval cache enabled flag.

## Нужно реализовать

Если существующий механизм runtime settings подходит:

- добавить retrieval cache enabled в управляемые настройки;
- UI toggle ON/OFF;
- сохранение через existing API/settings path;
- отражение effective value в Retrieval Cache panel.

Если existing mechanism не подходит:

- сделать минимальный API/backend change;
- явно задокументировать, что именно меняется;
- не вводить скрытых источников истины.

## Важно

Если cache enabled всё ещё требует restart:
- показать compact badge/notice: `requires restart`;
- не обещать hot apply.

Если hot apply работает:
- показать effective status после сохранения.

---

# Scope B — OFF вместо N/A

В cache badge utility / RAG list / RAG detail:

- при явном disabled cache показывать OFF;
- при отсутствии telemetry в старых логах показывать N/A;
- при evaluation bypass показывать BYPASS;
- HIT/MISS оставить как есть.

Нужно аккуратно различить:

1. cache disabled by runtime config → OFF
2. cache bypass by evaluation policy → BYPASS
3. old log missing fields → N/A
4. cache enabled miss → MISS
5. cache enabled hit → HIT

---

# Scope C — RAG card panel layout

В RAG detail/card:

- сохранить compact operational density;
- не раздувать header/meta area;
- пять информационных панелей должны занимать примерно тот же vertical budget, что текущие верхние panels;
- question/answer должны вернуться выше;
- chunks не должны уходить далеко вниз.

Можно:
- использовать grid;
- уменьшить padding/gap;
- перегруппировать panels;
- сделать cache panel более компактной;
- перенести часть details в collapsed diagnostics.

Нельзя:
- делать гигантские text blocks;
- создавать новый большой нижний блок;
- ломать existing RAG diagnostics;
- прятать question/answer/chunks за дополнительным scroll без необходимости.

---

# Acceptance criteria

Pass считается успешным, если:

1. В Retrieval Settings retrieval cache можно включить/выключить через UI.
2. Основной вид использует ON/OFF, а не raw true/false.
3. Если изменение требует restart — это честно видно.
4. В RAG list/detail выключенный cache отображается как OFF, не N/A.
5. N/A остаётся только для настоящего отсутствия telemetry.
6. RAG-карточка стала компактнее.
7. Вопрос пользователя и ответ системы снова видны без сильного прокручивания.
8. Чанки поднялись ближе к привычному месту.
9. Нет explanatory prose в operational panels.
10. Frontend build проходит.
11. Если backend/API менялись — API smoke проходит.

---

# Session log

Создать:

docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_control_and_rag_card_layout.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. changed files;
2. как реализован ON/OFF control;
3. source of truth после изменения;
4. hot apply vs restart required;
5. cache badge state mapping;
6. RAG card layout changes;
7. что стало компактнее;
8. frontend build result;
9. API checks, если backend затронут;
10. remaining limitations;
11. git status.

---

# Operator commands / next verification commands

В конце session log добавить конкретные команды:

- frontend build;
- точечный rebuild admin-ui;
- rebuild/restart admin-api, если backend/API затронут;
- curl/API checks, если backend/API затронут;
- UI checklist;
- git status.

Использовать только portfolio stack форму:

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...

Не писать обобщённо `docker compose up -d --build` без `-p portfolio-test`.

---

# Ответ в чат Cursor

В ответе предоставить только:

1. changed files;
2. retrieval cache ON/OFF control result;
3. whether restart is required;
4. cache badge mapping result;
5. RAG card layout result;
6. frontend build result;
7. API check result, если применимо;
8. remaining limitations;
9. git status.

Commit НЕ выполнять.

---

## Engineering log

См. полный log в ответе чата; кратко: tuning API для `enable_retrieval_cache`, OFF badge, RAG grid compact, build OK.

## Operator commands

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-ui admin-api
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-ui admin-api
cd /opt/assistant-flow && git status --short
```
