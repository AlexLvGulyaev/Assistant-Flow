# 2026-09-03 — AF: полная актуализация документации по стандартам APL

## Задание (владелец)

> «Актуализируй документацию. Сделай это по полной программе, с предварительным
> чтением шаред паттернс и определением целевого состава документов и уровня их
> готовности. Список покажи мне перед началом работ. Список сделай в виде
> таблицы с названиями документов и перечнем их текущего несоответствия
> стандартам APL.»

Таблица несоответствий показана владельцу 2026-09-03. Решения владельца:
**«Да на все вопросы»** — (1) удалить `docs/homework/` из публичного репо;
(2) создать ретроспективно `docs/SPEC.md` и `docs/IMPLEMENTATION_PLAN.md`;
(3) вынести append-only инженерный журнал из PROJECT_STATE в отдельный файл.
Рабочее допущение принято: имя compose-проекта в доках — живой контур
(project `assistant-flow`, без `-p portfolio-test`).

## Стандарты (прочитанные паттерны shared/patterns)

- `three-layer-documentation-standard.md` — один документ = одна аудитория.
- `apl-documentation-pattern.md` — целевой состав, без дублирования, владельцы документов.
- `documentation-source-of-truth-discipline.md` — факты только из SOT (код/компоуз/БД).
- `documentation-audit-verification-pattern.md` — верификация списков и фактов, не «качество».
- `documentation-emoji-contract.md` — эмодзи-контракт заголовков.
- `deployment-validation-checklist.md` + операционная дисциплина CLAUDE.md — RUNBOOK как SOT развёртывания.
- Правило границы APL ↔ публичный репозиторий (CLAUDE.md).

## Целевой состав (утверждён)

Слой 1 (публичный GitHub): README, RUNBOOK, USER_GUIDE, docs/{ARCHITECTURE,
OPERATIONS, ADMIN_INDEXING, DEMO_SCENARIOS, RAG_SMOKE_TEST, SECURITY_NOTES,
security/, architecture/}, database/POSTGRES_SETUP.md, docs/SPEC.md (NEW),
docs/IMPLEMENTATION_PLAN.md (NEW).
Слой 2 (внутренний): PROJECT_STATE.md (паспорт) + docs/engineering_log.md (NEW,
вынесенный журнал). GITHUB_PREP.
Удалить из публичного репо: docs/homework/.

## Порядок и время (~9–11 ч)

1. Файл задачи + README + USER_GUIDE — 2–2.5 ч (**КТ-1**).
2. RUNBOOK + OPERATIONS (имя проекта, volume-имена) — 2 ч (**КТ-2**).
3. PROJECT_STATE: журнал → docs/engineering_log.md, паспорт по канону — 2.5–3 ч (**КТ-3**).
4. security/, architecture/, ADMIN_INDEXING, POSTGRES_SETUP, DEMO_SCENARIOS,
   RAG_SMOKE_TEST, GITHUB_PREP, чистка внутренних ссылок, удаление docs/homework — 2–2.5 ч.
5. SPEC + IMPLEMENTATION_PLAN, финальный верификационный прогон — 1–1.5 ч.

## Выполненные действия

### Фаза 1 — README + USER_GUIDE (КТ-1)

1. **README.md**: H1 `🏠` по эмодзи-контракту; таблица разделов консоли
   дополнена `/audit` + абзац о входе (Bearer-токен / демо-вход / локальный
   режим); каноническая команда деплоя без `-p portfolio-test` (проект =
   имя каталога `assistant-flow`); volumes `assistant-flow_portfolio_*` +
   абзац про multi-stage сборку и build-args; env-таблица дополнена группами
   «Доступ к консоли» (`AF_ADMIN_TOKEN`, `AF_ADMIN_DEMO_TOKEN`,
   `AF_AUTH_MIDDLEWARE_MODE`) и «Лимиты» (`ADMIN_UPLOAD_MAX_MB`); «Текущий
   статус» и Roadmap переписаны по факту (RAG-бэкенды, safeguards, аудит,
   multi-stage; roadmap: async-воркер, P5.4, фильтрация источников);
   таблица документации — без пометок «документ в разработке», добавлены
   SPEC.md, IMPLEMENTATION_PLAN.md, SECURITY_NOTES, POSTGRES_SETUP,
   DEMO_SCENARIOS.
2. **USER_GUIDE.md**: H1 `📖` (пометка «v1» снята); в §13 добавлены
   подраздел «Вход» (токен/демо-вход/выход, ссылки на SECURITY_NOTES и
   auth_modes), разделы `/audit`, `/login`, `/exit` в таблицу маршрутов,
   описание журнала аудита; «См. также» с эмодзи-иконками по контракту.

### Фаза 2 — RUNBOOK + OPERATIONS (КТ-2)

1. **RUNBOOK.md**: H1 `🚀`; все команды compose без `-p portfolio-test`
   (9 вхождений); пояснение про имя проекта из имени каталога; §E — имя
   проекта и предупреждение о втором стеке переписаны; §D — volume
   `assistant-flow_portfolio_pg_data`; ссылка §C.6 → §L; заявление о составе
   initdb уточнено (schema.sql вкл. 005–008 + 004 async_jobs).
2. **docs/OPERATIONS.md**: H1 `⚙️`; топология/контейнеры/Project/логи без
   `portfolio-test` (контейнеры `assistant-flow-*-1`); volume-имена
   Chroma/Weaviate — фактические `assistant-flow_portfolio_*` (сверено с
   `docker volume ls` живой инстанции).
3. **Верификация фактов по миграциям**: в `database/migrations/` реально
   002–008 (доки упоминали только 004/005/006). Найдено расхождение:
   `schema.sql` покрывает 005–007 и колонки 008, но без 3 индексов 008
   (`event_type`, `status`, `platform_role`). Индексы добавлены в snapshot
   (идемпотентно); живая БД уже содержит все 8 индексов — снимок совпал с
   продом.

### Фаза 3 — PROJECT_STATE → паспорт + журнал (КТ-3)

1. **Решение владельца по размещению журнала**: «клорские engineering logs —
   аналог task_history» → журнал положен в **`task_history/engineering_log.md`**
   (внутренний слой, не публичная документация). Вынесено append-only:
   исторические Cursor-процессные блоки (§20-хвост, Operator commands,
   ADDITIONAL CONTEXT) + все journal-секции §21–71 (P6–P9, инциденты, леджеры)
   — 2588 строк, нумерация § сохранена. Оригинал забэкаплен
   (`/tmp/PROJECT_STATE.md.bak-20260903`).
2. **PROJECT_STATE.md переписан как паспорт по канону APL** (H1 `📊`):
   Project Summary, Current Status (живой контур `assistant-flow`, закрытые
   инциденты, долг №6/№7), Market Validation (честно: внешних заказов нет),
   Commercial Assessment, Key Technology Areas, Decision, Next Steps,
   Status History (таблица), «Границы документа». Устаревшие §1–20
   (Streamlit-инфраструктура, «RBAC не реализован», CRITICAL-правило
   `portfolio-test` из §54) удалены — противоречили живому контуру.
3. **Перепривязка ссылок**: `docs/architecture/evaluation_layer_design.md` и
   `docs/architecture/security_rbac_design.md` — ссылки на §36/§38.5/§47.x
   переведены с PROJECT_STATE на `task_history/engineering_log.md`
   (нумерация сохранена). Ссылки в `docs/cursor_sessions/` — исторические,
   не переписываются.

## Изменённые файлы

- `README.md` — канон команды, env, статус/roadmap, таблица доков, `/audit`, H1.
- `USER_GUIDE.md` — вход по токену/демо, маршруты + `/audit` `/login` `/exit`, H1.
- `RUNBOOK.md` — живой контур compose (проект/volumes/команды), H1, initdb-факты.
- `docs/OPERATIONS.md` — топология/контейнеры/volumes/логи, H1.
- `database/schema.sql` — +3 индекса admin_audit_log (008), снимок = прод.
- `PROJECT_STATE.md` — переписан как паспорт (81 секция → 10 канон-разделов).
- `task_history/engineering_log.md` — NEW, вынесенный append-only журнал.
- `docs/architecture/evaluation_layer_design.md`, `docs/architecture/security_rbac_design.md` — перепривязка §-ссылок.

### Фаза 4 — слой docs/, безопасность, PostgreSQL (КТ-4)

1. **`docs/homework/`**: решение владельца изменено по ходу фазы — не удалить, а
   **переместить в аттачменты**: `docs/homework/module5_lesson9_security_rag_report.md`
   → `attachments/homework/` (git rename). Все ссылки на homework из
   `docs/SECURITY_NOTES.md`, `docs/security/security_walkthrough.md`,
   `docs/architecture/security_rbac_design.md` убраны (attachments — внутренний
   слой, публичные доки на него не ссылаются).
2. **SECURITY_NOTES.md**: H1 `🛡️`; блок Admin API переписан по факту —
   демо-стандарт APL (AF_ADMIN_TOKEN / AF_ADMIN_DEMO_TOKEN, enforcement
   automatic required, whoami, аудит входов, запечённый демо-токен) + легаси
   P9.2 как отдельный пункт; сняты устаревшие «Admin API без auth» и
   «`/api/logs/recent` без auth».
3. **portfolio-test вычищен полностью** (0 вхождений вне task_history):
   GITHUB_PREP (2), RAG_SMOKE_TEST, DEMO_SCENARIOS, security/*.md (команды
   compose и имена контейнеров `portfolio-test-*` → `assistant-flow-*`).
4. **database/POSTGRES_SETUP.md**: H1 `🗄️`; цепочка миграций 002–008
   перечислена явно (был только пример 002); snapshot-факты — schema.sql вкл.
   005–008, 004 отдельно; initdb-факты синхронизированы с RUNBOOK/OPERATIONS.
5. **H1-эмодзи по контракту**: 🎬 DEMO_SCENARIOS, 🧪 RAG_SMOKE_TEST,
   ⚙️ ADMIN_INDEXING, 🛡️ security/*, 🏗️ architecture/*.
6. **GITHUB_PREP.md**: §7 переписан под паспорт PROJECT_STATE + журнал в
   task_history; пункт про cursor_sessions уточнён (не в git).

### Фаза 5 — SPEC + IMPLEMENTATION_PLAN + верификация

1. **docs/SPEC.md** (NEW, `🎯`) — ретроспективная спецификация: проблема/идея,
   аудитории, функциональные требования по модулям (Telegram, RAG, консоль,
   доступ/безопасность, наблюдаемость), NFR, вне скоупа, критерии приёмки.
   Помечена как ретроспективная (разработка началась до формализации SPEC).
2. **docs/IMPLEMENTATION_PLAN.md** (NEW, `📋`) — архитектура, состав
   компонентов, модель данных, интеграции, фактическая хронология этапов
   (P5–P9, production build, демо-стандарт; P5.3-воркер и P5.4 — ◐),
   критерии готовности.
3. **Финальный верификационный прогон**: 187 относительных ссылок — все
   резолвятся (после создания SPEC/IMPLEMENTATION_PLAN); `portfolio-test` /
   `docs/homework` / «в разработке» — 0 вхождений вне легитимных
   (пункт решения владельца в PROJECT_STATE, формулировка чеклиста GITHUB_PREP);
   снимок schema.sql = прод (8 индексов admin_audit_log).

## Изменённые файлы

- `README.md` — канон команды, env, статус/roadmap, таблица доков, `/audit`, H1.
- `USER_GUIDE.md` — вход по токену/демо, маршруты + `/audit` `/login` `/exit`, H1.
- `RUNBOOK.md` — живой контур compose (проект/volumes/команды), H1, initdb-факты.
- `docs/OPERATIONS.md` — топология/контейнеры/volumes/логи, H1.
- `database/schema.sql` — +3 индекса admin_audit_log (008), снимок = прод.
- `PROJECT_STATE.md` — переписан как паспорт (81 секция → 10 канон-разделов).
- `task_history/engineering_log.md` — NEW, вынесенный append-only журнал (2588 строк).
- `docs/SPEC.md`, `docs/IMPLEMENTATION_PLAN.md` — NEW, ретроспективные по канону APL.
- `docs/SECURITY_NOTES.md` — демо-стандарт как текущий auth, сняты stale-факты, H1.
- `database/POSTGRES_SETUP.md` — цепочка 002–008, snapshot-факты, H1.
- `docs/GITHUB_PREP.md`, `docs/DEMO_SCENARIOS.md`, `docs/RAG_SMOKE_TEST.md`,
  `docs/ADMIN_INDEXING.md` — канон команды, H1, актуальные формулировки.
- `docs/security/*.md`, `docs/architecture/*.md` — команды на живой контур,
  H1-эмодзи, перепривязка §-ссылок (evaluation_layer_design,
  security_rbac_design).
- `attachments/homework/module5_lesson9_security_rag_report.md` — перенос из
  `docs/homework/` (решение владельца).

## Итоговый статус

**DONE** (2026-09-03). Документация кейса приведена к стандартам APL по
утверждённому составу: публичный слой (README/USER_GUIDE/RUNBOOK/docs) —
на живом контуре compose-проекта `assistant-flow`, без пометок «в разработке»,
по эмодзи-контракту; внутренний слой — PROJECT_STATE как паспорт (канон APL) +
append-only журнал в task_history/engineering_log.md; ретроспективные SPEC и
IMPLEMENTATION_PLAN созданы; homework перемещён в attachments по решению
владельца (не удалён). Верификация: 187/187 ссылок, факты свергнуты с кодом/
compose/живой БД (миграции 002–008, индексы, volume-имена). Не пушится —
только по явной команде владельца.