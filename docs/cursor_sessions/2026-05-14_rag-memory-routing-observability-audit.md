# Engineering log: RAG / Logs UI, routing diagnostics, documents raw preview

**Date:** 2026-05-14 (`date +%F`)

---

## Full development prompt (verbatim)

Cursor, нужен точечный patch по RAG/Logs UI и routing diagnostics.

1. Logs: убрать дублирующее слово «ДОКУМЕНТ»

Сейчас в Logs для document route отображается:

doc ДОКУМЕНТ · УСПЕШНО

Нужно:

doc УСПЕШНО

То есть:

* badge `doc` оставить;
* текстовое название route/entity «ДОКУМЕНТ» рядом убрать;
* не ломать другие route labels;
* для RAG/Text/Memory поведение не менять, если там нет такого дублирования.

2. RAG UI: вернуть серый label `RAG-запрос`, если retrieval_ready_query совпадает с user query

Сейчас после скрытия `RAG-запрос` у обычных запросов возникла визуальная асимметрия.

Нужно:

* если retrieval_ready_query отсутствует → показывать обычный серый label `RAG-запрос`, как раньше;
* если retrieval_ready_query есть и совпадает с raw user query → показывать обычный серый label `RAG-запрос`;
* если retrieval_ready_query есть и отличается от raw user query → показывать синюю раскрывающуюся action-ссылку `RAG-запрос`, по которой видно transformed retrieval query.

Иными словами:

* серый label = обычный случай;
* синяя ссылка = есть diagnostic value, потому что query был transformed.

3. Logs: синие details-ссылки оставить

В Logs синие details/JSON preview уже выглядят нормально.
Не откатывать.

4. Routing diagnostics: объяснить, почему одни memory/meta-dialog вопросы идут в retrieval, а другие нет

Нужно найти в коде:

* какой обработчик / router / classifier решает, запускать retrieval или нет;
* какие признаки используются;
* почему вопрос `О чем был мой предыдущий вопрос?` ушел без retrieval;
* почему вопросы `Там — это где?` и `Сколько вопросов об этой системе я Вам задал в процессе диалога?` ушли в retrieval.

Особенно важно:
эти вопросы явно относятся к контексту диалога, и в идеале не должны запускать retrieval.

5. Proposal: memory/meta-dialog intent should skip retrieval

Подготовить короткое инженерное предложение:

Если вопрос относится к истории текущего диалога:

* предыдущий вопрос;
* о чем мы говорили;
* что я спросил;
* сколько вопросов я задал;
* что ты ответил;
* там/это/она/он в контексте предыдущей реплики;

то retrieval лучше пропускать, если query классифицирован как memory/meta-dialog intent.

Причины:

* экономия токенов;
* меньше latency;
* меньше retrieval noise;
* меньше риск, что LLM начнет опираться на нерелевантные chunks.

Важно:
пока НЕ внедрять радикальную новую маршрутизацию без отдельного решения.
Сейчас:

* исправить UI пункты 1–2;
* провести code audit routing logic;
* описать найденную причину;
* дать proposal для следующего шага.

6. Documents UI: вернуть просмотр сырого документа

Обнаружено, что в консоли Documents пропал просмотр сырого документа.

Нужно проверить:
- Documents page;
- document detail view;
- preview/raw text component;
- API endpoint, который отдаёт raw/original document content.

Ожидаемое поведение:
в карточке документа оператор должен иметь доступ к просмотру сырого документа / исходного текста, как было раньше.

Важно:
- не подменять raw preview чанками;
- не показывать только indexed chunks;
- raw document preview нужен отдельно от chunks/version diagnostics;
- если endpoint есть, но UI его потерял — вернуть UI;
- если endpoint сломан — описать root cause и исправить минимально.

В engineering log добавить:
- почему raw document preview пропал;
- какие файлы исправлены;
- как проверить вручную.

7. Engineering log

Создать:

docs/cursor_sessions/YYYY-MM-DD_rag-memory-routing-observability-audit.md

Дата через:

date +%F

Включить:

* полный prompt;
* changed files;
* root cause по UI;
* где находится routing decision;
* почему разные memory-вопросы ведут себя по-разному;
* proposal по skip retrieval for memory/meta-dialog intent;
* operator commands.

Commit НЕ выполнять.

---

## Changed files

| Area | File |
|------|------|
| Logs / Audio list row label | `frontend/admin-ui/src/utils/operationalLabels.ts` — `showLogsRouteLabelBesideModalityBadge()` |
| Logs list + detail | `frontend/admin-ui/src/pages/LogsPage.tsx` |
| Audio list (same list pattern) | `frontend/admin-ui/src/pages/AudioPage.tsx` |
| RAG «RAG-запрос» foot | `frontend/admin-ui/src/pages/RagPage.tsx` |
| Documents detail preprocessing + raw panel | `frontend/admin-ui/src/pages/DocumentsPage.tsx` |
| TS type for detail `preprocessing` | `frontend/admin-ui/src/api/client.ts` |
| API: attach preprocessing to detail bundle | `services/admin_service.py` |

---

## UI root causes

### 1. Duplicate «ДОКУМЕНТ»

List row rendered **both** `OperationalModalityBadge` (`doc`) **and** `routeLabelRu(routeKey)` → «Документ» in uppercase. For the document bucket the badge already disambiguates the modality; the extra route word was redundant.

**Fix:** `showLogsRouteLabelBesideModalityBadge(routeKey)` is false only for normalized route `document`; then only `statusLabelRu` is shown after the badge (`doc УСПЕШНО`). Other routes unchanged.

### 2. RAG «RAG-запрос» asymmetry

After retrieval-ready observability, the grey foot was omitted whenever the expandable block was hidden (same query / no field), so the right column still had «RAG-ответ» but the left had no foot.

**Fix:** If the blue `<details>` is not shown (no `retrieval_ready_query` or same normalized string as user query), render the original `<p className="rag-io-foot muted">RAG-запрос</p>`.

### 3. Documents raw preview «пропал»

**Cause:** The **inline** raw block was gated on `selected.preprocessing?.preview_raw`. `selected` comes from **GET `/api/documents`** list, where `preprocessing` is merged from recent logs by filename keys. The **detail** response from **`get_document_detail_bundle`** did not include a `preprocessing` object at all, so after navigation or key mismatches the right-hand card could lose preprocessing even though `timeline` still contained upload events with `details.preprocessing.preview_raw`.

**Fix:**

1. **Backend:** `get_document_detail_bundle` now scans `timeline_rows` for `document_upload_pipeline_done` / `admin_document_uploaded`, matches `source_filename` to `indexed_target_filename` / `filename` / `original_upload_filename`, and returns the same public preprocessing dict as the list endpoint (`preview_raw`, sizes, etc.).
2. **Frontend:** `docPreprocessing = detail?.preprocessing ?? selected?.preprocessing`; preprocessing fields and the «Preprocessing · до очистки (raw)» panel use `docPreprocessing`. Panel is shown whenever preprocessing exists; if `preview_raw` is missing, a short hint is shown and «открыть RAW» still runs the existing full-raw fetch. `openRawLargeViewer` no longer requires `preview_raw` to exist before opening.

---

## Where retrieval vs memory-meta is decided

**Handler:** Telegram RAG branch in `interfaces/telegram_bot.py` (after `route_selected` for `rag`, history load, optional hybrid ids).

**Classifier:** `services/memory_meta_intent.py` — `detect_memory_meta_intent(query) -> MemoryMetaIntent | None` (deterministic Russian heuristics, no LLM).

**Gate (critical):**

```python
meta_intent = (
    detect_memory_meta_intent(text)
    if use_pg_memory and sid_str and uid_str
    else None
)
if meta_intent is not None and sid_str and uid_str:
    # memory_meta path: build_memory_meta_reply, NO rag_service.answer()
else:
    # RAG path: rag_service.answer(...) → always runs vector retrieval today
```

So retrieval is **skipped** only when **all** hold:

1. PostgreSQL conversation memory is enabled (`database_url`, `telegram_pg_conversation_memory`, successful `load_telegram_rag_history_for_llm` → `sid_str` and `uid_str`).
2. `detect_memory_meta_intent(text)` returns non-`None`.

Otherwise the flow always calls `rag_service.answer` → `_retrieve_raw` (retrieval runs).

---

## Why specific questions behave differently

| Question | Behavior | Reason |
|----------|----------|--------|
| **«О чем был мой предыдущий вопрос?»** | No retrieval (memory_meta) if PG memory + session ids exist | Matches `memory_meta_intent.py`: `"предыдущ" in ql and "вопрос" in ql` → `PREVIOUS_QUESTION`. |
| **«Там — это где?»** | Retrieval (normal RAG) | Short deictic follow-up; **no** substring rules in `detect_memory_meta_intent` for «там»/«это»/ellipsis resolution → `None` → full RAG. (Follow-up hint for the **LLM** exists separately in `rag_query_service` / assembly, but it does **not** skip retrieval.) |
| **«Сколько вопросов … я … задал … в процессе диалога?»** | Retrieval | No pattern for «сколько вопросов» / counting user turns in `detect_memory_meta_intent` → `None` → full RAG. |

If PG memory is **off** or session/user ids are missing, **even** meta-shaped questions go through retrieval (meta_intent is forced to `None`).

---

## Proposal (next step — not implemented)

**Goal:** Extend meta-intent coverage (or a small second stage) for clear **dialog-self** queries: turn counts, «там/это» follow-ups when `followup_question_detected` / history exists, «что ты ответил», etc., and route them to **memory-only** or lightweight LLM **without** `rag_service.answer` / `_retrieve_raw`.

**Guardrails:**

* Keep `detect_memory_meta_intent` (or successor) **deterministic** and testable; add unit tests per phrase class.
* Log explicit `intent` + `retrieval_skipped: true` in `processing_logs` for observability.
* Do not remove RAG path for ambiguous queries; optional confidence / fallback to retrieval.
* Requires product sign-off: risk of false positives skipping retrieval when the user actually wanted KB facts.

---

## Operator commands / manual checks

```bash
date +%F
cd frontend/admin-ui && npm run build
python3 -m py_compile services/admin_service.py
```

**Logs:** Open Logs → filter «документ» → row should read `doc` + status only (e.g. `УСПЕШНО`), not `doc ДОКУМЕНТ · …`.

**RAG:** Open RAG console → session with identical user vs retrieval string → grey «RAG-запрос» under user bubble; if telemetry shows a different `retrieval_ready_query` → blue expandable.

**Documents:** Open Documents → select a document with upload/preprocessing logs → «Preprocessing · до очистки (raw)» panel visible; `preview_raw` or hint + «открыть RAW»; canonical preview block unchanged (not replaced by chunks).

**API (optional):** `GET /api/documents/{id}/detail` — response should include top-level `preprocessing` when matching upload events exist in `timeline_rows`.

---

## Commit

Not performed (per request).
