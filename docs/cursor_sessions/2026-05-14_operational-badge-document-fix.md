# Engineering log: operational modality badge — `document` → `doc`

**Date:** 2026-05-14 (from `date +%F`)

## Problem

In **Logs**, sessions with route/entity `document` showed the **`log`** mini-badge because `operationalModalityFromRouteKey()` had no branch for `document` and fell through to the default **`log`**. `document` is a first-class Assistant Flow bucket (upload / preprocess / index pipeline), not a generic log modality.

## Change

1. **`frontend/admin-ui/src/utils/operationalConsoleUi.ts`**
   - Extended **`OperationalModality`** with **`"doc"`**.
   - **`OPERATIONAL_MODALITY_LABEL`**: `doc` → displayed label **`doc`** (short badge text as requested).
   - **`MODALITY_ORDER`**: inserted **`doc`** before **`log`**.
   - **`normalizeOperationalModality`**: maps **`document`** and **`documents`** → **`doc`** before the fallback to **`log`** (so string props like `modality="document"` also resolve correctly).
   - **`operationalModalityFromRouteKey`**: early return **`doc`** for **`document`** and **`documents`** (matches **`pickRouteKey`** in Logs and route labels elsewhere).

2. **`frontend/admin-ui/src/styles/globals.css`**
   - Added **`.mini-badge--af-doc`** (distinct from gray **`.mini-badge--af-log`** and from **`.mini-badge--af-text`** — cool file/archive tint).

## Scope / unchanged behavior

- **`log`** remains the fallback for unknown route keys and empty keys (generic / technical events).
- **RAG / Text / Memory / …** mappings unchanged; no edits to **Documents** lifecycle UI (it does not use `operationalModalityFromRouteKey` today — only **Logs** and **Audio** list rows consume that helper for dynamic route keys).

## Verification (manual)

- Open **Logs**, filter **документ** / route **document**: list row badge should read **`doc`**, not **`log`**.
- Spot-check **RAG**, **Text**, **Memory** list badges unchanged.

## Commit

Not performed (per request).
