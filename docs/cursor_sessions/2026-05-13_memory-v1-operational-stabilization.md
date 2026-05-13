# Engineering log (2026-05-13): Memory v1 operational stabilization + contamination audit

**Календарная дата:** `2026-05-13` (по `date +%F` на момент работ).

## 1. Полный prompt

Стабилизация / верификация / hardening Memory v1 (не новый feature-эпик): engineering log с полным запросом пользователя; contamination audit; E2E verification guidelines; budget; SoT; lifecycle; UI stabilization; smoke; invariants; deferred; **commit не выполнять**. Контекст: Memory v1 PG, observability, Sessions UI уже есть.

## 2. Workspace snapshot

`/opt/assistant-flow` — `interfaces/telegram_bot.py`, `services/rag_query_service.py`, `services/memory_observability_service.py`, `frontend/admin-ui/src/pages/MemoryPage.tsx`, `scripts/test_memory_v1_contamination_smoke.py`, этот файл.

## 3. Git status before

```
## main...origin/main [ahead 14]
 M admin_api/... M frontend/... M interfaces/telegram_bot.py M repositories/...
 M services/rag_query_service.py ... (см. рабочее дерево до правок стабилизации)
?? admin_api/routes/sessions.py
?? docs/cursor_sessions/2026-05-13_memory-*.md
?? services/memory_observability_service.py
?? scripts/test_memory_observability_admin_smoke.py
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? frontend/admin-ui/src/pages/MemoryPage.tsx
...
```

## 4. Stabilization findings

| Область | Находка | Действие |
|--------|---------|----------|
| **RAG LLM history** | В `RagQueryService._rag_llm` / `_fallback_llm` использовался жёсткий `history[-6:]`, расходящийся с `TELEGRAM_MEMORY_MAX_LLM_MESSAGES` и с тем, что загружает Telegram/PG (`memory_load_done.messages_loaded`). | Введён `_history_tail_for_llm()` на базе `AppConfig.telegram_memory_max_llm_messages` (cap 500). |
| **Persist non-RAG** | OCR / voice / text ветки писали в `chat_messages` `assistant_text` после `format_for_telegram(...)` — артефакты разметки в персистентной истории (не KB chunks, но загрязнение «чистого» диалога). | Persist: OCR — сырое `(recognized).strip()`; voice/text — `(result_text).strip()`; UI по-прежнему `format_for_telegram` только для отправки. |
| **RAG persist** | Уже было: `assistant_text=(result.answer).strip()` — ок. | Подтверждено аудитом + smoke. |
| **`processing_logs` rag_answer_done** | Содержит `answer_text` / RAG diagnostics — **не** пишется в `chat_messages`. | Задокументировано как разделение каналов. |
| **Memory observability API** | Детали memory_* уже allowlist; summary не содержал явного поля tail cap для оператора. | Добавлены `llm_conversation_tail_cap` в summary и в `budget` session detail. |
| **Memory UI** | Lifecycle выводил `JSON.stringify(details)` — риск «простыни» и визуального шума. | Компактная однострочная строка из allowlist-ключей + ellipsis; truncation user column. |

## 5. Contamination audit

### `chat_messages` (персистентность)

- **RAG:** только `user_text` + `result.answer` (без KB context, без system prompt из сборки RAG).
- **OCR / voice / text:** после правки — без Telegram formatter в persist; ранее — риск markdown/HTML в теле assistant (исправлено).
- **Метаданные сообщений:** `memory_layer: dialog_history` — не содержит чанков.
- **Дубликаты assistant:** одна пара user+assistant на ход persist в этих путях.

### `processing_logs`

- **rag_answer_done:** diagnostics, `answer_text` preview — ожидаемо для ops; **не** смешивать с `chat_messages`.
- **memory_*** stages: в коде Telegram — только метаданные в `details` (session_id, counts, latency, command); тексты сообщений не пишутся.
- **Voice `route_selected`:** в логах может быть полный `transcript` — PII/объём; **не** `chat_messages`; оставить как open issue для отдельного slimming.

### Memory / session API

- `MemoryObservabilityService._slim_memory_details` — allowlist; session `recent_turns` — только усечённые превью из `content` (user/assistant).

### Telegram runtime RAG path

- История для LLM: из PG или in-memory snapshot; в LLM уходит `conversation_history` без retrieval chunks (chunks только внутри `_rag_llm` system + context).

### RAG reply formatting

- Telegram: `format_for_telegram(reply)` для UI; persist — сырой answer.

### Источники / diagnostics

- Источники в `RagQueryResult.sources`; инструкция LLM не добавлять раздел «Источники»; риск нарушения моделью остаётся (open issue).

## 6. Smoke results

```bash
python3 scripts/test_memory_v1_contamination_smoke.py
# OK: memory_v1_contamination_smoke (static checks)

cd frontend/admin-ui && npm run build
# ✓ built
```

Живой multi-turn Telegram / ручной `/clear` в агентской среде **не выполнялись** (нет привязанного runtime); рекомендация оператору: прогнать чеклист из §7 вручную на стенде.

## 7. Screenshots / findings summary

**Скриншоты:** в среде агента не создавались. Итоги зафиксированы в §4–6 и в кодовых правках выше.

## 8. Open issues

- **LLM может всё же добавить источники** в текст ответа — тогда они попадут в `chat_messages` при текущем контракте.
- **`processing_logs` voice:** полный transcript в `details` — объём/PII; вынести в отдельный hardening.
- **Пер-process in-memory fallback:** при `TELEGRAM_PG_CONVERSATION_MEMORY=false` история в RAM; рестарт процесса обнуляет буфер — ожидаемо; PG история сохраняется.
- **Индекс по `details->>'session_id'`** для memory_* — при росте логов может понадобиться (deferred в прошлом логе observability).

## 9. Deferred items

- Отдельный slimming voice intake `transcript` в processing_logs.
- Автоматический E2E против реальной Telegram+PG (Playwright / staging job).
- Semantic / vector / summarization memory (вне scope).

## 10. Confirmed operational invariants

- **Runtime retrieval context ≠ persistent memory:** KB context и system assembly RAG остаются только в runtime LLM messages; в `chat_messages` пишутся только user query и assistant answer (без чанков).
- **No retrieval chunks in `chat_messages`:** путь записи — `append_message` с `content` из user/answer текста; RAG chunks не передаются в persist.
- **No system prompts persisted:** роли в PG — user/assistant; system prompt не вызывается `record_message` для диалога.
- **PG is source of truth** для short-term при `DATABASE_URL` + `TELEGRAM_PG_CONVERSATION_MEMORY=true`; иначе явный fallback in-memory в конфиге/UI.
- **Clear/reset** ротируют сессию (Memory v1); старые строки не удаляются.
- **Memory lifecycle observable:** стадии `memory_load_*`, `memory_append_done`, `memory_session_cleared`, `memory_error` без текстов сообщений в `details` (контракт кода).

## 11. Git status after

```
## main...origin/main [ahead 14]
 M PROJECT_STATE.md
 M admin_api/app.py
 M admin_api/deps.py
 M frontend/admin-ui/src/App.tsx
 M frontend/admin-ui/src/api/client.ts
 M frontend/admin-ui/src/navigation/routes.ts
 M frontend/admin-ui/src/styles/globals.css
 M frontend/admin-ui/tsconfig.tsbuildinfo
 M interfaces/telegram_bot.py
 M repositories/processing_logs_repository.py
 M repositories/session_repository.py
 M services/cache/caching_retrieval_backend.py
 M services/cache/retrieval_cache_key.py
 M services/chat_session_service.py
 M services/memory/conversation_memory_service.py
 M services/rag_query_service.py
 M services/rag_types.py
 M utils/config.py
 M utils/telegram_user_state.py
?? admin_api/routes/sessions.py
?? docs/cursor_sessions/2026-05-13_chroma-faiss-retrieval-routing-audit-engineering-log.md
?? docs/cursor_sessions/2026-05-13_memory-architecture-legacy-analysis.md
?? docs/cursor_sessions/2026-05-13_memory-observability-and-sessions-ui.md
?? docs/cursor_sessions/2026-05-13_memory-v1-operational-stabilization.md
?? docs/cursor_sessions/2026-05-13_memory-v1-pg-backed-short-term-memory.md
?? frontend/admin-ui/src/pages/MemoryPage.tsx
?? scripts/test_memory_observability_admin_smoke.py
?? scripts/test_memory_v1_contamination_smoke.py
?? scripts/test_memory_v1_pg_short_term_smoke.py
?? scripts/test_retrieval_backend_identity_smoke.py
?? services/memory_observability_service.py
```
