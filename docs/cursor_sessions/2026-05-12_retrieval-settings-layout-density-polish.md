# Session: Retrieval Settings UI density polish

**Date:** 2026-05-12  
**Goal:** At 100% browser zoom, the main Retrieval Settings view should fit on a typical laptop screen so the **Cache** block is visible with little or no extra scroll; **System paths** stays collapsed by default.  
**Commit:** none (manual verification pending).

## Changed files

| File | Change |
|------|--------|
| `frontend/admin-ui/src/styles/globals.css` | Tighter spacing, typography, inputs, table, alerts, details; cache two-column split + responsive stack. |
| `frontend/admin-ui/src/pages/RetrievalSettingsPage.tsx` | Cache: two columns (flags + TTLs | generation + `CACHE_DB_PATH` + bullets); switch-warning footer uses `retrieval-settings__alert-foot` instead of inline margin. |

## CSS / layout parameters tightened (scoped under `.retrieval-settings` unless noted)

- **Page chrome:** `.page__title` / `.page__lead` — smaller font, reduced bottom margin, tighter line-height on lead.
- **Cards:** `.section-card.card` — less padding; `.section-card__header` — smaller margin; `.card__body` — smaller font + line-height.
- **Card titles:** `.section-card__header .card__title` — slightly smaller; `.section-card__desc` — smaller font/line-height.
- **Row grids:** `.retrieval-settings__grid2` — gap `12px` → `8px`, bottom margin `12px` → `8px`.
- **Head row:** `.retrieval-settings__head` — gap and `margin-bottom` reduced.
- **Alerts / lists:** `.retrieval-settings__alert*` padding, font-size, line-height; `.retrieval-settings__warn-list` margins and typography; new `.retrieval-settings__alert-foot` for post-warning note.
- **KV grids:** `.retrieval-settings__kv` — narrower label column min, row/column gaps, `margin-bottom`, base font-size.
- **Switch row:** `.retrieval-settings__switch-row`, `__label`, `__select`, `__apply` — padding/gap/font-size.
- **Hints / subwarn:** `.retrieval-settings__hint`, `__subwarn` — margins and font-size.
- **Health matrix:** `.retrieval-settings__table` — cell padding `6px 8px` → `4px 6px`, header row padding, font-size, line-height; `.retrieval-settings__cell-detail` — max-width slightly larger for readability + smaller type/line-height; `.retrieval-settings__pill` compact; `.retrieval-settings__table .status-badge` — slightly smaller padding/font.
- **Read-only inputs:** `.retrieval-settings__ro` — padding, border-radius, `font-size`, `line-height`, `min-height` for consistent short rows.
- **Micro copy:** `.retrieval-settings__micro`, `__micro-alert`, `__note-list` (and `li` spacing).
- **System paths `<details>`:** summary/body padding and margins reduced.
- **Full-width Cache card:** `.retrieval-settings > .section-card.card` — `margin-bottom: 8px` before collapsed paths.
- **Cache split:** `.retrieval-settings__cache-split` — two columns ≥961px; stacks to one column in same breakpoint as main grid (`max-width: 960px`).

## What did not change

- **API**, backend routes, retrieval overview payload, switching logic.
- **Copy** for “no silent fallback…” lead paragraph and other product wording (only layout/classes around switch warnings).
- **Collapsed-by-default** System paths `<details>` behavior and inner field set.
- **Active row** highlight rule (same background color; only surrounding density changed).

## Manual verification note

1. Open **Retrieval Settings** at **100%** zoom on a ~1080p (or typical laptop) display: confirm Row 1 + Row 2 + Cache (+ collapsed paths header) fit with minimal scroll.
2. Confirm **Cache** two-column layout on wide view; below **960px** width, confirm Cache stacks to a single column and main grids collapse to one column without overlap/broken scroll.
3. Expand **System paths** — long values still wrap/read; no regression on read-only fields.
