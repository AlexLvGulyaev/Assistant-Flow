# Evaluation Run UI — low-fidelity forensic layout specification

**Date:** 2026-05-15

**Scope:** layout specification only. No implementation, pseudo-code, CSS guidance, refactor plan, backend change, or schema change.

---

## 1. Screen Composition

The Evaluation Run screen should keep the existing AF operational console framing:

- outer console navigation remains `/evaluation`;
- left navigation remains the run selector area within the Evaluation runs tab;
- right side remains the evidence and action surface for the selected run.

Inside the selected run detail, the screen should be composed as:

1. Persistent compact run header.
2. Compact run-level summary strip.
3. Item forensic workspace.

The item forensic workspace should use a master-detail structure:

- left/sub-left area: compact item navigation for cases inside the run;
- right/main area: selected evaluation item evidence panel.

The primary focus area is the selected evaluation item evidence panel. Run-level summary exists to preserve experiment context, not to dominate the page.

---

## 2. Layout Hierarchy

Top-level hierarchy:

1. Evaluation tab shell.
2. Runs list navigation.
3. Selected run detail.
4. Selected item forensic detail.

Within the selected run detail:

1. Run identity and actions.
2. Run summary and aggregate RAGAS state.
3. Item navigation.
4. Selected item evidence.

The hierarchy should make clear that:

- `evaluation_run` is the container and comparison boundary;
- `evaluation_item` is the forensic unit;
- metrics are diagnostic annotations over an item, not the primary object by themselves;
- retrieval chunks are evidence attached to the selected item.

---

## 3. Run-Level Panel Specification

Run-level content should remain permanently visible while the operator is inside one selected run, but it should be compact.

Run header should contain:

- run name or short id;
- run status;
- created timestamp;
- primary action: Run RAGAS;
- refresh action.

Run summary strip should contain:

- item count;
- import mode;
- dataset/config hint;
- aggregate RAGAS status;
- aggregate metric means;
- unavailable metric notice;
- compact source execution id summary.

Run-level panels should answer:

- What experiment am I reviewing?
- Is the run completed/scored?
- Are RAGAS metrics available?
- What is the aggregate quality signal?

Run-level panels should not contain:

- full per-item editors;
- expanded retrieval chunks;
- long JSON/config bodies by default;
- large chart/dashboard areas.

During deep item inspection, the run summary should remain visible as a compact context band. It may be visually secondary, but it should not disappear entirely because operators need to maintain experiment context while moving across items.

---

## 4. Item Navigation Specification

Explicit recommendation: use a hybrid operational list, not a full data table as the primary item navigation.

Reason:

- A pure table is good for column comparison but poor for forensic case selection.
- A plain list is readable but can hide metric triage signals.
- A hybrid operational list preserves AF console density while showing enough metric/status information to guide selection.

Each item navigation row should include:

- ordinal;
- compact status;
- query preview;
- ground_truth state;
- key RAGAS metric chips or compact numeric values;
- optional warning state for missing ground_truth, unavailable metrics, or item error;
- short execution_id/correlation hint when available.

The row should not include:

- full generated answer;
- full ground_truth editor;
- retrieval chunk previews;
- large metric explanations.

Default selected item behavior:

- when opening a run, select the first item needing attention if one exists;
- priority order should be: item error, missing ground_truth, unavailable context_precision caused by missing ground_truth, low/failed metric, then first item;
- after RAGAS rerun or refresh, preserve selected item if it still exists;
- if the selected item no longer exists, fall back to the attention-priority rule.

Selection behavior should mirror other AF operational consoles: list remains available, selected item is visibly marked, and the evidence panel updates in place.

---

## 5. Selected Item Forensic Panel Specification

The selected item panel is the primary focus area.

It should present one evaluation case as a coherent evidence unit:

1. Item identity row.
2. Question.
3. Generated answer.
4. Ground truth and manual judgement.
5. Metrics.
6. Retrieval context.
7. Optional technical snapshot/correlation.

Item identity row should contain:

- item ordinal;
- item status;
- execution_id or correlation hint;
- source/import hint if useful;
- compact latency/token signals when available.

Question should be prominent and placed before the answer. It defines the evaluation target.

Generated answer should be highly visible. It is evidence, not secondary metadata. Operators should not need to leave the item panel to know what the system answered.

Ground truth should sit adjacent to the generated answer, not in a separate editor stack. The operator is comparing answer vs reference, so these must remain visually close.

Manual score and notes belong near the ground_truth block because they are the operator's judgement over the same comparison.

Metrics should appear near the answer/ground_truth comparison and before or alongside retrieval evidence. Their role is to explain what failed or passed:

- faithfulness relates answer to retrieval context;
- answer_relevancy relates answer to question;
- context_precision relates retrieval context to ground_truth/reference;
- manual score records operator judgement.

Metrics should not be isolated in a run-wide table only. The selected item panel should make each metric interpretable in context.

---

## 6. Retrieval Chunk Behavior

Retrieval chunks belong to the selected item detail, not the run summary.

Chunk placement strategy:

- show retrieval chunks below the question/answer/ground_truth/metrics comparison area;
- keep chunk cards compact and scan-friendly;
- preserve preview-first behavior;
- preserve full-text expansion through the existing modal pattern;
- include backend/source/score/relevance metadata as muted operational annotations;
- avoid turning the panel into a document reader.

Default chunk state:

- show compact previews for top chunks;
- keep all retrieved chunks available if the run item stores them;
- allow full text expansion one chunk at a time;
- avoid auto-expanding long chunk bodies.

Chunk behavior should support the forensic question:

> Did the retrieved evidence support the generated answer and the expected ground truth?

If metrics are weak, the operator should be able to inspect chunks without losing the answer/reference comparison.

---

## 7. Scroll And Interaction Behavior

Recommended scroll model:

- runs list scrolls independently;
- selected run detail owns the right-side vertical space;
- compact run header/summary remains at the top of the selected run detail;
- item navigation scrolls independently when item count grows;
- selected item evidence panel scrolls independently when answer/chunks are long.

The operator should be able to:

- change selected item without losing run context;
- scroll retrieval chunks without losing item identity;
- edit ground_truth/manual judgement without scrolling through unrelated items;
- refresh or rerun RAGAS without leaving the selected run.

The screen should avoid one long page that contains every item editor. Long-page scrolling causes the operator to lose both run context and selected-case context.

Interaction flow:

1. Select a run.
2. Review compact run summary.
3. Select or accept default selected item.
4. Inspect question, answer, ground truth, metrics, and chunks.
5. Edit ground_truth/manual judgement if needed.
6. Move to the next flagged item from the item navigation.
7. Rerun or refresh RAGAS when enough references are ready.

---

## 8. Density Strategy

The layout should feel like an operational forensic console.

Density principles:

- keep run summary compact;
- keep item rows short and scan-first;
- prioritize answer/reference/context adjacency over decorative spacing;
- use metrics as compact signals, not dashboard cards;
- show only one full item editor at a time;
- keep retrieval previews compact by default;
- avoid large empty states when data exists.

The screen must not become:

- BI dashboard;
- article reader;
- documentation viewer;
- analytics portal;
- large form builder.

The UI should support rapid investigation: "find the suspicious item, inspect evidence, make a judgement, move on."

---

## 9. Recommended Incremental Implementation Path

When implementation begins, the safest incremental path is:

1. Preserve the existing Evaluation page tabs and run list.
2. Preserve the existing run header and RAGAS action semantics.
3. Compress run summary into a stable context band.
4. Introduce selected-item state inside the run detail.
5. Replace the visible all-item editor stack with one selected item forensic panel.
6. Replace the primary per-item metrics table role with hybrid item navigation.
7. Place generated answer, ground_truth, manual score/notes, metrics, and retrieval chunks in the selected item panel.
8. Preserve current API/data shape and shared retrieval chunk rendering.

This should be treated as a presentation hierarchy evolution, not a backend or schema project.

---

## 10. Risks And Tradeoffs

Primary risks:

- Batch ground_truth entry may feel slower when only one item editor is primary.
- Metric comparison across many items may be less table-like unless item rows expose enough compact metric signals.
- Independent scroll regions can become confusing if too many panels compete for attention.
- Retrieval chunks can overwhelm the evidence panel if previews are too tall.
- Default item selection rules can surprise operators if the chosen attention priority is not visible.

Mitigations:

- keep item navigation dense and metric-aware;
- make selected item state obvious;
- keep run summary compact and stable;
- keep chunk previews collapsed/compact by default;
- preserve direct run-level RAGAS actions;
- defer batch editing mode unless real operator usage demands it.

The recommended tradeoff is to favor forensic clarity over batch editing speed. Evaluation quality work depends on understanding one case at a time: question, answer, ground truth, metrics, and retrieval evidence must be read together.
