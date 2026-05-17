# Full original task prompt

```text
# RAG memory leakage diagnostic prompt

Используй Codex 5.3.

Проведи targeted diagnostic investigation.

Контекст:
Во время анализа Evaluation / RAGAS обнаружен следующий кейс.

Вопрос:
`За сколько дней до окончания лицензии разрешено её продлевать?`

Generated answer:
`Лицензия может быть продлена не позднее чем за 30 дней до окончания её срока действия.`

Ground truth:
тот же самый корректный ответ.

Но:
- faithfulness = 0.000
- context_precision = 0.000

Текущий retrieval для этого item НЕ содержит прямого чанка с ответом.

Однако:
в другом evaluation item этого же run ранее использовался retrieval chunk:
`ragas_facts_baseline.txt #3`

который содержит строку:
`Продление лицензии возможно не позднее чем за 30 календарных дней до окончания срока.`

Гипотеза:
LLM взяла правильный ответ:
- либо из conversational memory/history;
- либо из ранее увиденного retrieval context внутри session/run;
- а не из current retrieval.

Цель:
точно установить, какая информация реально доступна LLM во время answer generation для этого кейса.

Необходимо:
1. проследить полный prompt assembly path;
2. определить, что именно попадает в LLM context window;
3. проверить:
   - retrieval chunks текущего запроса;
   - session memory/history;
   - previous retrieved chunks;
   - orchestrator memory injection;
   - conversational context reuse;
4. определить, мог ли ответ быть получен:
   - из предыдущего retrieval;
   - из memory subsystem;
   - из chat history;
   - или это genuine hallucination;
5. показать exact evidence.

Использовать:
- SQL;
- logs;
- processing_logs;
- intake_events;
- request payload tracing;
- orchestrator code path;
- prompt assembly tracing.

Constraints:
- diagnostics only;
- no code changes;
- no refactor;
- no cleanup.

Session logging:
создай:
`docs/cursor_sessions/2026-05-15_rag_memory_leakage_diagnostic.md`

В начало session log полностью помести этот prompt.

В конец добавить:
1. investigated execution_ids;
2. SQL queries;
3. relevant prompt fragments;
4. exact context sources visible to LLM;
5. root cause analysis;
6. conclusion: leakage vs memory vs hallucination;
7. git status.

Commit НЕ выполнять.

В ответе предоставить только:
1. exact information sources available to LLM;
2. whether previous retrieval context leaked into generation;
3. evidence;
4. conclusion.
```

## Investigated execution_ids

- target: `2d6a904a-2c91-482b-b5bc-3819eac29f86`
- same-session neighbors used for sequence tracing:
  - `d321d7f1-2690-4112-ba04-4f56fb74fd30`
  - `47ddc421-ed54-48ca-a644-a0cdb1529a7b`
  - `1210efe0-6fbb-4d04-b34c-b5a4c22f6809`
  - plus older messages in active session `4ce8f76a-12fa-4f04-98ca-21629c14b898`

## SQL queries

1. Run items + execution ids:
```sql
SELECT ei.ordinal, ei.id AS item_id, edi.metadata->>'execution_id' AS execution_id,
       ei.query_text, ei.answer_text, ei.retrieval_diag->>'fallback_reason' AS fallback_reason
FROM evaluation_item ei
JOIN evaluation_dataset_item edi ON edi.id = ei.dataset_item_id
WHERE ei.run_id='7fb2fea5-e3cc-448e-a502-2dadd203482d'
ORDER BY ei.ordinal;
```

2. Metrics for target item:
```sql
SELECT metric_key, metric_value_numeric, metric_value_json
FROM evaluation_metric_fact
WHERE run_id='7fb2fea5-e3cc-448e-a502-2dadd203482d'
  AND item_id='5fbb17d6-0a3f-4b7d-969c-f2c1af6cf63c'
ORDER BY metric_key;
```

3. Retrieved chunks for target item:
```sql
SELECT jsonb_pretty(ei.retrieval_diag->'retrieved_chunks') AS retrieved_chunks
FROM evaluation_item ei
WHERE ei.id='5fbb17d6-0a3f-4b7d-969c-f2c1af6cf63c';
```

4. Which items contain `ragas_facts_baseline.txt` chunks:
```sql
SELECT ei.ordinal, edi.metadata->>'execution_id' AS execution_id,
       jsonb_path_query_array(ei.retrieval_diag, '$.retrieved_chunks[*] ? (@.source == "ragas_facts_baseline.txt")') AS baseline_chunks
FROM evaluation_item ei
JOIN evaluation_dataset_item edi ON edi.id = ei.dataset_item_id
WHERE ei.run_id='7fb2fea5-e3cc-448e-a502-2dadd203482d'
ORDER BY ei.ordinal;
```

5. processing_logs pipeline for target execution:
```sql
SELECT stage, status, created_at,
       details->>'query_preview' AS query_preview,
       details->>'history_messages_loaded' AS history_messages_loaded,
       details->>'history_messages_used' AS history_messages_used,
       details->>'history_turns_used' AS history_turns_used,
       details->>'followup_question_detected' AS followup_question_detected,
       details->>'retrieval_ready_query' AS retrieval_ready_query
FROM processing_logs
WHERE execution_id='2d6a904a-2c91-482b-b5bc-3819eac29f86'
ORDER BY created_at;
```

6. Active session history before target turn:
```sql
SELECT c.execution_id, c.role, LEFT(c.content, 180) AS content_preview
FROM chat_messages c
WHERE c.session_id='4ce8f76a-12fa-4f04-98ca-21629c14b898'
  AND c.created_at < (SELECT MIN(created_at) FROM chat_messages WHERE execution_id='2d6a904a-2c91-482b-b5bc-3819eac29f86')
ORDER BY c.created_at DESC
LIMIT 12;
```

## Relevant prompt fragments (codepath)

### `services/rag_query_service.py`

- Retrieval query is literal current user text:
  - `retrieval_query = normalized`
  - comment: no conversational rewrite for retrieval query.

- Conversation history is explicitly loaded into LLM input:
  - `assembly = self._assemble_rag_conversation(normalized, conversation_history)`
  - in `_rag_llm(...)`: `messages.extend(history_for_llm)`.

- In non-hybrid path (`enable_hybrid_retrieval=false`), `context` passed to system prompt is KB-only:
  - `kb_formatted = _format_context(filtered)`
  - `context = kb_formatted`

### `interfaces/telegram_bot.py`

- RAG mode loads persistent PG history for current session:
  - `load_telegram_rag_history_for_llm(...)`
  - passes history into `rag_service.answer(..., conversation_history=history, ...)`.

### `services/conversational_context_assembly.py`

- Applies tail selection and char budgets; returns `history_for_llm`.
- So history injection into LLM is intended behavior, bounded by configured caps.

## Exact context sources visible to LLM for target case

For execution `2d6a904a-2c91-482b-b5bc-3819eac29f86`:

1. **Current retrieval chunks** (5 chunks, all from current query diagnostics).
   - Includes `ragas_facts_baseline.txt` fragment `dc0d8634...` (history/infrastructure section).
   - Does **not** include the direct license sentence chunk (`a8e791e9...` with “Продление лицензии ... 30 дней”).

2. **Session chat history tail** from active session `4ce8f76a-...`.
   - `processing_logs.details.history_messages_used = 12`
   - includes prior user/assistant turns from earlier execution_ids in same session.

3. **User current message**.

4. **No hybrid memory block** in this case (no evidence of memory section in context; non-hybrid KB formatting path used).

## Root cause analysis

Observed behavior is explained by **intentional chat-history injection into LLM prompt**:

- Retrieval for the target turn did not carry explicit license fact sentence.
- But LLM received 12 prior messages from same session (`history_messages_used=12`) in addition to KB context.
- Therefore the answer could be reconstructed from prior conversational context and/or model prior knowledge, independent of current retrieval evidence.

RAGAS then correctly penalized:

- `faithfulness=0` and `context_precision=0`
- because answer is not supported by current retrieved evidence for that turn.

## Conclusion: leakage vs memory vs hallucination

- **Previous retrieval context leaked directly between requests**: no evidence of backend-level retrieval leakage.
- **Conversational context reuse (chat history in prompt)**: **yes, confirmed**.
- **Memory subsystem influence**: yes, via explicit `conversation_history` injection path (session tail).
- **Genuine hallucination**: not required to explain outcome; strongest explanation is history-conditioned generation not grounded in current retrieval.

## Git status

```bash
git status --short
# output: clean working tree (no changes reported)
```
