# Engineering log: retrieval query observability — root cause audit

**Date:** 2026-05-14 (`date +%F`)

---

## Full prompt (verbatim)

Cursor, это уже не cosmetic/UI issue, а полноценный retrieval observability bug.

Ты ранее утверждал, что в retrieval уходит raw user query «как есть».

Это НЕ соответствует фактическому поведению системы.

Конкретный reproducible case:

USER QUERY:
«Сколько вопросов о ней я Вам задал в ходе диалога?»

Важно:
- пользователь СОЗНАТЕЛЬНО НЕ использовал слово:
  - "система"
  - "Assistant Flow"
  - "AF"
- query относится к dialog memory/meta-context.

Однако retrieval вернул:

- 3 чанка про Assistant Flow;
- chunks с "обработка запросов AF";
- chunks с "система Assistant Flow";
- chunks из AF regulations/docs.

Это означает одно из двух:

1. либо retrieval query ДОПОЛНЯЕТСЯ dialog context перед retrieval;
2. либо retrieval использует hidden rewritten query;
3. либо retrieval получает assembled context-aware query;
4. либо retrieval pipeline использует conversation expansion/rewrite;
5. либо retrieval запускается не по raw query, а по normalized/orchestrated prompt.

Текущее UI-поведение скрывает реальную retrieval query и вводит оператора в заблуждение.

Нужно провести полноценный code audit retrieval query assembly.

ЧТО НУЖНО НАЙТИ

1. Где именно формируется retrieval query:
- raw user input;
- normalized query;
- rewritten query;
- contextualized query;
- retrieval-ready query;
- expanded query;
- orchestration query.

2. Где retrieval получает FINAL STRING:
- перед embeddings;
- перед vector search;
- перед similarity_search;
- перед Weaviate query;
- перед Chroma query.

3. Что именно уходит в:
- embed_query()
- similarity_search()
- hybrid search
- vector search layer.

4. Есть ли:
- query rewrite;
- history injection;
- conversational expansion;
- pronoun resolution;
- follow-up enrichment;
- previous-turn augmentation.

5. Где именно происходит добавление контекста:
например:
«о ней» → «о системе Assistant Flow».

ЧТО НУЖНО СДЕЛАТЬ

1. Найти FINAL retrieval query.

2. Вывести его в UI.

Не "RAG-запрос" как label.

А именно:
- exact final query string,
- которая реально уходит в retrieval backend.

3. В RAG console:

панель:
«Что спросил пользователь»

должна содержать:

- raw user query;
- retrieval query (если отличается).

Например:

Пользователь:
«Сколько вопросов о ней я Вам задал в ходе диалога?»

Retrieval query:
«Сколько вопросов о системе Assistant Flow я задал в ходе диалога?»

или любой другой REAL transformed query.

4. Если retrieval query НЕ отличается:
- оставить серый label;
- не показывать раскрытие.

5. Если retrieval query отличается:
- показывать синюю expandable action;
- показывать FULL transformed retrieval query.

ОСОБО ВАЖНО

Сейчас operator observability ложная.

UI показывает:
- user query;

но НЕ показывает:
- реальную retrieval query.

Из-за этого невозможно:
- анализировать retrieval;
- понимать source relevance;
- понимать hallucinations;
- анализировать routing quality;
- анализировать conversational enrichment.

ИМЕННО ЭТО сейчас ломает диагностику retrieval.

Ещё раз:
пример с «о ней» доказывает,
что retrieval получает НЕ raw query.

Нужно найти место трансформации.

ДОПОЛНИТЕЛЬНО

После аудита:
дать инженерное заключение:

Нужно ли:
- отключать conversational query enrichment для memory/meta-dialog intent;
или
- routing должен раньше отсеивать такие запросы и вообще не запускать retrieval.

ENGINEERING LOG

Создать:

docs/cursor_sessions/YYYY-MM-DD_retrieval-query-observability-root-cause.md

Дата:
date +%F

Включить:
- полный prompt;
- root cause;
- exact pipeline path;
- где формируется retrieval query;
- чем raw query отличается от final retrieval query;
- какие файлы изменены;
- как проверить вручную;
- operator examples с before/after.

Commit НЕ выполнять.

---

## Root cause (verified in code)

### There is **no** string rewrite «о ней» → «о системе Assistant Flow» in the retrieval path

The **same** normalized user string is passed end-to-end into the embedding API and vector index:

| Stage | What happens | File / symbol |
|-------|----------------|----------------|
| User text | Telegram passes `text` into `rag_service.answer(text, …)` | `interfaces/telegram_bot.py` |
| Normalize | `normalized = (query or "").strip()` | `services/rag_query_service.py` → `answer()` |
| Retrieval string | `retrieval_query = normalized` (no history / hybrid mixed into this variable) | same |
| Vector call | `_retrieve_raw(retrieval_query, …)` → `_similarity_search_with_timeout(q, …)` with `q = query.strip()` | `services/rag_query_service.py` |
| Backend | `active.search(query, top_k=k, …)` | `RetrievalBackend.search` in `services/retrieval/base.py` |
| Chroma | `native_similarity_search_with_score(query, …)` → `embed_query(q)` with that exact `q` | `services/rag_chroma_store.py` (lines ~372–374) |
| FAISS / Weaviate | `embed_query(q)` on the same query string | `services/retrieval/faiss_backend.py`, `services/retrieval/weaviate_backend.py` |

**Conversational assembly** (`services/conversational_context_assembly.py`) builds `history_for_llm` and `followup_question_detected` for the **LLM** prompt only. It does **not** change the string used for `embed_query`.

**Hybrid retrieval** merges **retrieved KB chunks** with memory for the **LLM context** after vector search (`answer()` post-retrieval). It does **not** replace the retrieval query string.

### Why AF chunks still appear for a meta-style question

Because **vector search is not pronoun-aware**: the model embedding maps the whole utterance into a vector; if the KB is dominated by Assistant Flow documentation, **top‑k neighbors can still be AF chunks** even when the user never typed “Assistant Flow”. That is **semantic proximity + corpus skew**, not a logged second query string.

---

## Secondary observability bug (fixed): false “retrieval ≠ user” in UI

`rag_answer_done` details included **`query_preview`** (short diagnostic) but often **did not** include full **`user_input`**. `RagPage` picked `query_preview` **before** `query`, so the main bubble could show a **200‑char truncated** preview while `retrieval_ready_query` held the **full** normalized text → the expandable falsely implied a “transformed” retrieval query.

**Before:** `pickText([..., "query_preview", "query", ...])` and no `user_input` in Telegram RAG details.

**After:** Telegram adds `user_input` to RAG details; UI prefers full fields before `query_preview`.

---

## Engineering conclusion (memory / meta-dialog)

For questions that are **only** about dialog state (“сколько вопросов…”, «там — это где?»), the **correct** lever is upstream **routing / `detect_memory_meta_intent` expansion** (skip `rag_service.answer` / retrieval), **not** “fixing” a non-existent retrieval string rewrite. Retrieval string observability is now aligned with code; relevance issues for meta questions are **routing + corpus**, not hidden query text.

---

## Files changed (this session)

| File | Change |
|------|--------|
| `interfaces/telegram_bot.py` | `rag_details = {"route": "rag", "user_input": text}` before merging diagnostics |
| `frontend/admin-ui/src/pages/RagPage.tsx` | `pickText` order for session `query`: prefer `user_input` / full `query` before `query_preview` |
| `services/rag_query_service.py` | Comment at `retrieval_query` documenting no rewrite in this path |
| This log | Audit + before/after |

---

## Operator verification

1. **Code / logs:** After a RAG reply, open `rag_answer_done` JSON: `user_input` should equal the Telegram message; `retrieval_ready_query` should equal the same text after `.strip()` (unless a future rewrite is added at `retrieval_query`).

2. **RAG console:** For a normal-length question, main bubble text should match Telegram; expandable **“RAG-запрос”** appears **only** when `retrieval_ready_query` differs from displayed text (true rewrites or intentional divergence).

3. **Build:** `cd frontend/admin-ui && npm run build`  
4. **Python:** `python3 -m py_compile interfaces/telegram_bot.py services/rag_query_service.py`

---

## Commit

Not performed (per request).
