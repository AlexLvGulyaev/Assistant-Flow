# Evaluation Run UI — forensic layout analysis

**Date:** 2026-05-15

**Scope:** architectural/UI analysis only. No implementation, refactor, backend, or schema changes were performed.

---

## Task Envelope

Analyze the current Evaluation Run layout in the Evaluation / RAGAS operational console. The requested focus is run-level vs item-level hierarchy, cognitive flow, operational density, forensic analysis workflow, scalability, retrieval chunk placement, ground_truth workflow, and the relationship between question, generated answer, ground truth, metrics, and retrieval context.

The task explicitly asks not to start coding and to produce only an analysis document.

---

## 1. Current Layout Problems

The current Evaluation Run detail view is structurally run-centric, but most of the operator's real work is item-centric. The screen starts with an appropriate run header and compact run/RAGAS summary panels, then shifts into a `Per-item metrics` table and a separate stack of ground_truth/manual_score editors.

This creates several problems:

- The table compresses each evaluation item into a row where the question and metrics are visible, but the generated answer is absent.
- Ground truth is represented as a yes/not-provided state in the table, then edited elsewhere in a separate vertical editor stack.
- Retrieval context is not part of the run-detail item analysis path, even though evaluation quality depends on the answer-context-ground_truth relationship.
- Multiple item editors compete for vertical space even when the operator usually needs to inspect one case at a time.
- Metrics are visible as a batch summary, but their forensic explanation is weak because the evidence that produced them is not adjacent.

The result is not a backend or data-model problem. The item payload already contains the primitives needed for analysis: question, answer, ground_truth, metrics, retrieval diagnostics, retrieved chunks, status, and execution_id. The issue is that the current layout does not make one evaluation item the primary analytical object.

---

## 2. Cognitive Flow Analysis

The current flow asks the operator to switch mental contexts repeatedly:

1. Identify a run.
2. Read run-level summary.
3. Scan a metrics table.
4. Notice an item with weak or missing metrics.
5. Move down to a separate ground_truth editor.
6. Infer the generated answer and retrieval evidence from elsewhere or not see them at all.

This breaks the natural evaluation question:

> For this one question, did the retrieved context support the generated answer, and does that answer match the ground truth?

The table layout is efficient for spotting outliers, but weak for explaining them. The editor stack is useful for batch data entry, but weak for investigation. The generated answer has low visibility, so the operator cannot quickly distinguish among:

- bad retrieval with a plausible answer;
- good retrieval with a bad answer;
- missing ground_truth causing unavailable context_precision;
- good answer but incomplete reference answer;
- low RAGAS score caused by metric limitations rather than model failure.

For forensic evaluation, the cognitive unit should be one case, not one table row and one separate editor.

---

## 3. Operational Workflow Analysis

Assistant Flow's operational console pattern is strongest when the left side is a compact navigation surface and the right side is a focused evidence surface. This already works well for logs, RAG sessions, and recent RAG turns: the operator selects one operational entity, then inspects its evidence without losing list context.

Evaluation Run analysis has similar operational shape:

- The run is the experiment boundary.
- Items are the cases inside that boundary.
- Metrics are signals for prioritization.
- The answer, ground_truth, and retrieval chunks are evidence.
- Manual score and notes are operator judgement.

The current layout treats all run items as simultaneously editable. That is reasonable for minimal P2-lite functionality, but it does not scale as an operational review workflow. As runs grow beyond a handful of imported turns, a full table plus all editors becomes noisy. The operator needs a way to triage many items while deeply inspecting one selected item.

The operational workflow should therefore separate two modes without creating a new dashboard:

- Run triage: compact list/table of items with status, key metrics, and ground_truth availability.
- Item forensic analysis: selected case with full question/answer/reference/context/metrics relationship.

---

## 4. Evaluation Mental Model

The correct mental model is:

> An evaluation run is a container; an evaluation item is the unit of truth.

Run-level data answers:

- What was evaluated?
- Under which import/replay/config conditions?
- What is the aggregate quality signal?
- Can RAGAS be run or refreshed?

Item-level data answers:

- What was the user question?
- What answer did the system generate?
- What should the answer have been?
- Which chunks were retrieved?
- Did the chunks support the answer?
- Which metric failed, and is that failure meaningful?
- What manual judgement should be recorded?

RAGAS scores should not be presented as isolated numeric columns only. They are diagnostic annotations over the relationship among answer, context, and ground_truth. This means answer + ground_truth + metrics + retrieval context should become one unified evaluation item surface.

---

## 5. Run-Level vs Item-Level Separation

Run-level UI should remain visible but compact. It should not dominate the forensic surface after a run has been selected.

Recommended run-level responsibilities:

- Run title, id, status, creation time.
- Run action area: Run RAGAS, refresh.
- Compact summary: item count, import mode, dataset/config snapshot hints.
- Aggregate RAGAS means and unavailable metric notes.
- Source execution ids in a compact, secondary area.

Recommended item-level responsibilities:

- Compact item selector/list with ordinal, query preview, ground_truth state, status, and key metric chips.
- Selected item detail with question, generated answer, ground_truth editor, manual score/notes, metrics, and retrieval chunks.
- Retrieval chunks attached to the selected item, not to the run as a whole.

The separation should be visual and semantic: run summary describes the experiment, selected item explains one case.

---

## 6. Proposed Layout Evolution

The current hypothesis of a master-detail forensic layout fits operational RAG evaluation well.

Recommended incremental direction:

- Keep the existing outer `/evaluation` two-tab console.
- Keep the runs list on the left exactly as the run navigation entry point.
- Inside the selected run detail, replace the current "metrics table + all editors" stack with an item-focused split.
- Use a compact item list/table as the master area for the run's items.
- Use a selected item panel as the detail area.

The selected item panel should make the following relationship explicit:

- Question: primary input under evaluation.
- Generated answer: prominent evidence, not hidden or omitted.
- Ground truth: adjacent to answer, editable in place.
- Metrics: nearby as diagnostic labels or compact rows, not detached from evidence.
- Retrieval context: below or beside the answer/reference block, using the existing shared retrieval chunk cards.

Retrieval chunks should remain compact and expandable. They should not become a document viewer. In the selected item detail, chunks should answer: "What evidence did the model have?" The full-text modal remains appropriate for overflow, but the preview stack should be close enough to the answer to support faithfulness/context_precision reasoning.

Run summary should remain above the item forensic area as a compact strip/panel group. It should not scroll the operator far away from item analysis or require repeated re-reading during case review.

The current multi-editor layout should be retired in favor of editing the selected item. Batch editing all ground_truth fields at once is less important than preserving answer/reference/context coherence during review. If batch workflows are needed later, they can be a separate mode, not the default forensic layout.

---

## 7. Risks And Tradeoffs

The master-detail model improves forensic clarity but introduces tradeoffs:

- It may slow pure batch ground_truth entry because only one item is primary at a time.
- It requires reliable selected-item state and sensible default selection, especially after RAGAS reruns or item updates.
- If the item list becomes too narrow, metric labels may become cryptic; compact chips should be carefully named.
- If retrieval chunks are shown too prominently, they can crowd out answer vs ground_truth comparison.
- If run summary remains too large, the new item detail will still feel vertically constrained.

The key risk is overcorrecting into a large "case page" that becomes a dashboard tile or article reader. The AF visual language should remain dense, operational, and evidence-oriented.

The safest incremental path is to preserve the existing data flow and API shape, only changing the presentation hierarchy when implementation begins.

---

## 8. Recommended Next Implementation Step

The next implementation step should be narrow:

Build an item-focused run detail layout for the existing `EvaluationPage` using the current API response only.

Recommended implementation boundaries for the next pass:

- Frontend only.
- No backend/schema changes.
- Preserve run list, tabs, filters, import workflow, RAGAS run action, and shared retrieval chunk component.
- Add selected evaluation item state within `RunDetailPanel`.
- Replace the visible "all item editors" default with one selected item analysis panel.
- Keep a compact item list/table for navigation and triage.
- Show answer, ground_truth editor, manual score/notes, metrics, and retrieval chunks for the selected item as one unified forensic case.

This is an incremental layout evolution, not a redesign of the Evaluation subsystem. It aligns the UI with the existing Evaluation Layer architecture where `evaluation_item` is the atomic result and `evaluation_run` is the container for comparison and aggregation.

---

## Verification Note

No build or runtime verification was performed because this task intentionally made no code changes.
