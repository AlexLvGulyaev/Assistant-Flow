# Engineering log: аудит маршрутизации Chroma vs FAISS (2026-05-13)

## Наблюдение

При сравнении одинаковых запросов **distance/score** у Chroma и FAISS совпадают до 3–4 знака после запятой — выглядело как возможная подмена backend или общий кэш.

## Вывод (root cause)

**Ошибки маршрутизации (Chroma «за» FAISS) не обнаружено.** Цепочка:

1. **`build_retrieval_backend`** (`services/retrieval/factory.py`) — ветвление по `normalize_rag_backend(config.rag_backend)`; для `faiss` **обязателен** `embeddings`, для `chroma` — `chroma_store`; **нет** молчаливого fallback на Chroma.
2. **`RetrievalBackendManager._build_backend`** — подставляет `cfg = replace(base_eff, rag_backend=effective_backend_name())` и передаёт в `build_retrieval_backend`; активный backend совпадает с DB/env resolution.
3. **`RagQueryService._similarity_search_with_timeout`** — вызывает **`active.search()`** на объекте, возвращённом менеджером/статикой; `backend_label` в stdout берётся из **`active.backend_name`** (делегат у `CachingRetrievalBackend` → внутренний backend).
4. **FAISS** — `FaissBackend.search` читает **`vectors.faiss`** / `chunks.json`, score = **L2** из `IndexFlatL2` (`services/retrieval/faiss_backend.py`).
5. **Chroma** — `ChromaBackend.search` → `ChromaRagStore.native_similarity_search_with_score` → `collection.query(..., include=["distances"])`; для коллекции без явной смены метрики Chroma отдаёт **distance**, совместимую с **L2-пространством эмбеддингов** при той же модели.

**Почему числа почти одинаковые:** при **одной и той же** модели эмбеддингов, **одном и том же** тексте чанков в индексе и **L2-расстоянии** до query-вектора математика совпадает; расхождения ~1e-4 допустимы из-за float32 / различий ANN (Chroma) vs brute-force (IndexFlatL2) на ближайших соседях.

## Кэш retrieval

- Fingerprint (`services/cache/retrieval_cache_key.py`) включает **`normalize_rag_backend(config.rag_backend)`** (вторая строка fingerprint), плюс `top_k`, модель эмбеддингов, `RAG_RETRIEVAL_GENERATION`, hybrid-флаг.
- `CachingRetrievalBackend` получает **`AppConfig` уже с `rag_backend` = effective** из менеджера → **ключ кэша различается** для Chroma и FAISS; отдача Chroma-результата при активном FAISS через этот механизм **не ожидается**.

Дополнительно: RAG вызывает `search` из **worker** `ThreadPoolExecutor`; маркеры cache должны собираться **в потоке worker** — см. реализацию ниже.

## Изменения (instrumentation + тест + API slim)

### Диагностика в `RagRequestDiagnostics` / logs

В **`processing_logs.details`** и stdout (частично) добавлены поля:

- `backend_requested_env` — bootstrap из env-конфига (`normalize_rag_backend`).
- `backend_effective_resolved` — при наличии `RetrievalBackendManager`: `effective_backend_name()`.
- `backend_wrapper_class` / `backend_inner_class` — `type(...).__name__` (например `CachingRetrievalBackend` + `FaissBackend`).
- `backend_storage_label` — краткая метка (`faiss:…` или `chroma:…`).
- `faiss_index_path`, `chroma_collection_name` (для Chroma — константа коллекции RAG).
- `retrieval_cache_hit`, `retrieval_cache_key_hash_prefix`, `retrieval_cache_fingerprint_backend` — при включённом retrieval cache, из потока worker.

### Код

| Файл | Суть |
|------|------|
| `services/cache/caching_retrieval_backend.py` | Thread-local маркеры hit/miss + строка backend из fingerprint |
| `services/rag_query_service.py` | Worker возвращает `(results, cache_probe)`; `_routing_identity_for_logs`; `routing_extras` в `_build_diagnostics` |
| `services/rag_types.py` | Новые поля в dataclass, `to_log_details`, `emit_stdout` |
| `services/cache/retrieval_cache_key.py` | Комментарий про вторую строку fingerprint |
| `admin_api/deps.py` | `_PRESERVED_DETAIL_KEYS` — сохранение новых ключей при slim payload |
| `scripts/test_retrieval_backend_identity_smoke.py` | Smoke: разные классы, разные `id`, top scores и row ids |

## Команды проверки

```bash
python3 -m py_compile services/rag_query_service.py services/rag_types.py \
  services/cache/caching_retrieval_backend.py admin_api/deps.py \
  scripts/test_retrieval_backend_identity_smoke.py
```

```bash
python scripts/test_retrieval_backend_identity_smoke.py "ваш запрос"
```

(Нужны `OPENAI_API_KEY`, доступный Chroma и непустой FAISS индекс.)

## Пересборка / рестарт

| Вопрос | Ответ |
|--------|--------|
| Нужна ли пересборка? | **Да**, изменён **Python** (`assistant-flow` / `admin-api`), не фронт. |
| Команда (portfolio) | `docker compose -f docker-compose.portfolio.yml build assistant-flow admin-api && docker compose -f docker-compose.portfolio.yml up -d assistant-flow admin-api` (или только сервисы, где крутится бот + API). |
| Frontend | **Не нужен.** |
| Reindex | **Не требуется** для этого аудита. |
