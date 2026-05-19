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

- Маршруты `/api` **без** встроенной аутентификации и RBAC.
- Любой с сетевым доступом к порту **8600** может читать логи, обзор, загружать документы и запускать reindex — в объёме реализованного API.
- Admin UI (**8080**) рассчитан на **demo / single-tenant**; не выставлять в открытый интернет без:
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

## Честная оценка зрелости

Проект демонстрирует архитектуру и эксплуатацию AI-сервисов, но **не** сертифицирован как готовое мультиарендное или compliance-ready решение. Деградация и восстановление — best-effort в коде, не регламентированный SLA.
