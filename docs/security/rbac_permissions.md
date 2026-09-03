# 🛡️ RBAC permissions (P9.4)

Bounded role → permission model для Admin API control plane.

## Permissions

| Permission | Назначение |
|------------|------------|
| `documents:read` | Список/детали документов, overview, summary, preview |
| `documents:write` | Upload, edit-text |
| `documents:reindex` | Reindex document / all |
| `logs:read` | `/api/logs/recent`, memory observability, evaluation read |
| `logs:forensic` | Полные chunk bodies в operational logs API |
| `retrieval:read` | Retrieval overview/tuning GET |
| `retrieval:admin` | Active backend switch, tuning PUT/DELETE |
| `settings:read` | (зарезервировано; operator: read tuning) |
| `settings:write` | Evaluation import, RAGAS run, item patch |
| `users:read` | (зарезервировано P9.5+) |
| `users:write` | Только `superadmin` |
| `audit:read` | Auditor read-only audit prep |

## Roles → permissions

| Platform role | Admin API | Retrieval (P8) |
|---------------|-----------|------------------|
| `end_user` / guest | — | guest |
| `employee` | — | employee |
| `operator` | documents + logs read + reindex + retrieval read | employee |
| `auditor` | logs + forensic + audit + documents read | employee |
| `admin` | все operational | admin |
| `superadmin` | operational + `users:write` | admin |

**Bootstrap admin (P9.1):** `platform_role=admin`, `retrieval_role=admin`.

## Route mapping (основное)

| Route | Permission |
|-------|------------|
| `GET /api/documents*` | `documents:read` |
| `POST /api/documents/upload`, `edit-text` | `documents:write` |
| `POST /api/documents/reindex` | `documents:reindex` |
| `GET /api/logs/recent` | `logs:read` (+ forensic fields при `logs:forensic`) |
| `GET /api/retrieval/overview`, `tuning` | `retrieval:read` |
| `PUT/DELETE /api/retrieval/*` | `retrieval:admin` |
| `GET /api/overview`, `/api/summary` | `documents:read` |
| `GET/POST /api/evaluation/*` read | `logs:read` |
| `POST/PATCH /api/evaluation/*` write | `settings:write` |
| `GET /api/memory/*` | `logs:read` |
| `GET /api/security/audit/*` | `audit:read` |
| `GET /api/auth/*` | public / session (без RBAC) |

## Auth modes и RBAC

| `AF_AUTH_MIDDLEWARE_MODE` | RBAC enforcement |
|---------------------------|------------------|
| `disabled` | выключен (demo) |
| `optional` | только для authenticated principal |
| `required` | authenticated + permissions |

- **401** — не аутентифицирован (middleware / dependency).
- **403** — аутентифицирован, но нет permission.

## Frontend

`AuthProvider.hasPermission()` — скрытие upload/reindex/retrieval admin при отсутствии прав.

## Ограничения

- Нет UI управления пользователями / ролями.
- Нет ABAC / row-level security.
- In-memory session revoke (P9.3) без RBAC на token payload permissions (роль перечитывается из token + `resolve_permissions`).
