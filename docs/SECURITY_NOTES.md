# Заметки по безопасности

Известные ограничения portfolio-прототипа. Не заменяет threat model и не претендует на полноту продакшен-чеклиста.

---

## Секреты и публикация репозитория

- Ключи Telegram, LLM, Proxy API, embeddings и `DATABASE_URL` — **только** через переменные окружения.
- В git: **`.env.example`** с плейсхолдерами; файлы `.env`, `.env.server` — в `.gitignore`, не коммитить.
- Перед публичным GitHub: `git status`, сканирование истории ([GITHUB_PREP.md](GITHUB_PREP.md)), отсутствие IP внутренних серверов и приватных endpoint в документации.
- Скриншоты и логи в репозитории не должны содержать реальные токены.

---

## Admin API и Admin UI

- По умолчанию ``AF_AUTH_MIDDLEWARE_MODE=disabled`` — Admin API открыт; для staging задайте ``required`` и используйте login (P9.3) или Basic.
- **P9.3:** ``POST /api/auth/login`` выдаёт Bearer token; задайте ``AF_SESSION_SECRET`` в production (не dev fallback). Режим ``required`` validated после применения ``007_identity_foundation.sql`` (см. P9.3a).
- **P9.3a:** при ``column "email" does not exist`` на login — schema drift: применить ``database/migrations/007_identity_foundation.sql`` к PostgreSQL, затем restart Admin API. Bootstrap admin невозможен без актуальной схемы ``app_users``.
- Admin UI (**8080**) хранит token в ``sessionStorage``; не выставлять в открытый интернет без:
  - reverse proxy с TLS;
  - VPN, IP allowlist, OAuth2-proxy или аналога;
  - ограничения rate limit и размера тел.

---

## CORS и сеть

- `ADMIN_API_CORS_ORIGINS` — сузить под реальные origin UI вне localhost.
- В demo-compose Postgres (**5433**), Chroma (**8001**), Weaviate (**8089**) публикуются на хост — на публичной машине ограничить firewall / bind address.

---

## Данные

- Превью ассетов через API — политика хранения и удаления на стороне оператора.
- Векторные индексы и Postgres могут содержать содержимое загруженных документов; не использовать демо-стек для реальных персональных данных без оценки рисков.

---

## RAG и политики доступа

- **P8.1 (2026-05-19):** основной Telegram RAG path передаёт `security_context` через `policy_resolver` (env: `TELEGRAM_DEFAULT_RETRIEVAL_ROLE`, `TELEGRAM_ADMIN_USER_IDS`, `TELEGRAM_GUEST_USER_IDS`).
- Роли: **guest** → только `visibility=public`; **employee** → public + internal + legacy `unspecified`; **admin** → unrestricted.
- Дефолтная роль Telegram: **employee** (совместимость с corpus без явной visibility).
- **P8.2:** при upload через Admin API задаётся `visibility` (`public` | `internal` | `restricted`); default **internal**; metadata попадает в chunk/vector store. Legacy `unspecified` не меняется.
- Admin API по-прежнему **без** auth.
- Design: [architecture/security_rbac_design.md](architecture/security_rbac_design.md).

---

## PII и операционные логи

- **P8.3 (2026-05-19):** централизованный `services/security/log_sanitizer.py` — sanitization перед записью в `processing_logs` и при отдаче через Admin API (`truncate_details` / `_slim_details_for_payload`).
- Operational policy: redact `user_input`, `retrieval_ready_query`, `chunk_text_full`, `transcript`, `context`, `query`, `raw_payload`; PII masking + length caps; markers `sanitized`, `redacted_fields`, `truncated_fields`, `sanitization_policy`.
- Forensic (role=admin / `forensic=True`): bounded поля с PII masking, не raw unlimited.
- **P8.1:** pre-LLM masking перед LLM; retrieval cache изолирован по security fingerprint.
- Admin API `/api/logs/recent` без auth — оператор видит записанное в БД (новые записи — sanitized; исторические строки — без ретро-очистки).
- STT: `transcript` redact в operational logs → `transcript_preview` + `transcript_chars` (через lifecycle sanitizer).
- **Known limitations:** retrieval cache SQLite (полные тексты чанков для hit quality); `chat_messages` / memory subsystem; исторические `processing_logs` в PostgreSQL.
- **P8.4:** верификация — `scripts/test_p8_4_security_verification_smoke.py`; отчёт для ДЗ — `docs/homework/module5_lesson9_security_rag_report.md`.
- **P8.5:** demo walkthrough — [security/security_walkthrough.md](security/security_walkthrough.md); session logs P8.1–P8.4 приведены к self-contained формату (полные prompt'ы встроены).

---

## Identity & control plane (P9.0–P9.1)

- **P9.0:** архитектура — [architecture/identity_and_security_architecture.md](architecture/identity_and_security_architecture.md).
- **P9.1 (2026-05-19):** identity foundation — `app_users` расширен, `user_channel_identities`, `auth_login_events`, `IdentityService`, `PrincipalContext`, middleware foundation, bootstrap admin.
- Admin API auth: по умолчанию **выключен** (`AF_AUTH_MIDDLEWARE_MODE=disabled`); для проверки Basic auth — `optional` или `required` + `INITIAL_ADMIN_*`.
- Миграция: `database/migrations/007_identity_foundation.sql`.
- **P9.2 (2026-05-19):** enforcement middleware — режимы `disabled` / `optional` / `required`; `GET /api/auth/me`; защита Admin API в `required`. См. [security/auth_modes.md](security/auth_modes.md).
- **P9.3 (2026-05-19):** Admin UI login/session (Bearer); **P9.3a:** runtime validation выявила schema drift — перед login обязательна миграция 007.
- **P9.4 (2026-05-19):** real RBAC — `services/security/rbac.py`, `require_permission` на Admin API routes, UI `hasPermission`. Bootstrap = `admin`. См. [security/rbac_permissions.md](security/rbac_permissions.md).
- **P9.5 (2026-05-19):** security audit trail — `admin_audit_log`, `AuditService`, `GET /api/security/audit/*`. См. [security/audit_and_observability.md](security/audit_and_observability.md).
- **P9.5b (2026-05-19):** Security console — narrative scenarios, severity, retrieval/RBAC visualization в Admin UI `/audit`. См. [security/security_console_walkthrough.md](security/security_console_walkthrough.md).
- `app_users` / `PrincipalContext` / RBAC используются в Admin API; retrieval role bridge подключён (P9.1–P9.4).
- Ограничения control-plane: нет user-management UI, нет multi-tenant isolation, нет external IAM/OAuth, retention audit — вручную оператором.
- Направление: local auth first; Keycloak/OAuth — P9.7; multi-tenant — P9.6.

---

## Честная оценка зрелости

Проект демонстрирует архитектуру и эксплуатацию AI-сервисов, но **не** сертифицирован как готовое мультиарендное или compliance-ready решение. Data-path security (P8) и control-plane security (P9) — разные этапы зрелости. Деградация и восстановление — best-effort в коде, не регламентированный SLA.
