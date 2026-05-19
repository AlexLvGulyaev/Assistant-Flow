# Модуль 5, урок 9 — Security & RAG в Assistant Flow

Краткий инженерный отчёт по реализации разграничения доступа, защиты данных и observability в portfolio-прототипе **assistant-flow** (спринты P8.0–P8.3).

---

## Роли и retrieval

| Роль | Что видит при retrieval | Что запрещено |
|------|------------------------|---------------|
| **guest** | Только чанки с `visibility=public` | `internal`, `restricted`, legacy без метки не расширяют доступ |
| **employee** (дефолт Telegram) | `public` + `internal` + legacy `unspecified` | `restricted` и явно закрытые документы |
| **admin** | Полный corpus без post-filter по visibility | Ограничения только политикой приложения, не RBAC IAM |

Роль задаётся через `security_context` (Telegram: env `TELEGRAM_*_USER_IDS`, `TELEGRAM_DEFAULT_RETRIEVAL_ROLE`). Фильтрация — post-retrieval (`result_filter`) и при Chroma — `where` по allowed visibility.

---

## Меры защиты (реализовано)

- **Visibility-aware ingestion** — при upload метка `public` / `internal` / `restricted`; default для новых документов — `internal`.
- **Retrieval filtering** — отсечение чанков вне роли до формирования контекста LLM.
- **Pre-LLM masking** — email, телефон, длинные цифровые последовательности в контексте модели.
- **Logging sanitization** — централизованный `log_sanitizer`: operational vs forensic; redaction `user_input`, `retrieval_ready_query`, `chunk_text_full`, `transcript`.
- **Cache isolation** — fingerprint retrieval cache включает роль/scope (guest ≠ employee).
- **Diagnostics redaction** — в логах: счётчики visibility, security summary, preview чанков; без raw PII в operational mode.

---

## Operational conclusion

Assistant Flow демонстрирует **сквозной, но bounded** security layer для RAG: от метаданных при индексации до фильтрации при ответе и sanitization при записи в `processing_logs`. Это не production IAM: Admin API и UI остаются без аутентификации; multi-tenant изоляция и шифрование хранилища не заявлены.

Для оператора важны **явные markers** (`sanitized`, `redacted_fields`, `sanitization_policy`): по ним видно, что часть payload намеренно скрыта. Forensic-режим (role=admin) даёт расширенную диагностику с усечением и PII-mask, но не unlimited raw export.

Риски, осознанно оставленные вне scope P8: исторические строки в PostgreSQL, полные тексты в retrieval cache SQLite, содержимое `chat_messages` / memory. Их нужно учитывать при развёртывании demo-стека на чувствительных данных.

Верификация P8.4: smoke `scripts/test_p8_4_security_verification_smoke.py` + регрессия P8.1–P8.3. Для полного e2e с API — portfolio compose и curl к `/api/health`, `/api/logs/recent`, `/api/documents`.

---

## Ссылки в репозитории

- Design: `docs/architecture/security_rbac_design.md`
- Ограничения: `docs/SECURITY_NOTES.md`
- **Demo walkthrough:** `docs/security/security_walkthrough.md` (P8.5)
- Session logs: `docs/cursor_sessions/2026-05-19_p8-*.md` (self-contained, полные prompt'ы)
