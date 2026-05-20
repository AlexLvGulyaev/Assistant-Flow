# Audit trail и security observability (P9.5)

Bounded production-style audit foundation — **не** SIEM.

## Модель события

Таблица `admin_audit_log` (миграция `008_admin_audit_extend.sql`):

| Поле | Описание |
|------|----------|
| `event_type` | `auth.login.success`, `security.permission.denied`, `privileged.documents.upload`, … |
| `admin_user_id` | UUID principal (legacy column name) |
| `principal_email`, `platform_role` | Снимок actor |
| `action` | Короткий код действия |
| `target_type`, `target_id` | Объект операции |
| `status` | `success` \| `failure` |
| `reason` | Код причины (без секретов) |
| `request_path`, `request_method` | HTTP контекст |
| `ip_hash` | SHA256 prefix IP (не raw IP) |
| `user_agent` | Обрезан до 512 символов |
| `execution_id` | Связь с pipeline при наличии |
| `details` | JSONB, sanitized |

Параллельно: `auth_login_events` (P9.1) — auth-specific stream; `admin_audit_log` — единый security audit.

## Что аудируется

| Категория | event_type (примеры) |
|-----------|----------------------|
| Auth | `auth.login.success`, `auth.login.failure`, `auth.logout` |
| Security | `security.access.denied` (401, dedup 60s), `security.permission.denied` (403) |
| Documents | `privileged.documents.upload`, `.reindex`, `.edit_text` |
| Retrieval | `privileged.retrieval.backend.switch`, `.settings.update`, `.settings.delete` |
| Settings | `privileged.settings.evaluation.*` |

## API

| Endpoint | Permission |
|----------|------------|
| `GET /api/security/audit/recent` | `audit:read` |
| `GET /api/security/audit/summary` | `audit:read` |

Фильтры: `event_type`, `status`, `principal_email`, `since_hours`, pagination.

## Admin UI (P9.5b Security console)

Страница **Безопасность** (`/audit`) — operational security console:

- narrative scenarios (auth, RBAC, retrieval, documents);
- severity (info / warning / error / critical);
- left/right split как Logs/RAG;
- **canonical pipeline A–E** (Пользователь ↔ Система); retrieval policy встроен в B/C, не отдельный виджет;
- collapsible raw JSON.

См. [security_console_walkthrough.md](security_console_walkthrough.md).

## Sanitization

`AuditService` redact: `password`, `token`, `authorization`, `secret`, `api_key`, …  
Не пишутся raw Bearer headers.

## Retention

Audit logs **растут** без автоматической ротации. Retention — manual/operator-managed (SQL cleanup / partition — future). Не реализован subsystem retention в P9.5.

## Ограничения

- Нет SIEM / OpenSearch / distributed tracing rewrite.
- Нет immutable WORM storage.
- Graceful degradation: ошибка INSERT в audit не блокирует privileged action.
- Invalid/expired token → anonymous → `security.access.denied` (не отдельный event per token parse).

## Operator

```bash
# после миграции 008:
cat database/migrations/008_admin_audit_extend.sql | \
  docker exec -i portfolio-test-postgres-1 psql -U assistant -d assistant_flow

docker exec portfolio-test-assistant-flow-1 python scripts/test_p9_5_audit_smoke.py
```
