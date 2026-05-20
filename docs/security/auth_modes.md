# Режимы аутентификации Admin API (P9.2)

Переменная: **`AF_AUTH_MIDDLEWARE_MODE`**

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| **`disabled`** (default) | Principal anonymous; все `/api/*` открыты | Локальная разработка, legacy demo, обратная совместимость |
| **`optional`** | Basic auth разбирается → principal; маршруты **не** блокируются | Постепенное внедрение, отладка credentials |
| **`required`** | Защищённые маршруты → **401** без Basic auth | Staging / production-style single-tenant |

## Bootstrap admin

```bash
INITIAL_ADMIN_EMAIL=admin@example.local
INITIAL_ADMIN_PASSWORD=change-me-strong
```

При старте Admin API (lifespan) создаётся platform admin, если активных admin ещё нет.  
Пароль **не** пишется в логи.

## Аутентификация запросов

### Admin UI (P9.3) — Bearer session token

```bash
TOKEN=$(curl -sS -X POST http://localhost:8600/api/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$INITIAL_ADMIN_EMAIL\",\"password\":\"$INITIAL_ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8600/api/auth/me
curl -sS -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8600/api/auth/logout
```

Токен: HMAC-signed payload (`AF_SESSION_SECRET`, TTL `AF_SESSION_TTL_SECONDS`, default 8h).  
Хранение в UI: `sessionStorage` (`af_admin_access_token`). Refresh-token platform **нет**.

### HTTP Basic (по-прежнему)

```bash
curl -u "$INITIAL_ADMIN_EMAIL:$INITIAL_ADMIN_PASSWORD" \
  http://localhost:8600/api/logs/recent?limit=1
```

Статус principal:

```bash
curl -sS http://localhost:8600/api/auth/me
```

## Поведение Admin UI по режимам

| Режим | UI |
|-------|-----|
| `disabled` | Login не обязателен; консоль открыта (demo) |
| `optional` | Login доступен; можно работать без сессии |
| `required` | Login обязателен; protected routes → `/login` |

## Public allowlist (режим `required`)

Всегда без auth:

- `GET /api/health`
- `GET /api/auth/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `/docs`, `/redoc`, `/openapi.json`

Опционально (`AF_AUTH_PUBLIC_READ_ONLY=true`) — только **GET**:

- `/api/overview`
- `/api/summary`
- `/api/documents` (список; detail/upload/reindex остаются protected)

Все остальные `/api/*` требуют authenticated principal.

## Защищённые категории (required)

- Загрузка и reindex документов
- Логи и сессии (PII)
- Retrieval settings / active backend
- Evaluation / RAGAS
- Preview ассетов
- Редактирование документов

## Dev-only

`AF_IDENTITY_DEV_HEADERS=true` — заголовки `X-AF-Principal-Email` / `X-AF-Principal-Password` (не для production).

## RBAC (P9.4)

В режимах `optional` (authenticated) и `required` маршруты Admin API проверяют **permissions**, не только login.

- **401** — нет сессии.
- **403** — сессия есть, permission нет.

Матрица: [rbac_permissions.md](rbac_permissions.md).

## Связанные документы

- [identity_and_security_architecture.md](../architecture/identity_and_security_architecture.md)
- [rbac_permissions.md](rbac_permissions.md)
- [security_walkthrough.md](security_walkthrough.md)
- [SECURITY_NOTES.md](../SECURITY_NOTES.md)
