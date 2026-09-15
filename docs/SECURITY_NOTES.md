# 🛡️ Безопасность Assistant Flow

**Статус:** актуально на 2026-09-15.

Единый справочник безопасности: доступ к операционной консоли, RBAC, защита
данных при retrieval, аудит, гигиена секретов. Факты соответствуют runtime
(auth middleware `services/security/`, RBAC `services/security/rbac.py`,
миграции 007/008, `.env.example`). Архитектура контуров —
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🔑 1. Секреты и публикация репозитория

- Ключи Telegram, LLM, Proxy API, embeddings и `DATABASE_URL` — **только** через переменные окружения.
- В git: `.env.example` с плейсхолдерами; файлы `.env`, `.env.server` — в `.gitignore`, не коммитить.
- Скриншоты и логи в репозитории не должны содержать реальные токены.
- Перед публикацией проверять: `git status` чистый, в истории нет секретов, в документации нет IP внутренних серверов и приватных endpoint.

---

## 🔐 2. Модель доступа к консоли (демо-стандарт APL)

Доступ к Admin API/Admin UI — через статические Bearer-токены консоли:

| Переменная | Роль | Возможности |
|------------|------|-------------|
| `AF_ADMIN_TOKEN` | `admin` | Полный доступ: все разделы, загрузка/reindex документов, retrieval settings, evaluation |
| `AF_ADMIN_DEMO_TOKEN` | `demo` (read-only) | Только просмотр: Обзор, Сводка, Текст, RAG, Документы (база знаний в employee-scope: public + internal), Retrieval Settings (чтение), Логи, Аудит. Мутации → **403** |
| не заданы | — | Авторизация выключена — консоль открыта (локальный режим разработки) |

Правила:

- **Enforcement автоматический:** задан `AF_ADMIN_TOKEN` (или демо-токен) → режим
  защиты `required`; токенов нет → открытый режим. Явно переопределяется
  `AF_AUTH_MIDDLEWARE_MODE` (§3).
- **Авторитетная роль:** `GET /api/auth/whoami` — Bearer-токен → роль
  (`admin`/`demo`); фронтенд сохраняет сессию `{token, role}`.
- **Демо-вход в UI:** демо-токен запекается в бандл admin-ui при сборке
  (`VITE_OPS_DEMO_TOKEN` ← `AF_ADMIN_DEMO_TOKEN`) — кнопка «Войти в демо-режиме».
  **Смена демо-токена требует пересборки admin-ui.**
- **Аудит входов:** каждый успешный вызов `whoami` с валидным ops-токеном пишется
  в `admin_audit_log` как `auth.console.login` (действие `console_login`).
- **Rate-limiting / квоты на демо-вход не реализованы** — ограничение демо-режима
  только правами (read-only, 403 на мутации) и аудитом обращений.
- Сессия UI хранится в `sessionStorage` (закрывается с вкладкой).

---

## 🗝️ 3. Режимы аутентификации (`AF_AUTH_MIDDLEWARE_MODE`)

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| `disabled` | Все `/api/*` открыты | Локальная разработка (default при отсутствии токенов) |
| `optional` | Credentials разбираются → principal; маршруты не блокируются | Отладка credentials |
| `required` | Защищённые маршруты → **401** без principal | Консоль с заданным токеном; staging/production-style |

**Legacy-режим (email/password, без ops-токенов):** `POST /api/auth/login` →
HMAC-signed session token (`AF_SESSION_SECRET`, TTL `AF_SESSION_TTL_SECONDS`,
default 28800 с = 8 ч); HTTP Basic (`INITIAL_ADMIN_EMAIL` /
`INITIAL_ADMIN_PASSWORD`; bootstrap admin создаётся при старте Admin API, если
активных admin нет). Пароль в логи не пишется; refresh-токенов нет.

**Public allowlist (режим `required`):** `GET /api/health`, `GET /api/auth/me`,
`POST /api/auth/login`, `POST /api/auth/logout`, `/docs`, `/redoc`,
`/openapi.json`. Опционально (`AF_AUTH_PUBLIC_READ_ONLY=true`) — только GET для
`/api/overview`, `/api/summary` и списка `/api/documents`.

**Dev-only:** `AF_IDENTITY_DEV_HEADERS=true` — заголовки
`X-AF-Principal-Email`/`X-AF-Principal-Password` (не для production).

**Schema drift:** при `column "email" does not exist` на login — применить
`database/migrations/007_identity_foundation.sql` и перезапустить Admin API
(bootstrap невозможен без актуальной схемы `app_users`).

**Экспозиция UI в интернет:** Admin UI (8080) не выставлять в открытый доступ
без reverse proxy с TLS (demo-контур — same-origin `/api` через nginx
контейнера admin-ui), VPN/IP-allowlist/OAuth2-proxy или аналога; CORS
(`ADMIN_API_CORS_ORIGINS`) — для прямого доступа браузера к API на 8600.

---

## 🧩 4. RBAC (роль → permission)

Модель: bounded role → permission для Admin API control plane
(`services/security/rbac.py`, миграция `007_identity_foundation.sql`).

### Permissions

| Permission | Назначение |
|------------|------------|
| `documents:read` | Список/детали документов, overview, summary, preview ассетов |
| `documents:write` | Upload, edit-text |
| `documents:reindex` | Reindex документа / всей коллекции |
| `logs:read` | Логи, memory observability, evaluation read |
| `logs:forensic` | Полные тела чанков в operational logs API |
| `retrieval:read` | Retrieval overview/tuning GET |
| `retrieval:admin` | Смена активного backend, tuning PUT/DELETE |
| `settings:read` | Чтение tuning (operator) |
| `settings:write` | Evaluation import, RAGAS run, item patch |
| `users:read` / `users:write` | Управление пользователями (`users:write` — только `superadmin`) |
| `audit:read` | Чтение журнала аудита |

### Роли → permissions

| Роль | Admin API | Retrieval (data path) |
|------|-----------|----------------------|
| `end_user`/`guest` | — | guest |
| `employee` | — | employee |
| `operator` | documents (read/write/reindex) + logs read + retrieval read + settings read | employee |
| `auditor` | logs + forensic + audit + documents read + retrieval read | employee |
| `admin` | все operational permissions | admin |
| `superadmin` | operational + `users:write` | admin |
| `demo` | только чтение: documents/logs/retrieval/settings/audit read | employee (просмотр KB: public + internal) |

Bootstrap admin (identity foundation): `platform_role=admin`, `retrieval_role=admin`.

### Route enforcement

Маршруты защищены через `require_permission(...)`:

- `GET /api/documents*` → `documents:read`; upload/edit-text → `documents:write`; reindex → `documents:reindex`
- `GET /api/logs/recent`, `GET /api/memory/*` → `logs:read` (forensic-поля — при `logs:forensic`)
- `GET /api/overview`, `/api/summary` → `documents:read`
- `GET /api/retrieval/*` → `retrieval:read`; PUT/DELETE → `retrieval:admin`
- `GET /api/evaluation/*` → `logs:read`; write-операции → `settings:write`
- `GET /api/security/audit/*` → `audit:read`
- `/api/auth/*`, `/api/health` — public/session

Ответы: **401** — нет/невалидный токен; **403** — токен есть, permission нет.
Фронтенд (`AuthProvider.hasPermission()`) скрывает недоступные операции.

**Ограничения RBAC:** нет UI управления пользователями/ролями; нет ABAC /
row-level security.

---

## 🗄️ 5. Retrieval security (data path)

Безопасность пользовательского контура (Telegram RAG) — отдельный слой:

- **Retrieval-роли:** `guest` (только `visibility=public`) / `employee` (public +
  internal + legacy `unspecified`) / `admin` (unrestricted). Роль задаётся env
  (`TELEGRAM_DEFAULT_RETRIEVAL_ROLE`, списки `TELEGRAM_ADMIN_USER_IDS` /
  `TELEGRAM_GUEST_USER_IDS`) и фильтрует результаты поиска (Chroma `where` +
  post-filter; FAISS — oversample + post-filter).
- **Visibility документов:** `public` | `internal` (default для новых) |
  `restricted` — задаётся при upload, распространяется: документ → чанки →
  vector store → retrieval filter.
- **Pre-LLM masking:** перед вызовом LLM — email → `[EMAIL]`, телефон →
  `[PHONE]`, длинные числа → `[PII]`.
- **Sanitization логов:** `services/security/log_sanitizer.py` — политики
  `operational` (default: redact опасных полей + PII mask + preview) и
  `forensic_admin` (bounded поля + PII mask); markers в `processing_logs.details`.
- **Isolation кэша:** fingerprint retrieval cache учитывает роль/visibility —
  guest и employee не делят cache entry.

---

## 📜 6. Audit trail

`admin_audit_log` (базовая таблица — миграция `002_runtime_lifecycle.sql`,
расширение — `008_admin_audit_extend.sql`) — единый security audit; параллельно
`auth_login_events` (identity, 007) — auth-специфичный поток.

Поля события: `event_type` (`auth.login.success`, `security.permission.denied`,
`privileged.documents.upload`, …), `admin_user_id`, `principal_email`,
`platform_role`, `action`, `target_type`/`target_id`, `status`
(`success`/`failure`), `reason` (без секретов), `request_path`/`request_method`,
`ip_hash` (SHA256-префикс, не raw IP), `user_agent` (до 512 символов),
`execution_id`, `details` (JSONB, sanitized).

Что аудируется: auth (login success/failure, logout, console login), access
denied (401, dedup 60s), permission denied (403), privileged-операции
documents/retrieval/settings, evaluation write.

API (`audit:read`): `GET /api/security/audit/recent`,
`GET /api/security/audit/summary` (фильтры: `event_type`, `status`,
`principal_email`, `since_hours`).

UI: страница **Аудит** (`/audit`) — сценарии (не raw events), severity, split
«список / pipeline», collapsible raw JSON.

Sanitization: `AuditService` redact — `password`, `token`, `authorization`,
`secret`, `api_key` и т.п.; raw Bearer-заголовки не пишутся.

**Retention — ручной** (автоматической ротации нет). Audit не SIEM: нет
distributed tracing, immutable WORM storage. Graceful degradation: ошибка
INSERT в audit не блокирует privileged-операцию.

---

## ⚠️ 7. Границы и известные ограничения

| Ограничение | Комментарий |
|-------------|-------------|
| Single-tenant | Нет multi-tenant изоляции; external IAM/OAuth — не реализовано |
| Encrypted storage at rest | Нет (векторы и кэш в открытом виде) |
| Retention audit/логов | Ручная очистка |
| Rate-limiting консоли | Нет (права + аудит, без квот) |
| FAISS | Фильтрация post-filter, не pre-vector deny |
| SQLite retrieval cache | Хранит тексты чанков для качества HIT |

Документ не заменяет threat model и не претендует на полноту
продакшен-чеклиста — это честная карта фактического security-контура
portfolio-прототипа.

---

## 📚 Связанные документы

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — env-переменные доступа при развёртывании
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура контуров
- [USER_GUIDE.md](USER_GUIDE.md) — вход в консоль (пользовательский взгляд)
- [database/db_contract.md](../database/db_contract.md) — контракт БД (identity, аудит)