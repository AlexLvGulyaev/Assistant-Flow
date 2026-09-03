# 🏗️ Cache Layer Design (PEr07) — Assistant Flow

Статус: architectural design / legacy audit / integration planning only.  
Область: Retrieval Optimization в рамках существующей архитектуры Assistant Flow.

---

## 1. Цель и границы этапа

Этот этап фиксирует архитектурное решение по cache layer без broad implementation.

Что делаем:
- аудит `legacy/PEr07_source` как reference;
- анализ фактических точек интеграции в текущем AF runtime;
- оценка cache layers по выгоде, рискам и сложности инвалидации;
- предложение первого bounded, безопасного implementation pass.

Что не делаем:
- Redis/distributed cache;
- асинхронные cache workers;
- schema migration и UI-реализацию;
- hot-path rewrite.

---

## 2. Legacy audit: `legacy/PEr07_source`

### 2.1 Что реализовано в legacy

В `legacy/PEr07_source` реализован учебный контур:
- `ResponseCache` в `cache.py` (JSON-файл `cache.json`);
- ключ кеша = SHA256 от нормализованного query (lower + trim spaces);
- cache check перед RAG, cache set после генерации ответа (`main.py`);
- persistence в один JSON файл на локальном диске.

Связанные файлы:
- `legacy/PEr07_source/cache.py`
- `legacy/PEr07_source/main.py`
- `legacy/PEr07_source/rag.py`
- `legacy/PEr07_source/embeddings.py`

### 2.2 Какие cache levels есть в legacy

Фактически есть только:
- final answer cache (response cache).

Отсутствуют:
- embedding cache;
- retrieval result cache;
- query rewrite/normalized retrieval cache;
- cache generation/revision strategy;
- backend-aware invalidation;
- document-version-aware invalidation;
- observability контур cache hit/miss в operational logs.

### 2.3 Что пригодно для AF (концептуально)

Можно адаптировать:
- идею deterministic key hashing;
- нормализацию query для стабильности ключа;
- простую локальную persistence-стратегию как старт (но не JSON file, а AF-native store).

### 2.4 Что непригодно/опасно для AF

Непригодно как есть:
- `cache.json` без namespace и без versioning;
- кэширование final answer без учёта conversation history, retrieval revision и runtime flags;
- отсутствие TTL/invalidation reason;
- отсутствие связки с observability и diagnostics.

Почему это риск:
- stale answers после reindex/смены backend/model;
- скрытие retrieval regressions;
- невозможность корректного forensic анализа.

---

## 3. Контекст AF и найденные integration points

Ниже точки текущего runtime, где cache связан с retrieval quality и observability.

### 3.1 Retrieval pipeline

Ключевые точки:
- query normalization и `retrieval_query` формируются в `services/rag_query_service.py`;
- vector retrieval вызывается через `_retrieve_raw` -> `_similarity_search_with_timeout` -> `RetrievalBackend.search`;
- backend выбирается через `services/retrieval/factory.py` и `services/retrieval/runtime_manager.py`;
- embeddings используются backend-реализациями (Chroma/FAISS/Weaviate) и factory path.

### 3.2 Где уже встроен cache

Уже есть foundation:
- `services/cache/caching_retrieval_backend.py` (retrieval namespace, hit/miss, TTL);
- `services/cache/retrieval_cache_key.py` (fingerprint: query, backend, top_k, embedding model, retrieval generation, hybrid flag, security fingerprint);
- `services/cache/invalidate.py` (namespace invalidation hook);
- `services/cache/answer_cache_service.py` (contract only, без интеграции в `RagQueryService` hot path).

### 3.3 Observability hooks

Уже логируется:
- `retrieval_cache_hit`, `retrieval_cache_key_hash_prefix`, `retrieval_cache_fingerprint_backend`;
- retrieval diagnostics в `RagRequestDiagnostics` и `processing_logs.details`;
- retrieval-ready query, dedupe, fallback reason, latency, token usage.

Это критично: cache можно развивать без потери operational visibility.

### 3.4 Где формируется final answer

Final answer формируется в `RagQueryService.answer()` через `_rag_llm(...)`, с явной инъекцией `history_for_llm` и (опционально) hybrid memory section.

Вывод:
- final response cache в AF сложнее, чем в legacy, потому что ответ зависит не только от query, но и от conversation context, retrieval state и runtime flags.

---

## 4. Анализ потенциальных cache layers в AF

### 4.1 Embedding cache

Выгода:
- снижение latency и стоимости повторных embed запросов;
- полезно для повторяющихся retrieval queries и indexing subflows.

Риски:
- несоответствие при смене embedding model/dimension;
- сложнее контролировать consistency между runtime и indexing.

Сложность инвалидации: средняя-высокая.  
Relevance для AF: средняя (важно, но не первый безопасный шаг).

### 4.2 Retrieval result cache

Выгода:
- прямое ускорение retrieval hot path;
- снижение нагрузки на vector backend;
- высокая наблюдаемость уже поддерживается в текущем контуре.

Риски:
- stale context при reindex/backend switch/model/top_k/threshold drift;
- потенциальная маскировка retrieval деградации без правильных сигналов.

Сложность инвалидации: средняя (управляемая через generation/revision + hooks).  
Relevance для AF: высокая (лучший кандидат для first pass).

### 4.3 Final response cache

Выгода:
- максимальная экономия токенов и генерации.

Риски:
- высокий риск stale/wrong answer из-за history/hybrid/routing differences;
- может скрыть проблемы retrieval и снизить диагностируемость;
- сильное влияние на reproducibility evaluation/RAGAS.

Сложность инвалидации: высокая.  
Relevance для AF: низкая на первом pass; допустимо только как узкий opt-in сценарий.

### 4.4 Prompt fragment cache (context assembly cache)

Выгода:
- уменьшение CPU/formatting overhead при больших одинаковых контекстах.

Риски:
- высокий риск неконсистентности при изменении history tail или memory routing.

Сложность инвалидации: высокая.  
Relevance для AF: низкая на данном этапе.

### 4.5 Retrieval diagnostics cache

Выгода:
- может ускорить UI/forensic чтение тяжелых payloads.

Риски:
- риск расхождения с source-of-truth логами.

Сложность инвалидации: средняя.  
Relevance для AF: низкая-средняя (не приоритет первого pass).

---

## 5. Invalidation model (ключевой раздел)

Основной принцип AF: correctness > hit ratio.

Кеш считается недействительным при:
- reindex (полный или затронувший retrieval corpus);
- изменении active document version;
- смене backend (Chroma/FAISS/Weaviate);
- смене embedding model;
- изменении retrieval tuning (`top_k`, thresholds);
- изменении security filtering scope;
- bump `RAG_RETRIEVAL_GENERATION`/knowledge revision.

### 5.1 Active vs archived versions

Кеш должен быть привязан к active retrieval space.  
Архивные версии не должны переиспользовать retrieval cache active версии и наоборот.

### 5.2 Generation/revision strategy

Рекомендуемая схема:
- `retrieval_generation_id` (или `knowledge_base_revision`) как обязательная часть retrieval fingerprint;
- automatic invalidation hook на индексирующих операциях;
- явный `cache_invalidation_reason` в logs.

Текущее состояние AF частично уже этому соответствует (`RAG_RETRIEVAL_GENERATION`, invalidate hooks), но требует дисциплины bump/reindex runbook.

---

## 6. Observability implications для cache layer

Минимальный обязательный operational contract:
- `cache_hit` / `cache_miss`;
- `cache_layer` (retrieval / answer / embedding);
- `cache_latency_ms`;
- `saved_tokens_estimate` (когда применимо);
- `skipped_retrieval`;
- `skipped_generation`;
- `stale_cache_detection` (детект mismatch revision/model/backend);
- `cache_invalidation_reason`.

Для AF это должно жить в том же telemetry контуре, что и retrieval diagnostics (`processing_logs.details` + консоли наблюдаемости), а не отдельным "невидимым" механизмом.

---

## 7. Evaluation / RAGAS implications

Cache может:
- искусственно завышать perceived quality;
- скрывать retrieval regressions;
- ломать воспроизводимость сравнительных run;
- искажать RAGAS метрики (особенно faithfulness/context metrics), если generation/retrieval были пропущены кешом без явной маркировки.

Обязательная архитектурная позиция:
- evaluation mode должен поддерживать bypass cache (минимум retrieval и answer layers);
- run metadata должны явно фиксировать cache policy (`cache_bypass`, `cache_mode`, `cache_layer_used`);
- сравнение run без одинаковой cache policy некорректно.

---

## 8. Proposed cache key policy

### 8.1 Retrieval cache key (обязательные компоненты)

- normalized retrieval query;
- effective backend id;
- embedding model id;
- retrieval generation/revision;
- retrieval tuning affecting result (`top_k`, threshold profile);
- security scope fingerprint;
- optional hybrid flag (если влияет на retrieval semantics в будущем).

### 8.2 Answer cache key (если когда-либо включать)

Дополнительно к retrieval key:
- normalized user query;
- history window fingerprint;
- memory routing fingerprint;
- llm model id + major prompt contract version.

Без этого answer cache unsafe.

---

## 9. Recommended minimal safe implementation pass

Рекомендованный первый bounded pass:
- retrieval cache only (opt-in, уже существующая foundation);
- scope: hardening and operationalization, не расширение в новые layers;
- answer cache оставить выключенным;
- embedding cache не включать на первом pass;
- evaluation runs по умолчанию выполнять с cache bypass.

Почему это лучший first pass:
- минимальная архитектурная сложность;
- максимальная наблюдаемость уже есть в текущем коде;
- rollback простой (feature flag off);
- риски stale answer минимизированы (нет answer cache в hot path).

### 9.1 Конкретный safe-pass checklist (без broad refactor)

1. Подтвердить и документировать invalidation triggers в runbook.  
2. Зафиксировать обязательный bump policy для `RAG_RETRIEVAL_GENERATION`.  
3. Добавить/нормализовать cache observability fields в единый contract.  
4. Явно обозначить cache policy для evaluation mode (bypass по умолчанию).  
5. Проверить smoke сценарии rollback (`ENABLE_RETRIEVAL_CACHE=false`).

---

## 10. Основные риски и предупреждения

- Stale retrieval context после reindex/version switch без generation bump.
- Иллюзия улучшения качества за счёт cache hits вместо реального retrieval quality.
- Невоспроизводимые evaluation/RAGAS сравнения при смешанном cache режиме.
- Попытка раннего включения final answer cache без history-aware ключей.
- Смещение фокуса в premature optimization вместо observable correctness.

---

## 11. Итоговые архитектурные выводы

1. Legacy PEr07 полезен только как учебный reference ключей/нормализации, но непригоден как прямой donor реализации.  
2. В AF уже есть правильная база для retrieval cache (namespace, fingerprint, invalidate hooks, diagnostics).  
3. Первым безопасным шагом должен быть только retrieval cache hardening с жёсткой invalidation discipline и evaluation bypass.  
4. Final response cache на текущем этапе архитектурно рискован и должен оставаться вне bounded pass.  
5. Cache в AF обязан быть частью observability/evaluation contract, а не "скрытым ускорителем".

---

## 12. Configuration audit — source of truth (2026-05-17)

### 12.1 Runtime ownership

| Слой | Роль | Authoritative? |
|------|------|----------------|
| **Process env → `AppConfig`** (`utils/config.py`, `load_config()`) | Включение retrieval/answer cache, TTL, `CACHE_DB_PATH` | **Да** для cache policy |
| **`RAG_RETRIEVAL_GENERATION`** | Revision fingerprint в ключе (`services/cache/retrieval_cache_key.py`, `os.getenv`) | **Да** (env, не поле AppConfig) |
| **PostgreSQL `platform_settings`** | `rag_top_k`, active backend, chunking и др. | **Да** для retrieval tuning, **не** для cache flags |
| **SQLite `SqliteCacheStore`** | Записи namespace `retrieval` | **Нет** — acceleration layer, пересоздаваем |
| **Admin UI `/api/retrieval/overview` → `cache`** | Зеркало effective env для оператора | Read-only reflection |

Cache **не** редактируется через Admin API (`editable_via_api=false` в overview). Смена env требует перезапуска процесса.

### 12.2 Parameter map (operational)

| Параметр | UI (unified panel) | Runtime | Использование |
|----------|-------------------|---------|---------------|
| `ENABLE_RETRIEVAL_CACHE` | Runtime + advanced env | `AppConfig` → `CachingRetrievalBackend` wrapper | Вкл/выкл обёртки |
| `RETRIEVAL_CACHE_TTL_SECONDS` | Effective TTL + advanced | `CachingRetrievalBackend` | TTL записей |
| `RAG_RETRIEVAL_GENERATION` | generation/revision + advanced | `retrieval_cache_key.py` | Часть fingerprint |
| `CACHE_DB_PATH` | Хранилище + advanced | `sqlite_cache.py` | Путь SQLite WAL |
| `ENABLE_ANSWER_CACHE` | Answer cache (stub) | `answer_cache_service.py` | Foundation only, не hot path |
| `ANSWER_CACHE_TTL_SECONDS` | Advanced only | answer cache service | Placeholder |
| effective backend / `top_k` | Fingerprint hints | DB settings + factory | Логический miss при смене |

Дублирование в UI (два блока «Кэш retrieval» + «Cache») устранено единым `RetrievalCacheSettingsPanel`: runtime сверху, env — в collapsible advanced.

### 12.3 Invalidation policy

1. **Явная:** `invalidate_retrieval_cache()` → `clear_namespace("retrieval")` при reindex / add / delete vectors (`CachingRetrievalBackend` hooks).
2. **Неявная (fingerprint):** смена `top_k`, backend, embedding model или bump `RAG_RETRIEVAL_GENERATION` → новый ключ → miss без удаления старых строк (устаревшие строки истекают по TTL).
3. **Evaluation:** cache bypass по умолчанию (`evaluation_service`, telemetry `BYPASS`).

Оператор после reindex: bump `RAG_RETRIEVAL_GENERATION` + при необходимости restart с тем же env.

### 12.4 SQLite vs PostgreSQL

**Verdict:** SQLite остаётся осознанным выбором для local non-authoritative retrieval cache.

- **SQLite:** быстрый локальный KV с namespace, WAL, без сетевой зависимости; потеря/очистка не ломает SoT (корпус в vector store + metadata в PostgreSQL).
- **PostgreSQL:** SoT для documents, evaluation, platform settings — не для ephemeral cache entries; перенос cache в PG не входит в bounded pass (операционная сложность, размер БД, нет выигрыша для single-node portfolio).

Redis / distributed cache — вне scope.

