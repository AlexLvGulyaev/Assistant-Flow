# Промпт для Cursor: Cache Layer / PEr07 — architectural design & legacy audit pass

Используй Codex 5.3.

Прочитай и выполни. Общаемся, комментарии и отчёты пишем строго на русском языке.

Начинаем новый subsystem-scoped sprint:
PEr07 / Cache Layer / Retrieval Optimization для Assistant Flow.

ВАЖНО:
это НЕ учебная standalone-демка с `cache.json`.
Нельзя просто переносить код из урока.
Работаем только через архитектуру Assistant Flow.

==================================================
КОНТЕКСТ
==================================================

Assistant Flow уже содержит:

- multimodal assistant runtime;
- RAG pipeline;
- retrieval diagnostics;
- retrieval observability;
- Evaluation Layer;
- RAGAS integration;
- forensic evaluation console;
- operational logging;
- Admin UI;
- retrieval backend abstraction;
- PostgreSQL persistence;
- AssetRepository;
- runtime degraded mode;
- lifecycle logging.

Недавний sprint был посвящен:
- RAGAS;
- retrieval diagnostics;
- forensic evaluation;
- operational observability;
- retrieval-quality investigation.

Теперь начинается следующий subsystem sprint:
Cache Layer / Retrieval Optimization.

==================================================
ВАЖНО
==================================================

НЕ реализовывать сейчас полноценный production cache subsystem.

Сначала нужен:
architectural design + legacy audit + integration planning.

Никакой broad implementation на этом этапе.

==================================================
ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ ПЕРЕД РАБОТОЙ
==================================================

1. PROJECT_STATE.md

2. Документы из:
`docs/architecture/`

Особенно:
- evaluation layer architecture/design;
- operational workflow;
- operational discipline;
- cursor workflow regulation;
- subsystem sprint model;
- bounded execution principles.

3. Документы из:
`docs/cursor_sessions/`

Особенно:
- последние evaluation/RAGAS sessions;
- retrieval investigations;
- forensic findings;
- operational UI findings.

4. Legacy lesson source:
`legacy/PEr07_source`

ВАЖНО:
legacy — это reference material для анализа,
а НЕ код для прямого копирования.

==================================================
ЦЕЛЬ ЭТАПА
==================================================

Подготовить архитектурное понимание того:

1. как cache layer должен выглядеть внутри AF;
2. какие уровни кэширования реально полезны;
3. какие уровни опасны;
4. как cache связан с retrieval quality;
5. как cache связан с observability;
6. как избежать stale-context и stale-answer проблем;
7. как cache должен инвалидироваться;
8. как cache связан с document versioning;
9. как cache связан с Evaluation/RAGAS;
10. какой minimal safe implementation pass делать первым.

==================================================
ЧТО НУЖНО СДЕЛАТЬ
==================================================

1. Провести audit legacy/PEr07_source
--------------------------------------------------

Определить:
- что реализовано;
- какие cache levels используются;
- какие решения пригодны;
- какие решения непригодны для AF;
- какие решения слишком toy/demo-oriented;
- что можно адаптировать концептуально.

Особенно обратить внимание:
- query cache;
- embedding cache;
- retrieval cache;
- final answer cache;
- invalidation model;
- cache persistence;
- cache keys.

==================================================

2. Проанализировать текущий AF runtime
--------------------------------------------------

Найти:
- где сейчас проходит retrieval pipeline;
- где формируется retrieval query;
- где вызываются embeddings;
- где вызывается retrieval backend;
- где формируется final answer;
- где уже есть observability hooks;
- где логируются retrieval diagnostics;
- где можно безопасно встраивать cache.

==================================================

3. Подготовить architectural analysis
--------------------------------------------------

Нужно описать:

Какие cache layers потенциально существуют в AF:

Например:
- embedding cache;
- retrieval result cache;
- final response cache;
- prompt fragment cache;
- retrieval diagnostics cache.

Для каждого:
- потенциальная выгода;
- риски;
- invalidation complexity;
- relevance для AF.

==================================================

4. Отдельно про invalidation
--------------------------------------------------

Нужно отдельно проанализировать:

- reindex;
- document version changes;
- active vs archived versions;
- backend switching (FAISS/Chroma/Weaviate);
- embedding model changes;
- top_k changes;
- retrieval threshold changes.

Главный вопрос:
когда cache становится недействительным.

==================================================

5. Отдельно про observability
--------------------------------------------------

Нужно продумать:

Какие operational signals нужны:

- cache_hit;
- cache_miss;
- cache_layer;
- cache_latency_ms;
- saved_tokens_estimate;
- skipped_retrieval;
- skipped_generation;
- stale_cache_detection;
- cache_invalidation_reason.

НЕ реализовывать пока fully.
Только architectural analysis.

==================================================

6. Evaluation / RAGAS implications
--------------------------------------------------

Проанализировать:

Как cache может:
- исказить evaluation;
- скрыть retrieval issues;
- ломать reproducibility;
- влиять на RAGAS metrics.

Нужно явно описать:
что evaluation mode, вероятно, должен уметь bypass cache.

==================================================

7. Minimal safe implementation proposal
--------------------------------------------------

Предложить:
какой первый bounded implementation pass наиболее безопасен.

Например:
- только retrieval cache;
- только response cache;
- только opt-in query cache;
- только operational hello/FAQ cache;
- только in-memory cache;
- или другой вариант.

Нужно:
- minimal complexity;
- minimal architectural risk;
- maximum observability;
- easy rollback.

==================================================
НЕ ДЕЛАТЬ
==================================================

НЕ делать:
- Redis integration;
- distributed cache;
- Kubernetes scaling;
- async cache workers;
- broad refactor;
- hot-path rewrite;
- premature optimization;
- UI implementation;
- schema migration без необходимости;
- production HA architecture.

НЕ копировать учебный код напрямую.

==================================================
DELIVERABLES
==================================================

Создать:

1.
`docs/architecture/cache_layer_design.md`

2.
session log:
`docs/cursor_sessions/YYYY-MM-DD_cache_layer_architecture_design.md`

Дата:
`date +%F`

В начало session log полностью поместить этот prompt.

В конце session log добавить:
1. analyzed files;
2. legacy findings;
3. AF integration points;
4. proposed cache layers;
5. invalidation findings;
6. observability implications;
7. minimal safe implementation proposal;
8. risks/warnings;
9. git status.

==================================================
ОТВЕТ
==================================================

В ответе предоставить только:
1. changed files;
2. key architectural conclusions;
3. recommended first implementation pass;
4. major risks;
5. git status.

Commit НЕ выполнять.

---

## analyzed files

- `PROJECT_STATE.md` (разделы P6, legacy инвентаризация, cache invalidation strategy, observability contract)
- `docs/architecture/evaluation_layer_design.md`
- `docs/architecture/operational_discipline_assistant_flow_ru.md`
- `docs/architecture/cursor_operational_workflow_regulation.md`
- `docs/cursor_sessions/2026-05-16_project_state_rag_quality_analysis_update.md`
- `docs/cursor_sessions/2026-05-15_rag_memory_leakage_diagnostic.md`
- `docs/cursor_sessions/2026-05-14_retrieval-query-observability-root-cause.md`
- `docs/cursor_sessions/2026-05-15_evaluation_ragas_operational_verification.md`
- `docs/cursor_sessions/2026-05-14_evaluation-layer-architecture-design.md`
- `legacy/PEr07_source/cache.py`
- `legacy/PEr07_source/main.py`
- `legacy/PEr07_source/rag.py`
- `legacy/PEr07_source/embeddings.py`
- `legacy/PEr07_source/README.md`
- `services/rag_query_service.py`
- `services/rag_types.py`
- `services/retrieval/factory.py`
- `services/retrieval/runtime_manager.py`
- `services/cache/base.py`
- `services/cache/retrieval_cache_key.py`
- `services/cache/caching_retrieval_backend.py`
- `services/cache/answer_cache_service.py`
- `services/cache/invalidate.py`
- `services/admin_service.py`
- `services/evaluation_service.py`
- `services/evaluation_ragas_service.py`
- `interfaces/telegram_bot.py`
- `.env.example`
- `utils/config.py`
- `scripts/test_cache_foundation_smoke.py`
- `scripts/test_retrieval_cache_smoke.py`

## legacy findings

- В `legacy/PEr07_source` фактически реализован только final response cache (`cache.json` + hash(normalized query)).
- Нет namespace-изоляции, TTL, generation/revision, backend/model-aware ключей.
- Нет invalidation hook на reindex/version/model/backend changes.
- Нет operational observability контракта cache hit/miss в pipeline логах.
- Концептуально полезны только deterministic hashing и query normalization; реализация напрямую для AF непригодна.

## AF integration points

- Retrieval query формируется в `RagQueryService.answer()` (`retrieval_query = normalized`), затем идёт в `RetrievalBackend.search`.
- Векторный backend выбирается через factory/runtime manager (`chroma`/`faiss`/`weaviate`).
- Есть обёртка `CachingRetrievalBackend` с namespace `retrieval`, TTL, hit/miss logging.
- Есть invalidate hooks при reset/add/delete в retrieval backend wrapper.
- `RagRequestDiagnostics` и `processing_logs.details` уже содержат retrieval cache telemetry поля.
- `AnswerCacheService` присутствует как foundation, но не включён в `RagQueryService` hot path.

## proposed cache layers

1. Embedding cache  
   - Выгода: cost/latency reduction для repeat embeddings.  
   - Риск: model/dimension drift.  
   - Invalidation complexity: средняя-высокая.

2. Retrieval result cache  
   - Выгода: ускорение retrieval, снижение backend pressure.  
   - Риск: stale context при смене retrieval state.  
   - Invalidation complexity: средняя.

3. Final response cache  
   - Выгода: максимальная экономия токенов.  
   - Риск: stale answer, скрытие retrieval regressions, evaluation distortion.  
   - Invalidation complexity: высокая.

4. Prompt fragment cache  
   - Выгода: уменьшение assembly overhead.  
   - Риск: рассинхронизация с history/memory routing.  
   - Invalidation complexity: высокая.

5. Retrieval diagnostics cache  
   - Выгода: ускорение forensic read-path.  
   - Риск: divergence от source-of-truth логов.  
   - Invalidation complexity: средняя.

## invalidation findings

Критические invalidation-триггеры:
- reindex (full/partial retrieval corpus changes);
- document version changes (active/inactive transitions);
- backend switch (FAISS/Chroma/Weaviate);
- embedding model change;
- `top_k` change;
- retrieval threshold policy change;
- security scope filter change;
- `RAG_RETRIEVAL_GENERATION` / knowledge revision bump.

Главный вывод:
- cache correctness важнее hit ratio;
- stale retrieval cache — критичный operational риск;
- generation/revision должен быть обязательной частью retrieval cache fingerprint.

## observability implications

Минимальный сигнал-контракт для cache layer:
- `cache_hit`
- `cache_miss`
- `cache_layer`
- `cache_latency_ms`
- `saved_tokens_estimate`
- `skipped_retrieval`
- `skipped_generation`
- `stale_cache_detection`
- `cache_invalidation_reason`

Наблюдаемость кеша должна быть частью existing retrieval diagnostics/processing logs, а не отдельным непрозрачным контуром.

## minimal safe implementation proposal

Рекомендованный первый bounded pass:
- только retrieval cache (opt-in, без включения answer cache в hot path);
- hardening существующего контракта (invalidation discipline + observability normalization);
- evaluation mode по умолчанию с bypass cache для воспроизводимости;
- лёгкий rollback через feature flags (`ENABLE_RETRIEVAL_CACHE=false`).

Почему это безопасно:
- минимальная сложность;
- минимальный архитектурный риск;
- максимальная observability;
- отсутствует самый рискованный слой (final response cache).

## risks/warnings

- stale context после reindex/version/backend/model changes без корректной invalidation policy;
- ложная стабильность quality за счёт cache hit вместо реального retrieval improvements;
- невоспроизводимость evaluation/RAGAS при смешанном cache policy;
- premature включение response cache без history-aware ключа;
- смещение усилий в optimization до закрытия correctness/observability gaps.

## git status

```text
 M PROJECT_STATE.md
?? docs/architecture/cache_layer_design.md
?? docs/architecture/operational_discipline_assistant_flow_ru.md
?? docs/cursor_sessions/2026-05-16_project_state_rag_quality_analysis_update.md
?? docs/cursor_sessions/2026-05-17_cache_layer_architecture_design.md
```

