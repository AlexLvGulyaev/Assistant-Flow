# Full original task prompt

```text
# RAGAS negative-answer inconsistency diagnostic prompt

Используй Codex 5.3.

Проведи targeted diagnostic investigation по двум negative-answer кейсам RAGAS.

Контекст:
В Evaluation / RAGAS run `ui-10-turns` есть два кейса с одинаковым или практически одинаковым набором retrieved chunks, но диаметрально разными RAGAS scores.

Кейс 9:
Question:
`Какой биржевой тикер у компании «НоваТех» на NASDAQ?`

Generated answer:
`В базе знаний нет информации о биржевом тикере компании «НоваТех» на NASDAQ.`

Ground truth:
`В базе знаний отсутствует информация о биржевом тикере компании "НоваТех" на NASDAQ`

Observed metrics:
- faithfulness = 0.000
- answer_relevancy = 0.000
- context_precision = 0.000

Кейс 10:
Question:
`Какова рыночная капитализация ООО «НоваТех»?`

Generated answer:
`В базе знаний нет информации о рыночной капитализации ООО «НоваТех».`

Ground truth:
`В базе знаний отсутствует информация о рыночной капитализации ООО "НоваТех"`

Observed metrics:
- faithfulness = 1.000
- answer_relevancy = 0.000
- context_precision = 1.000

Наблюдение оператора:
retrieval в обоих кейсах визуально возвращает один и тот же или очень похожий набор нерелевантных/общекорпоративных chunks. При этом RAGAS в одном случае трактует отсутствие информации как unsupported claim, а в другом — как fully grounded absence.

Цель:
найти точную причину расхождения RAGAS scores между кейсами 9 и 10.

Проверить:
1. exact execution_id, item_id, ordinal для обоих кейсов;
2. точный набор retrieved_chunks для обоих items;
3. порядок chunks, source, distance, text/full_text;
4. raw persisted RAGAS metric_value_json для всех трех метрик по обоим items;
5. какие поля реально передаются в RAGAS adapter для каждого кейса:
   - question
   - answer
   - contexts
   - ground_truth/reference
6. есть ли различия в formatting / escaping / quotes / punctuation / null handling;
7. есть ли различия в no-answer wording между answer и GT;
8. зависит ли context_precision от порядка chunks в этих кейсах;
9. не происходит ли metric overwrite / stale metric reuse;
10. можно ли объяснить расхождение логикой RAGAS или это LLM-as-judge instability.

Отдельно ответить:
Если retrieved chunks явно помечены системой как нерелевантные или не прошедшие фильтр, попадают ли они вообще в RAGAS contexts? Проверить код path `contexts_from_retrieval_diag()` и фактические rows.

Constraints:
- diagnostics only;
- no code changes;
- no refactor;
- no schema changes;
- use SQL/logs/code reading only.

Session logging:
создай:
`docs/cursor_sessions/2026-05-15_ragas_negative_absence_inconsistency_diagnostic.md`

В начало session log полностью помести этот prompt.

В конец добавить:
1. investigated item ids / execution ids;
2. SQL queries;
3. side-by-side chunks comparison;
4. side-by-side RAGAS input rows;
5. metric_value_json analysis;
6. exact explanation or strongest evidence;
7. conclusion: expected RAGAS behavior vs evaluator instability vs implementation bug;
8. git status.

Commit НЕ выполнять.

В ответе предоставить только:
1. exact cause or strongest evidence;
2. whether this is RAGAS behavior or AF implementation issue;
3. whether chunk order explains CP difference;
4. whether code change is needed;
5. git status.
```

## Investigated item ids / execution ids

Run: `7fb2fea5-e3cc-448e-a502-2dadd203482d` (`ui-10-turns`)

- Case 10 (market cap):
  - `ordinal=1`
  - `item_id=46a10888-c83a-41ad-8cc5-e38c90886ca2`
  - `execution_id=b0f7e833-6899-414d-a851-32a04dfafc3e`
- Case 9 (NASDAQ ticker):
  - `ordinal=2`
  - `item_id=e112b84e-5c01-4cf8-ad78-95136f971f12`
  - `execution_id=a38f3b9a-6410-4d79-bafb-d4203fe14873`

## SQL queries

1. IDs + Q/A/GT mapping (ordinals 1,2).
2. Side-by-side retrieved chunks (source/score/text_fp/order).
3. Raw persisted metrics with `metric_value_json`.
4. Reconstructed RAGAS input rows (question/answer/ground_truth/contexts).
5. Chunk order/set hash comparison.
6. Metrics timestamp check (stale reuse / overwrite suspicion).
7. `passed_filter` flags check for all chunks.

## Side-by-side chunks comparison

For ordinals 1 and 2:

- Same 5 chunks
- Same order
- Same sources
- Same `text_fp` sequence
- Very close scores

Proof:

- `chunk_fp_order_hash` identical for both: `c71c4d3cc09764639851dcd0f0dfe730`
- `chunk_fp_set_hash` identical for both: `07032d3eb948e1da5c0c6234c972ff82`

Also:

- `passed_filter=true` for all 10 chunk rows (both items)
- Therefore all 5 chunks are eligible for `contexts_from_retrieval_diag()`.

## Side-by-side RAGAS input rows (as actually built)

From code path `services/evaluation_ragas_service.py`:

- `question = evaluation_item.query_text`
- `answer = evaluation_item.answer_text`
- `ground_truth = evaluation_dataset_item.metadata["ground_truth"]`
- `contexts = contexts_from_retrieval_diag(retrieval_diag)` where:
  - `passed_filter=False` chunks are excluded
  - chunk body uses `chunk_text_full` fallback `text_preview`
  - dedupe by body text

For both cases:

- `contexts_count=5`
- contexts list content is effectively the same (same text_fps/order hash).

Differences are only:

1. question text
2. answer text
3. ground_truth text

## metric_value_json analysis

Raw persisted rows:

- case 10 (ordinal 1):
  - `faithfulness=1`
  - `context_precision=1`
  - `answer_relevancy=0`
- case 9 (ordinal 2):
  - `faithfulness=0`
  - `context_precision=0`
  - `answer_relevancy=0`

`metric_value_json` in all rows:

- same shape
- `errors=null`
- `question_type="interactive_trace"`
- `contexts_count=5`

No per-item adapter-side anomaly in JSON payload.

## Exact explanation / strongest evidence

Strongest evidence:

1. AF sends near-identical contexts for both items (confirmed by set/order hashes).
2. AF sends no hidden per-item special flags; adapter payload structure is uniform.
3. No stale metric reuse:
   - all 6 metric rows for ordinals 1/2 share same fresh timestamp (`2026-05-16 10:51:09.547829+00`), produced in one rerun.
4. Yet evaluator outputs opposite `faithfulness/context_precision` judgments for two semantically similar negative-absence answers.

Interpretation:

- Divergence is produced inside RAGAS evaluation itself (LLM-as-judge behavior on phrasing/question semantics), not by AF payload assembly bug.

## Additional required check: do non-relevant / failed chunks enter contexts?

- Code: `contexts_from_retrieval_diag()` explicitly skips chunk when `passed_filter is False`.
- Fact for these two cases: all chunks have `passed_filter=true`, so all 5 enter contexts.
- Therefore “marked failed/non-passing chunks” are not the reason here.

## Conclusion

- **Expected AF implementation behavior**: confirmed (payload construction consistent).
- **Chunk order explains CP difference**: no (order identical).
- **Most likely source of inconsistency**: RAGAS evaluator / LLM-as-judge instability and sensitivity to question/answer/GT wording under similar context.
- **Implementation bug in AF**: no hard evidence found in this investigation.

## Git status

```bash
?? docs/cursor_sessions/2026-05-15_rag_memory_leakage_diagnostic.md
?? docs/cursor_sessions/2026-05-15_ragas_negative_absence_inconsistency_diagnostic.md
```
