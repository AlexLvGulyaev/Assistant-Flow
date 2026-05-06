# Demo scenarios — Assistant Flow

Use these checks before a demo or portfolio review. Run commands from the **repository root** with `.env` configured (see `.env.example`).

## Prerequisites

- `pip install -r requirements.txt`
- `.env` with at least: `TELEGRAM_BOT_TOKEN`, `GIGACHAT_AUTH_KEY` (and related GigaChat vars), keys for OpenAI or Proxy (RAG + images + embeddings as needed)
- For RAG + admin indexing with DB metadata: PostgreSQL with `database/schema.sql` applied, `DATABASE_URL` set

---

## 1. Text mode (GigaChat + usual Q&A)

1. Start the bot: `python run_telegram_bot.py`
2. In Telegram: `/reset` then `/mode text` (or stay default after `/start`)
3. Send a short factual question, e.g. *«Объясни простыми словами, что такое инфляция»*
4. **Expect:** Long answer in Russian, formatted for Telegram (no RAG sources block)

---

## 2. RAG mode (read-only over Chroma)

1. Ensure the knowledge base is indexed (see scenario 4) or use `scripts/rag_smoke_test.py --reindex` once
2. Start the bot if not running
3. `/mode rag`
4. Ask something covered by your documents, e.g. *«Что такое RAG в этом проекте?»* (if `sample_career_rag.txt` or similar is indexed)
5. **Expect:** Answer plus an **«Источники:»** section with file names and scores; if nothing retrieved, a note about fallback

---

## 3. `/stats`

1. With the bot running, send `/stats`
2. **Expect:** Chunk count in Chroma, absolute paths to Chroma dir and `RAG_DOCUMENTS_DIR`, hint to indexing docs

---

## 4. Admin indexing CLI

1. Place or keep `.pdf` / `.txt` / `.md` under `data/documents/` (or `RAG_DOCUMENTS_DIR`)
2. Run: `python scripts/admin_index_documents.py --reindex`
   - Add `--no-postgres` if you only want Chroma without DB writes
3. **Expect:** Console summary — files found, chunks created, total chunks in Chroma; exit code `0` on full success, `3` if any file failed
4. Optional: verify PostgreSQL rows for `documents` / `document_versions` / `indexing_jobs` if `DATABASE_URL` was set

---

## 5. Image generation (text mode)

1. `/mode text`
2. Send a prompt with image intent, e.g. *«Нарисуй закат над морем в минималистичном стиле»*
3. **Expect:** Status message, then a photo; on failure, an error message from the bot

---

## 6. `/reset`

1. After using RAG, send `/reset`
2. **Expect:** Confirmation; mode back to `text`; in-memory RAG history cleared (until next `/mode rag`)

---

## Quick local RAG smoke (without Telegram)

```bash
python scripts/rag_smoke_test.py --reindex --question "Ваш вопрос по документам"
```

See also: `docs/RAG_SMOKE_TEST.md`, `docs/ADMIN_INDEXING.md`, `docs/ARCHITECTURE.md`.
