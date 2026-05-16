# Full original task prompt

```md
# Task: Evaluation Run UI — master-detail forensic layout implementation (incremental pass)

Date: 2026-05-15

Status: active

Recommended Cursor model: Codex 5.3

---

# Context bootstrap

Assistant Flow operational context.

Before execution read:

- PROJECT_STATE.md
- docs/architecture/evaluation_layer_design.md
- docs/architecture/cursor_operational_workflow.md
- docs/cursor_sessions/2026-05-15_evaluation_layout_analysis.md
- docs/cursor_sessions/2026-05-15_evaluation_layout_specification.md

Use the layout specification as the implementation contract.

Current active subsystem:

Evaluation / RAGAS operational console.

Current sprint focus:

Incremental implementation of item-centric forensic evaluation workflow.

Important constraints:

- frontend only
- no backend changes
- no schema changes
- no API contract changes
- no broad refactor
- no dashboard redesign
- preserve existing Evaluation functionality
- preserve import/RAGAS actions
- preserve shared retrieval chunk rendering
- preserve AF operational console visual language
- preserve compact operational density

---

# Task

Cursor, implement the first incremental pass of the new master-detail forensic Evaluation Run layout.

Goal:

Transform the current run detail screen from:

- metrics table + multiple editor stack

into:

- compact run summary
- compact item navigation
- selected item forensic detail panel

without changing backend/API behavior.

---

# Required implementation scope

Implement ONLY the following:

## 1. Preserve existing outer Evaluation structure

Keep:

- `/evaluation`
- existing tabs
- existing runs list
- existing import workflow
- existing Run RAGAS action
- existing filters/pagination behavior

No navigation redesign.

---

## 2. Compact run summary strip

Compress current run summary into a compact operational context band.

Keep visible:

- run status
- item count
- aggregate metric summary
- run actions
- key config hints if already available

Do NOT keep:

- oversized metric cards
- vertically inflated summary sections
- large spacing

Run summary should remain visible but visually secondary.

---

## 3. Replace current item area with master-detail layout

Current problem:

- metrics table
- multiple ground_truth editors
- fragmented forensic workflow

Need:

LEFT/SUB-LEFT:
compact item navigation

RIGHT:
selected item forensic panel

---

## 4. Item navigation requirements

Use hybrid operational list behavior.

Each item row should contain:

- ordinal/index
- query preview
- compact status
- ground_truth state
- compact key metric signals/chips
- warning state if useful

Do NOT include:

- full answer
- full retrieval chunks
- expanded editors

Selection behavior:

- one selected item at a time
- selected row visually highlighted
- changing selection updates forensic panel in place

Default selected item:

prefer:
- item missing ground_truth
- failed/weak metric item
- otherwise first item

---

## 5. Selected item forensic panel

This becomes the primary focus area.

Must include in this order:

1. Item identity row
2. Question
3. Generated answer
4. Ground truth editor
5. Manual score / notes
6. Metrics
7. Retrieval chunks

Critical requirement:

Generated answer must be clearly visible and operationally readable.

Ground truth must sit adjacent to the generated answer.

Metrics must appear as compact diagnostic annotations near the answer/reference comparison.

---

## 6. Retrieval chunk behavior

Use existing shared retrieval chunk rendering.

Keep:

- compact chunk cards
- expand full text behavior
- compact metadata hierarchy
- operational density

Chunks belong ONLY to selected item detail.

Do not create:
- giant document viewer
- large stacked retrieval pages

---

## 7. Density requirements

The resulting screen must feel like:

- operational forensic console
- investigation workspace
- retrieval engineering surface

It must NOT feel like:

- dashboard
- analytics portal
- article reader
- form application

Prioritize:

- scanability
- compact density
- fast item triage
- answer/reference/context comparison

---

# Files

Likely:

- frontend/admin-ui/src/pages/EvaluationPage.tsx
- related evaluation UI components
- globals.css
- shared operational list helpers if already present

Backend untouched.

---

# Session logging requirements

Create session log:

docs/cursor_sessions/YYYY-MM-DD_evaluation_master_detail_implementation.md

Date:

```bash
date +%F
```

Session log must include:

1. Full original task prompt
2. Changed files
3. Layout decisions
4. What was intentionally preserved
5. Density/interaction rationale
6. Build verification
7. UI verification checklist
8. Operator commands

The full original task prompt must be copied into the beginning of the session log.

Session log is mandatory.

---

# Deliverable

At the end provide ONLY:

1. frontend build command
2. rebuild commands
3. 7-point UI verification checklist
4. git status

Commit НЕ выполнять.
```

## Changed files

- `frontend/admin-ui/src/pages/EvaluationPage.tsx`
- `frontend/admin-ui/src/styles/globals.css`
- `docs/cursor_sessions/2026-05-15_evaluation_master_detail_implementation.md`

## Layout decisions

1. Preserved existing `/evaluation` shell with tabs, left runs list, import flow, and `Run RAGAS` action.
2. Replaced run-detail inner area (`Per-item metrics` table + multi-item editors) with a master-detail workspace.
3. Added compact item navigation panel with:
   - ordinal
   - query preview
   - status
   - ground truth state
   - compact metric chips (`faith`, `ans.rel`, `ctx.prec`)
   - warning marker (`attention`) for missing GT / weak metrics / errors
4. Added selected-item forensic panel in required order:
   - identity row
   - question
   - generated answer
   - adjacent ground truth + manual score/notes editor
   - compact metrics annotations
   - retrieval chunks using existing shared rendering component
5. Implemented default item selection priority:
   - missing ground truth
   - weak metric item
   - first item fallback
6. Compressed run summary strip and added compact config hints (`backend`, `top_k`) without changing API contracts.

## What was intentionally preserved

- No backend changes.
- No schema/API changes.
- No route/navigation redesign.
- Existing runs list behavior and pagination/filters behavior unchanged.
- Existing import flow untouched.
- Existing `Run RAGAS` action semantics untouched.
- Existing shared retrieval chunk rendering (`OperationalRetrievalChunksSection`) preserved.
- Operational compact AF visual language preserved (no dashboard/card explosion).

## Density and interaction rationale

- Master-detail allows rapid triage (left list) plus deep forensic read (right panel) without context switching across long stacked editors.
- Generated answer and ground truth are intentionally adjacent to reduce cognitive distance in answer/reference comparison.
- Metric chips are compact diagnostic annotations, not standalone dashboard objects.
- Retrieval chunks remain compact and attached only to selected item, preserving evidence context and avoiding oversized viewer patterns.
- Independent list/detail scroll regions keep operator context stable during long answer/chunk inspection.

## Build verification

Executed:

```bash
cd frontend/admin-ui && npm run build
```

Result:

- `tsc -b && vite build` completed successfully.
- Output artifacts generated under `frontend/admin-ui/dist`.

## UI verification checklist (7 points)

1. `/evaluation` route still opens with both tabs (`Recent RAG turns`, `Evaluation runs`) and existing left runs navigation.
2. Selecting a run shows compact run header/summary strip with run actions and status.
3. Run detail now shows master-detail workspace: item navigation panel + selected-item forensic panel.
4. Item row selection updates forensic panel in place and selected row remains visibly highlighted.
5. Generated answer is clearly visible; ground truth editor + manual score/notes is adjacent to it.
6. Metrics appear as compact chips near answer/reference area (not only in a detached run-wide table).
7. Retrieval chunks render for selected item via shared chunk component, keeping compact cards/full-text behavior.

## Operator commands / next verification commands

```bash
cd frontend/admin-ui && npm run build
cd frontend/admin-ui && npm run dev
git status
```
