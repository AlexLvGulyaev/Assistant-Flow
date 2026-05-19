# Security walkthrough — Assistant Flow (P8)

Демонстрационный обзор security-aware RAG increment после спринтов P8.0–P8.4.  
Цель: показать **наблюдаемый** engineering increment, а не только design-документ.

Связанные материалы:

- Design: [architecture/security_rbac_design.md](../architecture/security_rbac_design.md)
- Ограничения: [SECURITY_NOTES.md](../SECURITY_NOTES.md)
- ДЗ (краткий отчёт): [homework/module5_lesson9_security_rag_report.md](../homework/module5_lesson9_security_rag_report.md)
- Session logs: `docs/cursor_sessions/2026-05-19_p8-*.md`

---

## 1. До P8 (baseline)

| Область | Состояние |
|---------|-----------|
| Retrieval | Практически **permissive** — `security_context=None` → полный corpus |
| Visibility metadata | Отсутствовала на upload; legacy `unspecified` |
| Operational logs | `chunk_text_full`, `retrieval_ready_query`, `user_input` могли уходить raw в `processing_logs` |
| Retrieval cache | Общий fingerprint без учёта роли |
| Admin API | Без auth; оператор видит всё, что записано в БД |
| Pre-LLM | Контекст LLM без обязательного PII masking |

---

## 2. После P8 (что появилось)

### 2.1 Retrieval security (P8.1)

| Роль | Доступ при retrieval |
|------|---------------------|
| **guest** | только `visibility=public` |
| **employee** | `public` + `internal` + legacy `unspecified` |
| **admin** | unrestricted (без post-filter по visibility) |

Роль → `RetrievalSecurityContext` → `filter_search_results_by_security` + Chroma `where`.

Env (Telegram): `TELEGRAM_DEFAULT_RETRIEVAL_ROLE`, `TELEGRAM_ADMIN_USER_IDS`, `TELEGRAM_GUEST_USER_IDS`.

### 2.2 Visibility-aware ingestion (P8.2)

- Upload: `public` | `internal` | `restricted` (Admin API + Admin UI).
- Default для **новых** документов: `internal`.
- Propagation: document → chunk metadata → vector store → retrieval filter.

### 2.3 Pre-LLM masking (P8.1)

Перед вызовом LLM на контексте retrieval:

- email → `[EMAIL]`
- телефон → `[PHONE]`
- длинные цифры → `[PII]`

Telemetry: `masking_applied` в stdout.

### 2.4 Logging sanitization (P8.3)

`services/security/log_sanitizer.py`:

| Policy | Когда | Поведение |
|--------|-------|-----------|
| `operational` | default (guest/employee) | redact опасных полей; PII mask; preview |
| `forensic_admin` | `retrieval_security_role=admin` | bounded поля + PII mask |

Markers в `processing_logs.details`: `sanitized`, `sanitization_policy`, `redacted_fields`, `truncated_fields`.

### 2.5 Retrieval diagnostics (P8.2 + P8.3)

Без raw тел чанков в operational mode:

- `visibility_distribution_retrieved` / `_kept`
- `retrieval_security_summary`
- `retrieval_ready_query_len` (без полного query)
- chunk rows: `source`, `score`, `text_preview`, `visibility`

### 2.6 Cache isolation (P8.1)

Fingerprint retrieval cache: `role|scope|vis=...` — guest и employee **не делят** cache entry.

---

## 3. End-to-end сценарии

### 3.1 Guest: вопрос в Telegram

```text
1. Пользователь в TELEGRAM_GUEST_USER_IDS (или role=guest)
2. policy_resolver → RetrievalSecurityContext (public_only)
3. Vector search → post-filter: internal/restricted/unspecified отброшены
4. Pre-LLM masking на оставшемся context
5. LLM → ответ
6. lifecycle.log_processing_event:
   - details с sanitized=true
   - нет retrieval_ready_query, нет chunk_text_full
   - visibility_distribution_* в summary
7. Admin UI /api/logs/recent — markers redaction, preview чанков
```

### 3.2 Employee (дефолт)

```text
1. Обычный Telegram user → role=employee
2. Retrieval: public + internal + unspecified (legacy corpus)
3. restricted → denied
4. Logs: operational sanitization
5. Cache fingerprint ≠ guest
```

### 3.3 Admin: forensic flow

```text
1. TELEGRAM_ADMIN_USER_IDS → role=admin
2. Retrieval: все visibility levels
3. to_log_details(forensic=True) + sanitization_policy=forensic_admin
4. Bounded retrieval_ready_query (cap), chunk text cap 2k, PII masked
5. Admin API slim: chunk_text_full только при forensic policy
```

---

## 4. Known limitations (честно)

| Ограничение | Почему оставлено |
|-------------|------------------|
| Admin API без auth | вне scope P8; demo single-tenant |
| Исторические `processing_logs` | нет ретро-очистки |
| Retrieval cache SQLite | полные тексты чанков для cache hit quality |
| `chat_messages` / memory | subsystem не переписывался |
| Production IAM / JWT / OAuth | запрещено в scope P8 |
| Multi-tenant isolation | нет |
| Encrypted storage at rest | нет |
| FAISS | oversample + post-filter (не pre-vector deny) |

---

## 5. Demo verification commands

### Compose (portfolio)

```bash
cd /opt/assistant-flow

COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

### Health & API

```bash
curl -sS http://localhost:8600/api/health
curl -sS "http://localhost:8600/api/logs/recent?limit=3" | head -c 4000
curl -sS "http://localhost:8600/api/documents" | head -c 2000
```

В ответе logs искать: `sanitized`, `retrieval_security_role`, `visibility_distribution_*`, `chunk_text_full_redacted`.

### Smoke tests (в контейнере)

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_1_retrieval_security_wiring_smoke.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_2_security_aware_document_ingestion_smoke.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_3_logging_sanitization_smoke.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_p8_4_security_verification_smoke.py
```

Агрегированный прогон P8.4 включает регрессию P8.1–P8.3.

### Upload для демо visibility

```bash
# public — guest должен видеть в RAG после индексации:
curl -sS -F "file=@./sample.txt" -F "visibility=public" \
  http://localhost:8600/api/documents/upload

# internal — только employee/admin:
curl -sS -F "file=@./sample.txt" -F "visibility=internal" \
  http://localhost:8600/api/documents/upload
```

### Telegram role check

```bash
# В .env контейнера assistant-flow:
# TELEGRAM_GUEST_USER_IDS=<id>
# TELEGRAM_ADMIN_USER_IDS=<id>
# пересборка: COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build assistant-flow
```

### Admin UI (без пересборки frontend)

- **Documents** — select visibility при upload (P8.2).
- **Logs / RAG** — telemetry, `retrieval_security_role`, sanitized markers (P8.3).
- Скриншоты в репозитории (если есть): см. `docs/` и session log `2026-05-19_insert_screenshots_into_docs.md`.

---

## 6. Как читать этот increment

P8 — это **сквозной bounded layer**: metadata при ingestion → filter при retrieval → mask перед LLM → sanitize при logging → verify smoke.  
Не замена enterprise IAM, а демонстрация зрелого подхода к рискам RAG-платформы в portfolio-прототипе.
