# 🛡️ Security console — operational walkthrough (P9.5b)

Страница **Безопасность** (`/audit`) — operational console Assistant Flow, не SIEM.

## Layout (канон AF, P9.5c)

| Зона | Содержание |
|------|------------|
| Верх | Summary 24ч, фильтры |
| Слева | Список **сценариев** (не raw events): время, severity, результат, актор, title |
| Справа | **Единый pipeline** (всегда одинаковая структура): |

### Pipeline (правая колонка)

```text
A. Пользователь
   → B. Система — интерпретация (включая retrieval / visibility policy)
   → C. Решение системы (RBAC + retrieval)
   → D. Последствия / enforcement
   → E. Technical timeline
```

Модель: **Пользователь ↔ Система**. Retrieval security — строки внутри B/C, не отдельный виджет.

## Сценарии

### Auth

| Событие | Severity | Описание |
|---------|----------|----------|
| `auth.login.success` | info | Успешный вход, сессия выдана |
| `auth.login.failure` | warning | Неверные учётные данные |
| `auth.logout` | info | Выход, отзыв токена |
| `security.access.denied` | warning | 401 — нет/невалидный Bearer |

### RBAC

| Событие | Severity | Описание |
|---------|----------|----------|
| `security.permission.denied` | error | 403 — недостаточно permission |

### Retrieval / LLM (P8 bridge)

Для событий retrieval и permission denied UI показывает панель **Retrieval / LLM security**:

- retrieval role (guest / employee / admin);
- допустимая visibility;
- scope (public_only / employee_kb / unrestricted).

Это отражает `policy_resolver` и `result_filter` без отдельного SIEM.

### Documents

| Событие | Описание |
|---------|----------|
| `privileged.documents.upload` | Загрузка |
| `privileged.documents.reindex` | Переиндексация |
| `privileged.documents.edit_text` | Редактирование |

## RBAC demo principals (smoke)

| Роль | Audit UI | Retrieval tuning | Documents |
|------|----------|------------------|-----------|
| admin | ✓ `audit:read` | ✓ `retrieval:admin` | ✓ write |
| auditor | ✓ read-only | ✗ | ✗ write |
| operator | ✗ | ✗ | ✓ read/write (без reindex) |
| employee / guest | ✗ | ✗ (platform) | ✗ |

Создание тестовых пользователей: `scripts/test_p9_5b_security_scenarios.py`.

## Ограничения

- Нет distributed tracing / OpenSearch / heatmaps.
- Invalid/expired token → тот же `security.access.denied`, не отдельный event_type.
- Retention audit — manual (см. P9.5).

## Operator

```bash
docker exec assistant-flow-assistant-flow-1 python scripts/test_p9_5b_security_scenarios.py
cd frontend/admin-ui && npm run build
```
