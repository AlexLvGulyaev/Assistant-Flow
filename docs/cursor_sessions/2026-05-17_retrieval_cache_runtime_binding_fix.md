# PEr07 — Retrieval Cache Runtime Binding Diagnostic & Fix

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Если Auto явно не справляется с multi-file backend reasoning — только тогда предложи оператору переключение.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

Мы дошли до содержательной проверки retrieval cache.

Через Retrieval Settings оператор включил retrieval cache:

```json
{
  "enable_retrieval_cache": true,
  "enable_retrieval_cache_source": "db",
  "enable_answer_cache": false,
  "retrieval_cache_ttl_seconds": 86400,
  "answer_cache_ttl_seconds": 86400,
  "rag_retrieval_generation": "1",
  "cache_db_path": "storage/cache/assistant_cache.sqlite3",
  "editable_via_api": true,
  "apply_note": "enable_retrieval_cache via PUT /api/retrieval/tuning; effective ~2.5s (backend wrapper rebuild)."
}
```

Это означает:

- Admin API видит `enable_retrieval_cache=true`;
- source = `db`;
- Retrieval Settings / `/api/retrieval/overview` работают;
- UI-level setting сохранён корректно.

Но после этого новые RAG-события в RAG console всё равно показывают cache state `OFF`.

Симптом:

- cache включён в RS;
- overview говорит `enable_retrieval_cache=true`;
- новые RAG execution logs продолжают вести себя так, будто cache не участвует;
- HIT/MISS не появляются;
- comparison показывает OFF/OFF или cache comparison unavailable.

Это уже не UI cosmetic issue.

Это разрыв между:

```text
Admin API / platform_settings
```

и

```text
assistant-flow runtime RAG execution pipeline
```

---

# Главная цель

Провести точечную диагностику и исправить runtime binding:

RAG execution pipeline должен использовать effective retrieval cache setting из того же source of truth, что и Retrieval Settings / overview.

После включения cache через UI:

- первый повторяемый RAG-запрос должен давать MISS;
- второй идентичный RAG-запрос должен давать HIT;
- logs/details должны содержать cache telemetry;
- RAG console должна показывать MISS/HIT, а не OFF.

---

# Важно

Это backend/runtime diagnostic and fix pass.

НЕ UI redesign.
НЕ новый cache layer.
НЕ Redis.
НЕ answer cache.
НЕ schema migration без необходимости.

Не трогать RAG-card layout, кроме минимальных изменений, если они нужны для правильного отображения runtime telemetry.

---

# Обязательно прочитать

1. docs/cursor_sessions/2026-05-17_retrieval_cache_onoff_api_fix.md

2. docs/cursor_sessions/2026-05-17_retrieval_cache_control_and_rag_card_layout.md

3. docs/cursor_sessions/2026-05-17_restore_rag_telemetry_semantics.md

4. docs/architecture/cache_layer_design.md

5. admin_api/routes/retrieval.py

6. services/admin_service.py

7. services/retrieval/runtime_manager.py

8. services/retrieval/factory.py

9. services/cache/caching_retrieval_backend.py

10. services/cache/retrieval_cache_key.py

11. services/cache/sqlite_cache.py

12. services/cache/invalidate.py

13. services/rag_query_service.py

14. services/rag_types.py

15. utils/config.py

16. repositories / services responsible for platform_settings / retrieval_tuning

17. interfaces/telegram_bot.py and core/orchestrator.py only if needed to trace RAG runtime path

---

# Diagnostic questions

Нужно ответить точно, по коду:

## 1. Кто читает `enable_retrieval_cache` в runtime?

Проверить:
- runtime manager;
- retrieval backend factory;
- RagQueryService construction;
- Telegram/orchestrator dependency creation;
- admin API dependency creation.

И выяснить:

- runtime RAG path читает DB override?
- или только env `ENABLE_RETRIEVAL_CACHE`?
- есть ли cached/stale singleton?
- происходит ли rebuild backend wrapper после DB setting change?
- тот ли process читает platform_settings?

---

## 2. Почему overview видит true, а RAG execution остаётся OFF?

Возможные причины:

- overview использует `RetrievalTuningResolver`, а runtime factory нет;
- admin-api и assistant-flow containers имеют разные managers/state;
- bot runtime не подключён к PostgreSQL/platform_settings;
- cache wrapper создаётся один раз на старом env config и не rebuild-ится;
- UI cache badge использует global overview false/stale, а logs на самом деле содержат telemetry;
- RAG logs не пишут cache fields даже при wrapper participation.

Нужно определить реальную причину, не гадать.

---

## 3. Где должен быть source of truth?

Ожидаемая модель:

- env `ENABLE_RETRIEVAL_CACHE` = default/fallback;
- DB/platform_settings override = runtime effective setting;
- overview и RAG runtime должны использовать один resolver/effective config;
- answer cache остаётся disabled/future stub.

Если текущий код иначе устроен — описать и исправить минимально.

---

# Что нужно реализовать

## A. Runtime binding fix

Сделать так, чтобы assistant-flow RAG runtime применял effective retrieval cache setting:

- `enable_retrieval_cache=true` из DB/platform_settings должен включать cache wrapper;
- `enable_retrieval_cache=false` должен выключать cache wrapper;
- изменение должно применяться по существующей политике:
  - hot apply через manager cache refresh;
  - или после короткого refresh interval;
  - или честно требовать restart, если hot apply невозможен.

В overview уже указано:
`effective ~2.5s (backend wrapper rebuild)`

Если это обещание не соответствует runtime — исправить либо поведение, либо apply_note.

---

## B. Telemetry fix

При cache enabled:

RAG logs/details должны получать cache telemetry:

- retrieval_cache_hit / retrieval_cache_miss;
- cache_layer;
- cache_latency_ms;
- retrieval_cache_generation;
- retrieval_cache_backend;
- retrieval_cache_key_hash_prefix;
- retrieval_cache_fingerprint_backend;
- skipped_retrieval, если применимо.

Если wrapper already computes telemetry but RagRequestDiagnostics does not receive it — исправить propagation.

---

## C. Test/smoke scenario

Добавить или обновить smoke script / test:

1. Set retrieval cache ON via tuning API or resolver test.
2. Run same RAG retrieval query twice.
3. Verify:
   - first execution = MISS;
   - second execution = HIT;
   - telemetry present;
   - cache db file contains retrieval namespace rows or equivalent evidence.
4. Set retrieval cache OFF.
5. Verify execution state = OFF/no wrapper.

Если полноценный RAG smoke дорогой — сделать focused backend smoke на retrieval backend factory/cache wrapper с minimal query/backend stub.

Но обязательно проверить true/false effective behavior.

---

# Что нельзя делать

Нельзя:

- менять UI layout;
- добавлять new panels;
- включать answer cache;
- менять cache storage backend;
- переносить cache в PostgreSQL;
- делать Redis;
- скрывать OFF как MISS;
- писать fake telemetry;
- делать broad refactor orchestration;
- ломать existing retrieval backend selection.

---

# Acceptance criteria

Pass считается успешным, если:

1. `/api/retrieval/overview` показывает `enable_retrieval_cache=true`.
2. RAG runtime реально использует cache wrapper.
3. Первый повторяемый RAG query после включения cache даёт MISS.
4. Второй идентичный RAG query даёт HIT.
5. RAG logs/details содержат cache telemetry.
6. RAG console больше не показывает OFF для новых событий после включения cache.
7. OFF остаётся только при effective disabled.
8. DB override и env fallback не конфликтуют.
9. Existing backend switch/top_k tuning не сломаны.
10. API/build/tests проходят.

---

# Session log

Создать:

`docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_runtime_binding_fix.md`

Дата:
`date +%F`

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. Root cause: почему overview=true, а RAG runtime=OFF.
2. Runtime ownership map after fix.
3. Changed files.
4. Effective source of truth.
5. Hot apply vs restart behavior.
6. Telemetry propagation path.
7. Smoke/test results.
8. Exact commands run.
9. Remaining limitations.
10. Git status.

---

# Operator commands / next verification commands

В конце session log добавить конкретные команды:

- backend test / smoke;
- rebuild affected services;
- curl overview check;
- manual RAG test checklist;
- git status.

Если изменён assistant-flow runtime, обязательно указать пересборку/перезапуск `assistant-flow`, а не только admin-api/admin-ui.

Использовать только portfolio stack форму:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...
```

Не писать обобщённо `docker compose up -d --build` без `-p portfolio-test`.

---

# Ответ в чат Cursor

В ответе предоставить только:

1. root cause;
2. changed files;
3. runtime binding fix summary;
4. source of truth after fix;
5. hot apply/restart behavior;
6. telemetry result;
7. smoke/test result;
8. services to rebuild/restart;
9. remaining limitations;
10. git status.

Commit НЕ выполнять.

---

## Engineering log (2026-05-17)

### 1. Root cause

**overview=true, RAG runtime=OFF** из‑за разрыва binding:

1. `build_retrieval_backend()` оборачивал inner backend в `CachingRetrievalBackend` **только** если `config.enable_retrieval_cache` был true **на момент сборки** (frozen `AppConfig` snapshot).
2. `enable_retrieval_cache` из `platform_settings.retrieval_tuning` попадал в effective config через `RetrievalTuningResolver` для overview/admin-api, но wrapper при `ENABLE_RETRIEVAL_CACHE=false` в env **не создавался** — в логах `backend_wrapper_class` ≠ `CachingRetrievalBackend`, UI показывал OFF.
3. Переключение cache ON/OFF через UI требовало rebuild backend по `build_key` с `cache=0|1`; при stale resolver или без wrapper telemetry (hit/miss) не появлялась.

### 2. Runtime ownership map (after fix)

| Компонент | Роль |
|-----------|------|
| `platform_settings.retrieval_tuning` + env | SoT для `enable_retrieval_cache` |
| `RetrievalTuningResolver` | effective `AppConfig` (TTL 2.5s), shared: admin overview, `RagQueryService._eff()`, `CachingRetrievalBackend._cache_enabled()` |
| `RetrievalBackendManager` | lazy inner backend + **всегда** `CachingRetrievalBackend` shell |
| `CachingRetrievalBackend` | live ON/OFF через resolver; hit/miss → thread TLS → `RagQueryService` → `processing_logs.details` |
| `RagQueryService` | `retrieval_cache_disabled` только если effective cache off и нет hit/miss |

### 3. Changed files

- `services/cache/caching_retrieval_backend.py` — `tuning_resolver`, `_cache_enabled()`
- `services/retrieval/factory.py` — always wrap; pass `tuning_resolver`
- `services/retrieval/runtime_manager.py` — pass resolver to factory; `build_key` без cache bit; `refresh()` invalidates resolver
- `services/retrieval/retrieval_tuning_resolver.py` — log DB degraded
- `scripts/test_retrieval_cache_runtime_binding_smoke.py` — new
- `scripts/test_retrieval_backend_factory.py` — expect wrapper

### 4. Source of truth

- Env `ENABLE_RETRIEVAL_CACHE` — bootstrap default.
- DB `retrieval_tuning.enable_retrieval_cache` — override (как overview).
- Runtime: `RetrievalTuningResolver.effective_config().enable_retrieval_cache` в wrapper и `RagQueryService`.

### 5. Hot apply / restart

- **Restart не нужен** для ON/OFF cache.
- Effective flag подхватывается в `CachingRetrievalBackend.search()` в пределах TTL resolver (~2.5s).
- Смена active RAG backend по-прежнему rebuild через manager.

### 6. Telemetry propagation

`CachingRetrievalBackend.search` → `_record_retrieval_cache_thread_diag` → `take_retrieval_cache_thread_diag` (worker thread) → `RagQueryService._retrieve_raw` → `_routing_identity_for_logs` → `RagRequestDiagnostics` → `processing_logs.details`.

### 7. Smoke / tests

- Inline unit (host): MISS + HIT на mock resolver — **OK**.
- `scripts/test_retrieval_cache_runtime_binding_smoke.py` — добавлен; полный прогон в portfolio container (нужен psycopg).
- Host: `psycopg` отсутствует — полные smokes не запускались.

### 8. Commands run

```bash
python3 -c '... inline CachingRetrievalBackend MISS/HIT ...'  # OK
git status --short
```

### 9. Remaining limitations

- Evaluation path по-прежнему принудительно отключает cache.
- Fingerprint `rag_backend` в ключе — snapshot при build manager (не live active backend name).
- `RAG_RETRIEVAL_GENERATION` — env-only.

### 10. Operator verification

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build assistant-flow admin-api
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d assistant-flow admin-api

# overview
curl -sS http://localhost:8600/api/retrieval/overview | jq '.cache.enable_retrieval_cache, .cache.enable_retrieval_cache_source'

# smoke (внутри assistant-flow container)
docker compose -p portfolio-test -f docker-compose.portfolio.yml exec assistant-flow \
  python scripts/test_retrieval_cache_runtime_binding_smoke.py

# manual: два одинаковых RAG-запроса в Telegram → MISS затем HIT в RAG console
```

### 11. Git status

См. ответ чата; commit не выполнялся.
