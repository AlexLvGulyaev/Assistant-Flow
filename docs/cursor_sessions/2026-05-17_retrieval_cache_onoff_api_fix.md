# Session: Retrieval cache ON/OFF API fix (2026-05-17)

# PEr07 — Fix Retrieval Cache ON/OFF API Binding

## Режим работы Cursor

Рекомендуемый режим Cursor: Auto.

Не фиксируй модель вручную без необходимости.
Если Auto явно не справляется с небольшим backend/frontend binding fix — только тогда предложи оператору переключение.

Все комментарии, session log и выводы — строго на русском языке.

---

# Контекст

После pass:

`2026-05-17_retrieval_cache_control_and_rag_card_layout.md`

в Retrieval Settings появился ON/OFF control для `ENABLE_RETRIEVAL_CACHE`.

Но при попытке включить cache через UI возникает ошибка:

`empty body: provide at least one tuning field`

Это означает, что frontend отправляет новое поле или intent, но backend endpoint/schema/update handler всё ещё не считает это поле допустимым tuning field.

Нужно сделать точечный fix.

---

# Цель

Исправить binding между Retrieval Settings UI и backend API так, чтобы изменение retrieval cache ON/OFF:

- корректно отправлялось;
- принималось backend schema;
- сохранялось в правильный source of truth;
- отображалось в `/api/retrieval/overview`;
- не ломало existing tuning fields;
- не требовало schema migration без необходимости.

---

# Обязательно прочитать

1. docs/cursor_sessions/2026-05-17_retrieval_cache_control_and_rag_card_layout.md

2. frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx

3. frontend/admin-ui/src/components/RetrievalCacheSettingsPanel.tsx

4. frontend/admin-ui/src/api/client.ts

5. admin_api/routes/retrieval.py

6. services/retrieval/runtime_manager.py

7. services/admin_service.py

8. utils/config.py

9. platform settings repository / service, если используется для retrieval tuning

---

# Что нужно проверить

## 1. Frontend request payload

Проверить:
- какое поле отправляется при ON/OFF;
- совпадает ли имя поля с backend schema;
- не отправляется ли `{}` из-за фильтрации false/true;
- не отбрасывается ли `false` как falsy value;
- используется ли existing update tuning function.

Особенно проверить:
- `enable_retrieval_cache`
- `ENABLE_RETRIEVAL_CACHE`
- `retrieval_cache_enabled`
- naming consistency.

---

## 2. Backend schema / handler

Проверить:
- какие поля endpoint считает валидными;
- где формируется ошибка `empty body: provide at least one tuning field`;
- добавить новое поле в allowed tuning fields;
- корректно обрабатывать both `true` and `false`;
- не считать `false` отсутствующим значением.

---

## 3. Source of truth

Проверить и зафиксировать:
- куда сохраняется UI-controlled `enable_retrieval_cache`;
- env остаётся default/fallback;
- runtime/platform setting становится effective override или наоборот.

Важно:
не создать два противоречащих source of truth.

Если hot apply невозможен:
- API/UI должны честно показывать, что нужен restart/recreate.

---

## 4. Overview response

После сохранения `/api/retrieval/overview` должен возвращать актуальный effective cache status.

Если нужно:
- минимально дополнить response;
- не делать broad API redesign.

---

# Требования

## Обязательно

- Исправить конкретную ошибку `empty body`.
- Поддержать включение `ON`.
- Поддержать выключение `OFF`.
- Не ломать существующие параметры:
  - top_k;
  - backend;
  - thresholds;
  - chunk settings;
  - other retrieval tuning.
- Frontend build должен пройти.
- API smoke должен пройти.

---

# Что нельзя делать

Нельзя:
- делать broad refactor Retrieval Settings;
- менять storage backend cache;
- переносить cache в PostgreSQL;
- включать answer cache;
- делать Redis;
- делать schema migration без необходимости;
- скрывать ошибку на frontend без исправления backend причины.

---

# Acceptance criteria

Pass успешен, если:

1. ON/OFF control отправляет непустой payload.
2. Backend принимает `enable_retrieval_cache=true`.
3. Backend принимает `enable_retrieval_cache=false`.
4. Ошибка `empty body: provide at least one tuning field` исчезла.
5. `/api/retrieval/overview` отражает состояние cache.
6. Existing tuning update still works.
7. Frontend build OK.
8. API check OK.

---

# Session log

Создать:

docs/cursor_sessions/YYYY-MM-DD_retrieval_cache_onoff_api_fix.md

Дата:
date +%F

В начало session log полностью поместить этот prompt.

---

# В engineering log обязательно включить

1. root cause;
2. changed files;
3. payload before/after;
4. backend schema/handler fix;
5. source of truth after fix;
6. true/false handling;
7. API checks;
8. frontend build result;
9. git status.

---

# Operator commands / next verification commands

В конце session log добавить конкретные команды:

- frontend build;
- backend/API syntax/check if applicable;
- точечный rebuild admin-ui/admin-api;
- curl command для проверки overview;
- UI checklist;
- git status.

Использовать только portfolio stack форму:

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml ...

Не писать обобщённо `docker compose up -d --build` без `-p portfolio-test`.

---

# Ответ в чат Cursor

В ответе предоставить только:

1. root cause;
2. changed files;
3. fix summary;
4. source of truth;
5. API check result;
6. frontend build result;
7. remaining limitations;
8. git status.

Commit НЕ выполнять.

---

## Engineering log

### 1. Root cause

`PUT /api/retrieval/tuning` строил patch как `body.model_dump(exclude_none=True)`. Если `enable_retrieval_cache` **не входил** в `TuningPutBody` (`extra="ignore"`), JSON-поле отбрасывалось → patch `{}` → HTTP 400 `empty body: provide at least one tuning field`.

UI отправлял корректно: `{"enable_retrieval_cache": true|false}`.

### 2. Changed files

- `admin_api/routes/retrieval.py` — `_tuning_put_patch_from_body`, Field description, `exclude_unset`
- `scripts/test_retrieval_tuning_settings_smoke.py` — тесты bool true/false + route patch
- `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx` — явный boolean в payload

### 3. Payload before/after

| | Before (broken) | After |
|---|-----------------|-------|
| Request | `{"enable_retrieval_cache": true}` | то же |
| Parsed patch | `{}` (field ignored) | `{"enable_retrieval_cache": true}` |
| OFF | `{"enable_retrieval_cache": false}` | `{"enable_retrieval_cache": false}` |

### 4. Backend fix

- `enable_retrieval_cache: bool | None` в `TuningPutBody` (подтверждено).
- `_tuning_put_patch_from_body`: `exclude_unset=True`, не фильтровать `false` по truthiness.

### 5. Source of truth

- Env default (`ENABLE_RETRIEVAL_CACHE`) + override в `platform_settings.retrieval_tuning`.
- Effective: `RetrievalTuningResolver` (~2.5s).
- Overview: `cache.enable_retrieval_cache` + `enable_retrieval_cache_source`.

### 6. true/false handling

`false` сохраняется в patch и DB (если ≠ env); при совпадении с env ключ strip из DB.

### 7. API checks

Локально psycopg недоступен; после rebuild:

```bash
curl -sS -X PUT http://HOST/api/retrieval/tuning \
  -H 'Content-Type: application/json' \
  -d '{"enable_retrieval_cache": true}' | jq '.effective.enable_retrieval_cache'
curl -sS http://HOST/api/retrieval/overview | jq '.cache.enable_retrieval_cache, .cache.enable_retrieval_cache_source'
```

### 8. Frontend build

`npm run build` — OK.

### 9. Git status

`git status --short` в Operator commands.

---

## Operator commands

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
python scripts/test_retrieval_tuning_settings_smoke.py  # в venv/portfolio container
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml build admin-api admin-ui
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d admin-api admin-ui
cd /opt/assistant-flow && git status --short
```

**UI:** Retrieval Settings → ON/OFF без ошибки empty body; overview обновляет статус.
