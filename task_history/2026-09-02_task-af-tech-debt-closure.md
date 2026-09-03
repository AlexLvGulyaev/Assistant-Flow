# 2026-09-02 — AF: закрытие технического долга (программа)

## Задание (владелец)

> «У меня "глаза" появились, базовые E2E я проделал, результатом вполне удовлетворен.
> Давай поработаем сначала над закрытием технического долга, ну а затем займемся
> причесыванием нашего старичка, который на самом деле был методологическим
> предшественником APL»

*(«старичок» — разъяснение владельца 02.09: это **сам кейс Assistant Flow**,
методологический предшественник APL; то есть после закрытия долга следует
причёсывание самого AF — упаковка/документация/витрина, а не другой кейс.)*

## Контур долга (PORTFOLIO_CORPUS_AUDIT.md v1.18, строка Assistant Flow)

1. **Heavy RAG stability** — instability после reindex больших документов (VPS RAM ~2 GB,
   no swap; паттерн «new version → reindex → RAG query → slowdown → instability»).
2. **Multi-version docs + idempotent reindex** — включая hygiene живого демо-индекса
   (dirty_test_*, «НоваТех» baseline, cooking_recipes и пр. мусор в 424 чанках Chroma).
3. **Telemetry/token economy**.
4. **RAG UI polish**.
5. **Production build**.
6. **Async layer**.
7. **Audio P5.4 remainder**.

Согласованный порядок (ранее): №1+№2 → затем №3; production build и async — позже.

## Порядок и время (этап 1: №1+№2, ~4–6 ч)

1. Файл задачи — 10 мин.
2. **Демо-индекс hygiene**: инвентаризация корпуса Chroma (424 чанка), вычистка
   dirty_test_* / «НоваТех» / cooking_recipes / candidate_scoring и прочего
   не-демо-мусора, идемпотентный скрипт чистки — 1–1.5 ч.
3. **Multi-version docs + idempotent reindex**: контракт reindex (dedupe чанков,
   lifecycle PG document_versions, повторный reindex без дублей) — 2–3 ч.
4. **Heavy RAG safeguards**: swap, caps на payload retrieval diagnostics,
   проверка degraded mode/healthcheck — 1.5–2 ч.
5. Проверки (rag_smoke, e2e RAG-режима бота, /stats) + отчёт КТ — 30 мин.

*(Далее по отдельным задачам: telemetry/token economy; затем RAG UI polish,
production build, async, audio P5.4 — по согласованию.)*

## Выполненные действия

### Шаг 1: демо-индекс hygiene (2026-09-02)

- Инвентаризация: Chroma 427 чанков / 22 источника; Weaviate (`AssistantFlowChunk`,
  secondary) 424 / 19. Роль: `RAG_BACKEND=chroma` — операционный бэкенд, Weaviate —
  июльское наследие, чистить оба.
- NEW `scripts/clean_demo_index.py` — идемпотентная чистка (dry-run по умолчанию,
  `--apply`): цели dirty_test_* ×7, cooking_recipes, candidate_scoring,
  ragas_facts_baseline («ООО НоваТех» — решение владельца: из индекса убрать,
  файл остаётся как источник повторного индексирования перед RAGAS-оценкой).
  Оставлены сознательно: p9_6b_restricted_handbook (демо P9.6b visibility),
  легитимный демо-корпус (it_ai_glossary_large 400 чанков и пр.).
- Результат: Chroma 427→415, Weaviate 424→415 (батч-делит через gRPC падал на
  клиенте 4.15.4 — обошёл REST по-объектно), PG-каталог 22→12 документов,
  файлы фикстур удалены. Оба хранилища синхронны: 415 чанков / 12 источников.
- Инцидент 1: скрипт удалил ragas_facts_baseline.txt вопреки KEEP_FILES (баг
  сравнения с расширением). Файл восстановлен из Weaviate-чанков (3675 байт),
  лежит в контейнерах и в репо (`data/documents/ragas_facts_baseline.txt`).
- Живой RAG-смоук после чистки: retrieval 634 мс, ответ грундирован, fallback=none.

### Шаг 2: multi-version docs + idempotent reindex (2026-09-02)

**Проверка контура:** lifecycle уже идемпотентен по дизайну — `_postgres_begin_file`
(reuse версии при неизменном hash; смена hash → deactivate старой версии + новая N+1),
delete-before-write в PG (`delete_document_chunks_for_version`) и в обоих векторных
сторах (Chroma `$or` по document_id/source; Weaviate `delete_many`).

**Аудитор NEW `scripts/index_consistency_check.py`** (read-only): сверяет PG ↔ файлы
`data/documents/` ↔ Chroma ↔ Weaviate (orphan-sources, расхождение счётчиков,
нарушения lifecycle-контракта). Первый же прогон поймал живой рассинхрон.

**Инцидент (мой):** `rag_smoke_test.py` без `--reindex` ДОБАВЛЯЕТ векторы поверх
(предупреждено в его же докстринге) — мой смоук-прогон разрос Chroma 415→834
(+419 дублей с `source` = полный путь, включая возврат «НоваТех» в индекс).
- Хирургическая чистка: удалены 419 full-path-строк → Chroma снова 415.
- `rag_smoke_test.py` переведён на **query-only по умолчанию**; перезапись
  индекса только под явным `--index` (перезаписана докстринг-шапка).
- `ragas_facts_baseline.txt` канонически перенесён в `evaluation/datasets/`
  (gitignore на `data/` исключал его из-под контроля); процедуры в docstring
  `evaluation_seed_ragas_dataset.py` + `ADMIN_INDEXING.md`.

**Ключевая находка:** активный retrieval backend живёт в PG
(`platform_settings.active_rag_backend = weaviate`, с 20.05.2026) — **живой бот
ходит в Weaviate**, env `RAG_BACKEND=chroma` не является источником истины.
Зафиксировано в `ADMIN_INDEXING.md`.

**Идемпотентность подтверждена эмпирически:** 3× `index_single_file(system_errors.txt)`
→ chroma=415, pg_versions=16, pg_docs=12 стабильны (hash неизменен → reuse версии).

**Финал:** consistency check OK (PG 12 док / 415 активных чанков = Chroma 415/12
= Weaviate 415/12); query-only смоук даёт грундированный ответ, ничего не пишет.

### Попутная находка (долг №3, heavy RAG stability)

- **Диск VPS 79–80%** → Weaviate сам закрыл шарды на запись (READ_ONLY-лимит 80%)
  — поэтому delete_many падал (`store is read-only`). После `docker builder prune -a
  -f` (освобождено **24.83 ГБ**, реального мусора-образов только ~2 ГБ — «52 ГБ
  reclaimable» из `docker system df` иллюзорны, там shared-слои) диск **79%→61%**;
  рестарт Weaviate → запись восстановлена, чистка прошла.
- **RAM-давление реальное:** free 231 Mi, swap 4.8/5 ГБ использован (машина 7.8G
  RAM — PROJECT_STATE с «~2 GB RAM» устарел). Учитывать в шаге 3 (safeguards).

### Шаг 3: heavy RAG safeguards (2026-09-02)

**Замеры живого контура** (пересмотр PROJECT_STATE-причин):

- **Diagnostics payloads не доминирующий фактор:** `processing_logs` в PG —
  `rag_answer_done` avg 4.2 КБ / max 12 КБ, строк >20 КБ нет, таблица 2.1 МБ.
  Operational tier уже пишет компактные чанк-суммари (без `chunk_text_full`),
  forensic-режим (роль admin) ограничен санитайзером.
- **RAM:** 7.8 GiB RAM + 5 GiB swap (два swapfile); si/so = 0, PSI ≈ 0, available
  ~3.6 GiB — простой стабилен. Риск — пики (reindex большого документа +
  параллельный RAG-запрос). Описание PROJECT_STATE «~2 GB RAM, no swap» устарело
  (исправлено).
- **Footprint AF-стека** ~820 МБ: admin-api 269 + chroma 234 + bot 227 +
  weaviate 70 + postgres 20 МБ.
- **Genuine дыра:** upload-роут читал файл целиком в RAM (`await file.read()`)
  без лимита; reindex аналогично не имел капа на файлы из bind mount.

**Реализованные safeguards:**

- NEW настройка `ADMIN_UPLOAD_MAX_MB` (default 25 МБ; `utils/config.py`,
  `.env.example`).
- `admin_api/routes/documents.py` upload: pre-check `file.size` + bounded read
  (чанками 1 МБ) → `413` на превышение, файл не грузится в RAM целиком.
- `services/admin_service.py`: `upload_max_bytes()` + кап в
  `save_uploaded_document` (ValueError → 400; вторая линия обороны).
- `services/admin_knowledge_indexer.py` `_index_one_file`: стат-гард — файлы
  больше лимита пропускаются («file too large … ADMIN_UPLOAD_MAX_MB»).
- `docker-compose.portfolio.yml`: Docker healthcheck admin-api (лёгкий
  `/api/health`, PG + retrieval readiness, без LLM-вызовов).

**Проверки (live):**

- `/api/health` → HTTP 200, overall ok; `docker ps` → admin-api `(healthy)`.
- E2E upload 26 214 401 байт → **HTTP 413**; small upload → success (chunks=1),
  затем пробный документ вычищен (PG/chroma/weaviate/файлы),
  `index_consistency_check.py` → OK (415/12 везде).
- Сервис-уровень: `save_uploaded_document` oversize → ValueError (26 214 401 >
  26 214 400).
- Бот пересобран/поднят: polling запущен, ошибок нет.

**Документация:** RUNBOOK (B.2 ADMIN_UPLOAD_MAX_MB + Шаг 1 ожидание healthy),
ADMIN_INDEXING.md (safeguard-блок), PROJECT_STATE.md (причины/замеры актуализированы).

## Изменённые файлы

Репозиторий (`cases/assistant-flow/`):

| Файл | Что сделано |
|------|-------------|
| `scripts/clean_demo_index.py` | NEW — идемпотентная чистка демо-индекса (Chroma+Weaviate+PG+файлы; dry-run по умолчанию, `--apply`) |
| `scripts/index_consistency_check.py` | NEW — read-only аудит PG ↔ файлы ↔ Chroma ↔ Weaviate |
| `scripts/rag_smoke_test.py` | Патч: query-only по умолчанию, индексация только под `--index`; переписана докстринг-шапка |
| `scripts/evaluation_seed_ragas_dataset.py` | Патч докстринга: каноническое место baseline-файла + процедура RAGAS-оценки |
| `evaluation/datasets/ragas_facts_baseline.txt` | Восстановлен из Weaviate-чанков (3675 байт), канонический home (git mv из data/documents) |
| `utils/config.py` | NEW `admin_upload_max_mb` (env `ADMIN_UPLOAD_MAX_MB`, default 25) |
| `admin_api/routes/documents.py` | Upload: pre-check размера + bounded read, 413 |
| `services/admin_service.py` | `upload_max_bytes()` + кап в `save_uploaded_document` |
| `services/admin_knowledge_indexer.py` | Стат-гард файла в `_index_one_file` |
| `docker-compose.portfolio.yml` | Docker healthcheck admin-api |
| `.env.example` | Задокументирован `ADMIN_UPLOAD_MAX_MB` |
| `RUNBOOK.md` | B.2 safeguard + ожидание admin-api healthy в Шаге 1 |
| `docs/ADMIN_INDEXING.md` | Секция hygiene (Шаг 1–2) + safeguard-блок (Шаг 3) |
| `PROJECT_STATE.md` | Актуализация причин heavy RAG instability (RAM/swap замеры, payload-замеры, mitigations) |
| `task_history/2026-09-02_task-af-tech-debt-closure.md` | Этот файл |

Состояние контейнеров/хоста (не в репо):

- PG-каталог `assistant_flow`: 22→12 документов, неактивные версии с чанками вычищены.
- Chroma `assistant_flow_rag`: 427→415 чанков / 12 sources; Weaviate: 424→415 / 12.
- Фикстурные файлы удалены из `data/documents/` (bind mount).
- Хост: `docker builder prune -a -f` (−24.83 ГБ, 79%→61%) — по решению владельца
  («1 делаем без проблем»); рестарт Weaviate снял READ_ONLY-шарды.
- Пересобраны/пересозданы контейнеры admin-api и assistant-flow (bot); admin-api
  healthy, бот на polling.

## Итоговый статус

Шаги 1–3 закрыты: **№2 hygiene + multi-version/idempotent reindex** — DONE
(consistency check OK, идемпотентность 3× повтором); **№1 heavy RAG
safeguards** — DONE (upload cap 413 e2e, indexer guard, admin-api Docker
healthcheck, PROJECT_STATE актуализирован). Долг №1 (heavy RAG stability)
считается покрытым на уровне safeguards; оставшиеся причины (sync pipeline,
Streamlit) — вне этой программы.

Далее по согласованной программе — **№3 telemetry/token economy** (отдельная
задача; частично уже есть: input/output/total_tokens в diagnostics). Затем RAG
UI polish, production build, async, audio P5.4 — по согласованию. После долга
AF — второй этап владельца: «причесывание старичка» (prompt-review).