# Cache Observability Console Design (PEr07)

Статус: design/spec pass (без frontend/backend реализации).  
Область: operator-facing cache observability в Admin UI Assistant Flow.

---

## 1. Цель этапа

Сформировать видимый operator-facing контур наблюдаемой оптимизации retrieval cache:
- где это живет в Admin UI;
- какой ручной workflow выполняет оператор;
- какие telemetry-поля обязательны;
- какие API/данные уже достаточны;
- какой минимальный bounded UI pass реализуется первым.

Ключевой принцип: это optimization console, а не дублирование страницы Logs.

---

## 2. Текущее состояние и ограничения

Уже доступно на backend/diagnostics уровне:
- `retrieval_cache_hit`, `retrieval_cache_miss`;
- `cache_layer`, `cache_latency_ms`;
- `retrieval_cache_generation`, `retrieval_cache_backend`;
- `retrieval_cache_key_hash_prefix`, `retrieval_cache_fingerprint_backend`;
- `evaluation_cache_bypass=true`, `evaluation_cache_policy="retrieval_cache_disabled"` для evaluation path.

Техническая база UI:
- `RagPage` уже является retrieval-centric консолью с list+detail и diagnostics timeline;
- `RetrievalSettingsPage` уже показывает runtime/cache configuration snapshot;
- `EvaluationPage` уже показывает retrieval diagnostics и quality-eval контур;
- `LogsPage` остается общей трассировкой execution-сессий.

Следствие: cache observability нужно встраивать в существующие retrieval/evaluation контуры, без создания "вторых логов".

---

## 3. Анализ вариантов размещения

### Вариант A: отдельная страница "Optimization"
- Плюс: явная навигационная сущность.
- Минус: высокий риск дублирования `RAG`/`Logs`, fragmentation operator workflow.

### Вариант B: вкладка "Кэш" внутри `RAG`
- Плюс: cache рядом с реальными RAG-сессиями и timeline.
- Минус: config/context (`generation`, флаги, TTL) все равно живут в Retrieval Settings.

### Вариант C: секция только в `Retrieval Settings`
- Плюс: близко к runtime controls.
- Минус: трудно проверять hit/miss-поведение на конкретных сессиях без session-centric view.

### Вариант D (рекомендуется): комбинированная модель
- `Retrieval Settings`: короткий `Cache Status` (режим, generation, ttl, safety hints).
- `RAG`: полный `Cache Diagnostics Mode` на уровне сессий, сравнение запросов, invalidation signals.
- `Evaluation`: явная индикация cache bypass policy.

Решение: выбрать Вариант D как минимально рискованный и максимально operator-useful.

---

## 4. Рекомендуемая UI структура (low-fidelity)

## 4.1 Retrieval Settings (короткий status-блок)
- Cache status summary:
  - retrieval cache enabled/disabled;
  - current generation;
  - retrieval cache TTL;
  - active backend.
- Invalidation hints:
  - "после reindex/generation bump ожидается miss";
  - "correctness > hit ratio".
- CTA-переход в `RAG` cache diagnostics mode.

Назначение: быстро понять текущую policy/конфигурацию, не анализируя сессии.

## 4.2 RAG page (полный cache diagnostics mode)
- **Блок 1: Cache status summary (for current window)**
  - hit/miss ratio по выбранному окну;
  - median/p95 `cache_latency_ms` (если доступно в окне);
  - текущий generation/backend footprint в выборке.
- **Блок 2: Recent RAG sessions with cache badges**
  - badge: `HIT`, `MISS`, `N/A`;
  - secondary badge: `BYPASS` (если evaluation-индикатор попал в сессию/режим).
- **Блок 3: Selected session cache telemetry**
  - `retrieval_cache_hit/miss`;
  - `cache_layer`;
  - `cache_latency_ms`;
  - `retrieval_cache_generation`;
  - `retrieval_cache_backend`;
  - `retrieval_cache_key_hash_prefix`.
- **Блок 4: Comparison panel (identical query)**
  - "предыдущий идентичный запрос" vs "текущий";
  - `hit/miss` и `retrieval_latency_ms` рядом;
  - fingerprint delta markers (generation/backend/top_k).
- **Блок 5: Invalidation / generation panel**
  - last observed generation in session;
  - detection note: generation/backend/top_k changed -> expected miss;
  - отображение `cache_invalidation_reason`, если событие есть.
- **Блок 6: Evaluation bypass explanation**
  - короткий фиксированный help-блок:
    - evaluation runs bypass retrieval cache;
    - цель: reproducibility protection.
- **Блок 7: Raw diagnostics JSON (collapsed)**
  - раскрываемый raw payload для forensic проверки.

Назначение: оператор валидирует реальные optimization-сценарии по execution-сессиям.

## 4.3 Evaluation page (минимальное дополнение)
- Явный "Cache Policy" chip в run/turn detail:
  - `evaluation_cache_bypass=true`;
  - `evaluation_cache_policy=retrieval_cache_disabled`.

Назначение: снять двусмысленность, почему evaluation и production RAG latency отличаются.

---

## 5. Operator workflow (ручной сценарий)

### A. Baseline query
1. Оператор запускает RAG-запрос.
2. В `RAG` видит `MISS`, `cache_latency_ms`, generation/backend/key-prefix.
3. Фиксирует baseline retrieval latency.

### B. Repeat query
1. Повторяет тот же запрос без изменения параметров.
2. Видит `HIT`.
3. Сравнивает latency с baseline в comparison panel.

### C. Change top_k / backend
1. Меняет `top_k` или backend (через Retrieval Settings).
2. Повторяет запрос.
3. Видит новый fingerprint + ожидаемый `MISS`.

### D. Reindex / generation bump
1. Делает reindex или bump generation.
2. Повторяет запрос.
3. Видит, что старый cache не reused; новый `MISS`; changed generation signal.

### E. Evaluation mode
1. Открывает evaluation run/turn.
2. Видит явный cache bypass policy.
3. Интерпретирует метрики как воспроизводимые, а не "ускоренные кешом".

---

## 6. API / data needs

## 6.1 Что уже можно взять сейчас (без новых endpoint)
- `GET /api/logs/recent`:
  - включает `details` с cache telemetry из `RagRequestDiagnostics`;
  - достаточно для session list, detail panel, raw JSON, частично comparison.
- `GET /api/evaluation/rag-turns/{execution_id}`:
  - `retrieval_diag`/`metadata` уже несут evaluation cache policy поля.
- `GET /api/retrieval/overview`:
  - дает cache config/status snapshot для short status блока.

Вывод: для первого bounded pass новые endpoint не обязательны.

## 6.2 Минимальные точечные расширения (по необходимости)
Без schema migration, только enrichment existing payloads:
- в `RAG` list-entry (aggregation layer фронта или API) добавить:
  - normalized "cache_state" (`hit`/`miss`/`na`);
  - optional "fingerprint_signature" (`generation|backend|top_k|key_prefix`) для comparison panel;
- в evaluation list/detail обеспечить стабильную прокладку:
  - `evaluation_cache_bypass`;
  - `evaluation_cache_policy`.

## 6.3 Что не нужно в pass-1
- отдельный cache-specific DB schema;
- отдельный cache-only API namespace;
- сложные агрегирующие endpoint под long-range analytics.

---

## 7. First implementation pass scope (UI)

Bounded scope:
1. `Retrieval Settings`: добавить компактный cache status summary + link в RAG diagnostics mode.
2. `RAG`: добавить cache diagnostics mode как расширение существующей session/detail модели:
   - cache badges в списке;
   - cache telemetry блок в detail;
   - comparison panel для identical query (локально по загруженному окну).
3. `Evaluation`: показать cache bypass policy в detail.
4. Сохранить raw diagnostics disclosure (не скрывать missing telemetry).

Out of scope:
- новая страница "Optimization";
- комплексный analytics dashboard;
- backend refactor/новые persistent агрегаты.

---

## 8. Acceptance criteria для pass-1

1. Оператор визуально отличает `cache hit` от `cache miss`.
2. Оператор видит `cache_latency_ms`.
3. Оператор видит `retrieval_generation`, `retrieval_backend`, `key_hash_prefix`.
4. Оператор видит cache bypass в evaluation sessions.
5. UI не маскирует отсутствие telemetry (явные `N/A`/gap markers).
6. Повторный одинаковый запрос проверяется end-to-end через RAG/Telegram + Admin UI.

---

## 9. Risks / warnings

- Риск перегрузить RAG page метриками и превратить ее в копию Logs.
- Неполные данные в older logs: нужны явные "telemetry gap" маркеры.
- Сравнение "identical query" ограничено окном загруженных сессий (pass-1 limitation).
- Возможны ложные выводы о speedup без контекста backend/readiness/reindex событий.

---

## 10. Report framing for PEr07

Правильная формулировка в lesson/report:

"В Assistant Flow создан контур наблюдаемой оптимизации retrieval: оператор в Admin UI видит cache hit/miss, cache latency, generation/backend fingerprint, invalidation-поведение и явный evaluation cache bypass для reproducibility."

Неправильная формулировка:

"Добавили cache.json/локальный кэш."

