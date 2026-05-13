# Engineering log: portfolio Docker Compose contour + Cursor log operator commands

**Дата (`date +%F`):** `2026-05-13`

## Полный текст prompt

```text
Cursor, нужно обновить PROJECT_STATE.md и operational rules после инцидента с параллельными Docker Compose контурами.

Обязательное правило:
создай engineering log:

`docs/cursor_sessions/YYYY-MM-DD_portfolio-compose-contour-operational-rule.md`

Дата:

```bash
date +%F
```

В log включить:

* полный текст этого prompt;
* workspace snapshot;
* git status before/after;
* что изменено в PROJECT_STATE;
* affected files;
* operational implications;
* commands policy;
* commit НЕ выполнять.

Задача 1. Усилить PROJECT_STATE operational rule.

В PROJECT_STATE уже есть правило, что primary operational contour — portfolio / GitHub container. Нужно append-only добавить отдельный явный блок большими заметными формулировками:

# CRITICAL OPERATIONAL RULE — DOCKER COMPOSE PROJECT NAME

Смысл:

1. Единственный canonical contour для разработки / runtime / smoke / GitHub portfolio:
   `portfolio-test-*`

2. Все команды Docker Compose для portfolio stack ОБЯЗАТЕЛЬНО запускать только с project name:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

3. Запрещено запускать portfolio compose без `-p portfolio-test`, потому что Docker Compose возьмёт project name из директории `/opt/assistant-flow` и создаст параллельный контур:

```text
assistant-flow-postgres-1
assistant-flow-weaviate-1
assistant-flow-assistant-flow-1
assistant-flow-admin-api-1
```

4. Такой параллельный контур опасен:

* занимает те же ports: 5433, 8089, 8600 и др.;
* может использовать другие volumes;
* может поднять другую PostgreSQL;
* может привести к тестированию не той БД;
* может привести к ложным выводам по Memory/RAG/Admin UI;
* может сломать reproducibility.

5. Если обнаружены `assistant-flow-*` контейнеры, а работа должна идти в portfolio contour, их нужно остановить:

```bash
docker ps --format "{{.Names}}" | grep '^assistant-flow-' | xargs -r docker stop
```

6. Если обнаружены старые/дублирующие `portfolio-test-*` контейнеры перед clean rebuild, корректная команда — не создавать новый project name, а пересобрать тот же project:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

7. Проверка активного контура:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Ожидаемый canonical prefix:
`portfolio-test-`

Задача 2. Добавить обязательное правило для будущих Cursor session logs.

В PROJECT_STATE / Team Workflow / Operational Rules append-only зафиксировать:

В конце каждого Cursor engineering log после выполнения prompt должен быть раздел:

## Operator commands / next verification commands

В этом разделе Cursor обязан дать:

* точную команду rebuild/recreate, если изменения требуют пересборки;
* точные docker exec smoke commands, если нужны runtime tests;
* curl/API checks, если затронут Admin API;
* npm build command, если затронут frontend;
* git status command;
* предупреждение, если host-level test недостаточен и нужен контейнерный прогон.

Правило:
для DB/RAG/runtime проверок использовать только canonical portfolio contour:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python <script>
```

Запрещено писать обобщённые команды вида:

```bash
docker compose up -d --build
```

без `-p portfolio-test`, если речь о portfolio stack.

Задача 3. Не переписывать старые разделы.
Добавить append-only блоки, сохранив numbering/chonology/style.

Задача 4. После изменений:

* показать path engineering log;
* показать git status;
* commit НЕ выполнять.
```

## Workspace snapshot

Корень `/opt/assistant-flow` (фрагмент `ls -1 | head -40`):

```text
Dockerfile
PROJECT_STATE.md
README.md
__pycache__
_test_chroma
admin_api
admin_ui
assistant-flow.zip
core
dashboard.py
data
database
docker-compose.assistant.yml
docker-compose.portfolio.yml
docs
evaluation
frontend
interfaces
legacy
main.py
outputs
providers
repositories
requirements.txt
run_admin_api.py
run_telegram_bot.py
scripts
services
storage
utils
Текстовый документ.txt
```

## Git status

### Before (начало сессии по этому prompt)

```text
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/app.py
 ... (прочие уже существовавшие локальные изменения; см. историю сессии)
```

Полный снимок «до» совпадает с состоянием дерева до правок **только** `PROJECT_STATE.md` и добавления этого файла лога; прочие `M`/`??` файлы не относились к данному prompt.

### After

```text
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/app.py
 M admin_api/deps.py
 M frontend/admin-ui/src/App.tsx
 M frontend/admin-ui/src/api/client.ts
 M frontend/admin-ui/src/navigation/routes.ts
 M frontend/admin-ui/src/pages/RagPage.tsx
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
 M interfaces/telegram_bot.py
 M repositories/processing_logs_repository.py
 M repositories/session_repository.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/retrieval_cache_key.py
 M services/chat_session_service.py
 M services/memory/conversation_memory_service.py
 M services/rag_query_service.py
 M services/rag_types.py
 M utils/config.py
 M utils/telegram_user_state.py
?? admin_api/routes/sessions.py
?? docs/cursor_sessions/2026-05-13_PROJECT_STATE_section-47-pe02-retrieval-backlog.md
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? docs/cursor_sessions/2026-05-13_memory-observability-and-sessions-ui.md
?? docs/cursor_sessions/2026-05-13_memory-v1-operational-stabilization.md
?? docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md
?? docs/cursor_sessions/2026-05-13_memory-v1_1-retrieval-aware-context.md
?? docs/cursor_sessions/2026-05-13_portfolio-compose-contour-operational-rule.md
?? frontend/admin-ui/src/pages/MemoryPage.tsx
?? scripts/test_memory_observability_admin_smoke.py
?? scripts/test_memory_v1_1_conversational_assembly_smoke.py
?? scripts/test_memory_v1_contamination_smoke.py
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? scripts/test_retrieval_backend_identity_smoke.py
?? services/conversational_context_assembly.py
?? services/memory_observability_service.py
```

**Commit не выполнялся.**

## Что изменено в PROJECT_STATE

| Место | Содержание |
|-------|------------|
| **§13 Operational Rules** | Append: подраздел про portfolio stack, запрет обобщённого `docker compose up` без `-p portfolio-test`, обязательный хвост engineering logs с разделом `## Operator commands / next verification commands`, отсылка к **§20** и **§54**. |
| **§20 Team Workflow** | Append: полное правило для Cursor engineering logs (заголовок раздела, перечень обязательных команд, канонический `docker exec`, запрет голого `docker compose up`). |
| **§28** | **§28.5** — краткая фиксация invariant project name + ссылка на **§54**. |
| **§32** | Append: уточнение после инцидента — всегда `COMPOSE_BAKE=false`, `-p portfolio-test`, `-f docker-compose.portfolio.yml`; ссылка на **§54**. |
| **§54** (новый, после §53) | Полный блок **CRITICAL OPERATIONAL RULE — DOCKER COMPOSE PROJECT NAME** (пункты 1–7 из prompt). |

Нумерация **§53 → §54** сохранена в хронологическом порядке (новый материал после существующего §53).

## Affected files

- `PROJECT_STATE.md`
- `docs/cursor_sessions/2026-05-13_portfolio-compose-contour-operational-rule.md` (этот файл)

## Operational implications

- Операторы и Cursor должны считать **`portfolio-test-`** единственным эталонным префиксом для portfolio stack; любой **`assistant-flow-*`** параллельный стек на тех же портах — инцидентный режим.
- Engineering logs становятся **исполняемыми чеклистами**: в конце обязателен блок команд для верификации без двусмысленности.
- Старый контур **`docker-compose.assistant.yml`** в §13/§16 **не удалён** — остаётся для legacy server workflow; правило **§54** относится к **portfolio** файлу.

## Commands policy

- **Portfolio:** только  
  `COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build`  
  и smoke через  
  `docker exec portfolio-test-assistant-flow-1 python <script>`.
- **Не использовать** для portfolio инструкцию `docker compose up -d --build` без `-p portfolio-test`.
- Остановка ошибочного контура:  
  `docker ps --format "{{.Names}}" | grep '^assistant-flow-' | xargs -r docker stop`  
  (с осторожностью в shared production).

## Operator commands / next verification commands

- **Пересборка / подъём canonical portfolio stack (после изменений только в документации пересборка не обязательна):**

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

- **Проверка, какой контур реально активен (обязательно перед DB/RAG smoke):**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Ожидаемые имена для portfolio work: префикс **`portfolio-test-`**. Если видны лишние **`assistant-flow-*`** на конфликтующих портах — см. политику остановки в **§54.5** `PROJECT_STATE.md`.

- **Пример smoke внутри приложения (если нужна runtime-проверка; подставить реальный скрипт):**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_memory_v1_contamination_smoke.py
```

**Предупреждение:** проверки Memory/RAG/Admin API с `DATABASE_URL` и Chroma **недостаточно** гонять только на хосте с несинхронным образом; для приёмки использовать контейнер **`portfolio-test-assistant-flow-1`** после rebuild stack.

- **Frontend (если затрагивался бы в этой задаче — здесь не затрагивался):**

```bash
cd frontend/admin-ui && npm run build
```

- **Статус дерева:**

```bash
git status -sb
```
