# Follow-up: retrieval dedupe by `(source, text_fp)` (2026-05-13)

## Problem

After the first dedupe patch, `scripts/test_rag_duplicate_chunks_audit.py --source-substr it_ai_glossary_large` still showed **five raw hits** with **repeated `text_fp`** while `removed=0`.  

Root cause: `_retrieval_dedupe_identity` **preferred real `chunk_id` / ids first**. FAISS (and other backends) can return **different internal ids** for **duplicate vectors** with the **same normalized body**. Synthetic `chunk_id` values (`{backend}-synthetic-rank-N`) are unique per rank and also **blocked** text-based collapse.

## Fix

In `services/rag_query_service.py`:

- Replaced identity-based dedupe with:
  1. **Primary:** `srcfp:{source}:{text_fp}` where `text_fp` is `_chunk_text_fingerprint(page_content)` (normalized whitespace).
  2. **Secondary:** skip if the same **non-synthetic** real vector key appears twice (`_real_retrieval_vector_key`: `chunk_id`, `chroma_id`, `vector_id`, `uuid`, non-synthetic `id`).

Identical normalized text under the **same `source`** cannot appear twice in the list passed to relevance filter / diagnostics / LLM context. Different sources with the same text both remain (explicit product choice).

## Diagnostics

When duplicates are removed, `retrieved_duplicate_count` > 0 and `retrieval_dedupe_applied=true` (unchanged contract from prior patch).

## Audit script

`scripts/test_rag_duplicate_chunks_audit.py`:

- **Hard failures:** post-dedupe duplicate normalized text / `text_fp`, dedupe noop when raw had duplicate bodies, PG duplicate `(document_version_id, chunk_index)` or `chroma_id`, duplicate vector ids in last log row.
- **Warnings (exit 0):** identical `chunk_text_preview` rows on active versions (historical PG metadata); raw vector duplicate bodies before dedupe; legacy `rag_answer_done` rows without `retrieval_dedupe_applied` but duplicate fingerprints (uses `text_fp` from chunk dict when logged to avoid preview-truncation false positives).
- Prints **raw** and **dedup** line listings when `--source-substr` is set.

**No automatic destructive reindex** in this change; if PG still shows historical duplicate previews, treat as **metadata debt** and plan manual cleanup / reindex separately.

## Operator commands / next verification commands

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
docker exec portfolio-test-assistant-flow-1 python scripts/test_rag_duplicate_chunks_audit.py --source-substr it_ai_glossary_large
```

```bash
python3 -m py_compile services/rag_query_service.py scripts/test_rag_duplicate_chunks_audit.py
python3 scripts/test_rag_duplicate_chunks_audit.py --source-substr it_ai_glossary_large
```
