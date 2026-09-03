# 2026-09-02 — AF: RAG UI polish (долг №4)

## Задание (владелец)

> «Оставшиеся пункты долга»

Закрытие остатка контура долга AF (PORTFOLIO_CORPUS_AUDIT.md v1.18, строка
Assistant Flow): №4 RAG UI polish → №5 production build → №6 async layer →
№7 audio P5.4 remainder. Этот файл — пункт №4.

## Скоуп (из PROJECT_STATE, принятая структура)

RAG-консоль по принятой операционной структуре:

```text
HEADER → summary + status
TOP PANELS → session parameters / retrieval metrics / quality metrics
QUESTION / ANSWER
FOUND CHUNKS (primary content)
TIMELINE (collapsible)
TECHNICAL SESSION SNAPSHOT (JSON) (collapsible)
```

Обязательная функциональность чанков: preview, полный текст, score/distance,
relevance label, filename, chunk index. UX-правило: оператор всегда может
посмотреть ПОЛНЫЙ текст чанка (modal/fullscreen scrollable viewer).
Компактные сгруппированные панели (brick/tile-раскладка отклонена владельцем).

## Порядок и время (~2–3 ч)

1. Файл задачи — 5 мин.
2. Инвентаризация текущей RAG-консоли против принятой структуры — 30–45 мин.
3. Полировка по гэпам — 1–1.5 ч.
4. Сборка admin-ui, деплой, headless-проверка (DOM, без визуальных проб),
   файл задачи — 30 мин.

## Выполненные действия

1. **Инвентаризация (headless DOM, CDP)** — live-проверка `/rag` против принятой структуры:
   структура консоли соответствует принятой (5 операционных панелей → Q/A →
   Найденные чанки → Таймлайн → JSON-снимок), JS-ошибок нет, горизонтального
   overflow нет.
2. **Выявленный гэп**: модалка «Полный текст чанка» показывала только
   96-символьный preview из логов — нарушение UX-правила «оператор всегда может
   посмотреть полный текст чанка».
3. **Backend**: новый read-only endpoint
   `GET /api/retrieval/chunk-fulltext` (право `retrieval:read`; demo-роль
   проверена — 200). Полный текст берётся из активного vector store
   (weaviate / chroma / faiss) по порядку совпадений: `text_fp` (fingerprint
   текста чанка, точный) → `chunk_index` → единственный кандидат; промахи
   возвращают `reason` (`source_required`, `unknown_backend`,
   `source_not_in_index`, `chunk_not_matched`, `backend_error: …`).
4. **Frontend**: чанки в логах расширены полем `textFp` (из
   `details.retrieved_chunks[].text_fp`); модалка переработана в состояние
   loading / ok (полный текст + `matched_by` + truncation note) / miss
   (лог-preview + поясняющая note). Стили source-note в globals.css.
5. **Верификация live**:
   - fp-match на 400-чанковом `it_ai_glossary_large.txt` — `matched_by: text_fp`, PASS;
   - single-candidate на `rag_overview.txt` (448 симв.) — PASS;
   - чистый промах (`source_not_in_index`) — graceful fallback на лог-текст, PASS;
   - demo-токен — 200, PASS;
   - headless DOM после деплоя: модалка с note «Полный текст из vector store
     недоступен (source_not_in_index); показан текст из логов.» + лог-текст,
     консоль без ошибок, overflow нет.
6. **Документация**: OPERATIONS.md — раздел «Полный текст чанка» (UI-поведение,
   API-контракт, ограничение переиндексации).

Примечание: счастливый путь (fp-match) в UI верифицирован на уровне API;
визуальная приёмка UI — за владельцем (без визуальных проб).

## Изменённые файлы

- `services/rag_chroma_store.py` — `get_by_source()` (выборка чанков по source).
- `services/retrieval/chroma_backend.py` — `fetch_chunks_by_source()`.
- `services/retrieval/weaviate_backend.py` — `fetch_chunks_by_source()`
  (weaviate-client 4.15.4: `fetch_objects(filters=Filter.by_property(...))`).
- `services/admin_service.py` — `fetch_chunk_full_text()` (fp/index/single-candidate
  matching; unwrap `CachingRetrievalBackend._inner`; faiss — прямой reading `chunks.json`).
- `admin_api/routes/retrieval.py` — endpoint `GET /api/retrieval/chunk-fulltext`.
- `frontend/admin-ui/src/api/client.ts` — `fetchChunkFullText()`.
- `frontend/admin-ui/src/utils/retrievalChunks.ts` — `textFp` в чанке.
- `frontend/admin-ui/src/pages/RagPage.tsx` — маппинг `text_fp` из логов.
- `frontend/admin-ui/src/components/OperationalRetrievalChunksSection.tsx` —
  модалка полного текста (fetch + состояния + notes).
- `frontend/admin-ui/src/styles/globals.css` — `.rag-chunk-modal__source-note`.
- `docs/OPERATIONS.md` — раздел «Полный текст чанка».

## Итоговый статус

**DONE** (2026-09-02). UX-правило «полный текст чанка всегда доступен
оператору» закрыто: полный текст из активного vector store, graceful fallback
на лог-preview при недоступности. Живая инстанция обновлена и проверена.