# 2026-09-02 — AF: Production build (долг №5)

## Задание (владелец)

> «Оставшиеся пункты долга»

Закрытие остатка контура долга AF (PORTFOLIO_CORPUS_AUDIT.md v1.18, строка
Assistant Flow): №4 RAG UI polish ✅ → **№5 production build** → №6 async layer
→ №7 audio P5.4 remainder. Этот файл — пункт №5.

## Скоуп

- Multi-stage backend-образ (сборочные зависимости не остаются в финальном образе).
- Аудит `.dockerignore` — в образ не должны попадать данные, кэши, локальные артефакты, секреты.
- Аудит зависимостей: dev-зависимости не в runtime-образе; `INSTALL_RAGAS` — opt-in сохраняется.
- Замер размера образов до/после.
- Деплой на живой инстанции (project `assistant-flow`), smoke-проверка
  (health, RAG-эндпоинты, включая новый chunk-fulltext).
- Актуализация документации развёртывания (RUNBOOK §C/D-E), если процесс меняется.

## Порядок и время (~2–3 ч)

1. Файл задачи — 5 мин.
2. Аудит текущего Dockerfile/.dockerignore/зависимостей, замер до — 30 мин.
3. Multi-stage Dockerfile backend, правки .dockerignore — 45–60 мин.
4. Rebuild + деплой live + smoke — 30–45 мин.
5. Замер после, документация, файл задачи — 30 мин.

## Выполненные действия

1. **Аудит до**: backend-образ — один stage, build-essential + curl + ffmpeg в
   runtime, `COPY . .` без ограничений; admin-api 2.91GB / assistant-flow
   2.89GB. admin-ui уже multi-stage (74.4MB) — без изменений.
2. **Multi-stage Dockerfile**: builder (build-essential + venv с зависимостями)
   → runtime (venv + ffmpeg + curl, без сборочных пакетов). Build-args:
   `INSTALL_RAGAS` (сохранён), `INSTALL_DASHBOARD` (новый).
3. **Dev-зависимости**: streamlit вынесен из `requirements.txt` в
   `requirements-dashboard.txt` (legacy Streamlit UI); в
   `docker-compose.assistant.yml` для `assistant-admin` включён
   `INSTALL_DASHBOARD=true`. Побочно обнаружен скрытый транзитивный деп
   `python-multipart` (раньше приходил со streamlit, нужен FastAPI upload) —
   добавлен явно в requirements.txt.
4. **`.dockerignore`**: добавлены data/, storage/, logs.db, frontend/ (backend-образ
   не носит React-приложение), docs/, task_history/, cursor_tasks_local/,
   evaluation/datasets/, *.zip, локальные артефакты. Секреты (.env/.env.*) —
   исключены и раньше, проверено.
5. **Инцидент при деплое (fd-leak)**: docker health → unhealthy за ~6 ч;
   `/proc/1/fd` = 1014, все ESTABLISHED к chroma:8000; Chroma-сервер заблокирован
   (принимает TCP, не отвечает). Root cause: per-call `chromadb.HttpClient` без
   закрытия (2 клиента на каждый `/api/health` ≈ 240 сокетов/час) + сломанная
   защита таймаутом (`with ThreadPoolExecutor` → `shutdown(wait=True)` блокирует
   выход при зависшем воркере). Фикс: `close_chroma_client()` (закрытие httpx
   сессии + System refcount), закрытие во всех per-call точках
   (healthcheck-воркеры, count_chroma_chunks, reset_chroma_for_reindex,
   ChromaRagStore.close(), chroma-путь fetch_chunk_full_text), bounded-пробы на
   `shutdown(wait=False, cancel_futures=True)`. Рестарт Chroma + пересборка +
   деплой. Верификация: 8 подряд health-вызовов → fd 19→16 (плоско), health ok
   (collection_count=415), docker health healthy, chroma heartbeat отвечает,
   chunk-fulltext 200, admin-ui 200, бот поднялся (weaviate, 415 чанков).
6. **Размер образов**: admin-api 2.91→2.19GB (−25%), assistant-flow
   2.89→1.95GB (−33%); admin-ui без изменений 74.4MB.
7. **Документация**: RUNBOOK §E — multi-stage сборка и build-args extras.
   Паттерн KB: `shared/patterns/short-lived-chroma-http-client-fd-leak.md`.

## Изменённые файлы

- `Dockerfile` — multi-stage (builder + runtime), build-args INSTALL_RAGAS / INSTALL_DASHBOARD.
- `requirements.txt` — streamlit убран (перенос в dashboard), + `python-multipart>=0.0.9`.
- `requirements-dashboard.txt` — NEW (legacy Streamlit UI, opt-in).
- `.dockerignore` — data/, storage/, frontend/, docs/, task_history/ и пр.
- `docker-compose.assistant.yml` — assistant-admin: INSTALL_DASHBOARD=true.
- `services/rag_chroma_store.py` — `close_chroma_client()`, `ChromaRagStore.close()`, закрытие в count/reset.
- `services/healthcheck_service.py` — закрытие клиентов в воркерах, bounded-пробы без блокирующего shutdown.
- `services/admin_service.py` — закрытие ChromaRagStore в chroma-пути fetch_chunk_full_text.
- `RUNBOOK.md` — §E: multi-stage сборка, build-args.
- `shared/patterns/short-lived-chroma-http-client-fd-leak.md` — NEW (KB).

## Итоговый статус

**DONE** (2026-09-03). Multi-stage образы (−25…−33% размера), чистый runtime
без build-пакетов и без dev-зависимостей, секреты не попадают в образ. По ходу
найден и закрыт fd-паттерн (утечка chromadb HttpClient + блокирующий shutdown),
живая инстанция обновлена и здорова. Обнаруженное расхождение (имя compose-проекта
доков `portfolio-test` vs живой контур `assistant-flow`) вынесено владельцу на
решение — документация канона не менялась.

## Operator commands / next verification commands

```bash
docker ps --format "{{.Names}}\t{{.Status}}" | grep assistant-flow
docker exec assistant-flow-admin-api-1 sh -c "ls /proc/1/fd | wc -l"   # ожидание: ~15-20, не растёт
curl -s http://localhost:8600/api/health | head -c 200
docker images --format "{{.Repository}}\t{{.Size}}" | grep assistant-flow
```