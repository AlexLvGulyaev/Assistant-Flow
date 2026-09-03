# 2026-09-03 — AF: async-слой, вариант A (долг №6, P5.3)

## Задание (владелец)

> «Что дальше по планам технического долга AF?» → представлен план долгов №6/№7
> с вилкой вариант A (воркер-поток в admin-api) vs B (отдельный контейнер).
> **Ответ владельца: «Давай А».**

## Скоуп (вариант A, оценка ~5–7 ч)

Фундамент P5.3a/b уже в коде: `AsyncJobService` (таблица `async_jobs`,
claim через `FOR UPDATE SKIP LOCKED`, retry), `AsyncReindexWorker`
(single-step skeleton, batch cap 5) — но daemon не стартует и enqueue-путь
не вызывается ниоткуда. Задача: довести до рабочего контура.

1. **Воркер-поток** (`services/async_job_worker.py`): daemon-loop внутри
   admin-api, claim → исполнение `rag_reindex` через `run_single_job()`,
   graceful stop, reclaim stale-`running` задач на старте (защита от
   рестарта mid-job), env: `AF_ASYNC_WORKER_ENABLED` (default on),
   `AF_ASYNC_WORKER_POLL_SECONDS` (default 5).
2. **Lifespan** admin-api: старт/останов потока.
3. **Endpoints** admin_api: POST `/api/documents/reindex-async` (enqueue
   full-corpus reindex), GET `/api/documents/async-jobs` (список),
   POST `/api/documents/async-jobs/{id}/retry`.
4. **UI (DocumentsPage)**: панель «Фоновые задачи» — enqueue-кнопка,
   список задач (статус/attempts/duration), retry. Синхронные кнопки
   не трогаем.
5. **Доки**: README (env-таблица, статус/roadmap), IMPLEMENTATION_PLAN
   (P5.3 ◐→✅), SPEC (вне-скоупа), .env.example; PROJECT_STATE (№6 закрыт,
   плюс снятие устаревшей строки про документацию «в процессе»).
6. **Деплой** на живой инстанции (rebuild admin-api + admin-ui) и верификация.

КТ-1 — после воркера и endpoints; КТ-2 — после UI; финал — после деплоя
и проверки на живом.

## Результаты

### КТ-1 — воркер + endpoints (код)

- `services/async_job_worker.py` (NEW) — `AsyncJobWorkerDaemon`: поток-потребитель
  `async_jobs` (одна задача за итерацию, claim через существующий
  `claim_next_job` с `FOR UPDATE SKIP LOCKED`), graceful stop через
  `threading.Event`, process-wide singleton `get_async_job_worker()`;
  env `AF_ASYNC_WORKER_ENABLED` (default on) / `AF_ASYNC_WORKER_POLL_SECONDS`
  (default 5) / `AF_ASYNC_WORKER_STALE_RUNNING_SECONDS` (default 1800).
- `services/async_job_service.py` — +`reclaim_stale_running()`: на старте
  воркера брошенные после рестарта `running`-задачи возвращаются в `queued`
  (порог по `updated_at`, триггер 004 подтверждён).
- `admin_api/app.py` — старт/останов воркера в lifespan.
- `admin_api/routes/documents.py` — POST `/api/documents/reindex-async`,
  GET `/api/documents/async-jobs`, POST `/api/documents/async-jobs/{id}/retry`
  (права: reindex — `PERM_DOCUMENTS_REINDEX`, список — `PERM_DOCUMENTS_READ`;
  аудит `documents.reindex_async` / `documents.async_job_retry`).
- `.env.example` — блок «Фоновый воркер async_jobs».

### КТ-2 — UI (DocumentsPage)

- Панель «Фоновые задачи»: enqueue-кнопка «⏭ Переиндексировать всё (фон)»,
  список последних 10 задач (StatusBadge + attempts/duration/время + текст
  ошибки), retry для failed/retry_scheduled, авто-poll 4 с при активной
  задаче. Синхронные кнопки не тронуты.
- `client.ts` — типы `AsyncJobInfo`/`AsyncJobItem` + 3 функции;
  `StatusBadge` — статусы queued/retry_scheduled/succeeded;
  `globals.css` — блок `.docs-async-panel*`. tsc 0 ошибок, build ok.

### Финал — деплой + живая верификация (2026-09-03)

- Рестарт `admin-api` + `admin-ui` (--build); в логах
  `async_worker: started (poll_seconds=5.0, stale_running_seconds=1800)`.
- API e2e: enqueue → claim → **succeeded за 23.4 с** (415 чанков);
  негативные пути: retry по succeeded → 409, invalid uuid → 400,
  без токена → 401, демо-токен enqueue → 403 (read-only), демо-токен
  список → 200. Всё как задумано.
- Headless DOM (живая витрина, 1280×900): статическая проба **9/9 PASS**;
  полный UI-путь (клик enqueue → задача в списке → воркер исполнил →
  бейдж «выполнено») **4/4 PASS**; 0 JS-ошибок, без переполнения.
- После reindex: health ok (postgres/chroma/rag ok), fd admin-api = 24
  (утечек нет), все контейнеры healthy.

## Изменённые файлы

- NEW: `services/async_job_worker.py`,
  `task_history/2026-09-03_task-af-async-worker-variant-a.md`.
- `services/async_job_service.py` — reclaim_stale_running().
- `admin_api/app.py` — lifespan старт/стоп воркера.
- `admin_api/routes/documents.py` — 3 новых endpoint'а.
- `frontend/admin-ui/src/api/client.ts`, `src/pages/DocumentsPage.tsx`,
  `src/components/StatusBadge.tsx`, `src/styles/globals.css`.
- Доки: `.env.example`, `README.md` (env-таблица, статус/roadmap, подпись
  скриншота), `docs/IMPLEMENTATION_PLAN.md` (P5.3 ◐→✅), `docs/SPEC.md`
  (фоновые задачи — реализовано; вне скоупа — отдельный контейнер-воркер),
  `PROJECT_STATE.md` (№6 закрыт, Status History, риски/дефициты).

## Итоговый статус

**DONE** (2026-09-03). Долг №6 закрыт (вариант A, воркер-поток в admin-api).
Верификация на живом инстансе: API-путь и полный UI-путь PASS, негативные
пути соответствуют контракту прав. Не пушится — по явной команде владельца.