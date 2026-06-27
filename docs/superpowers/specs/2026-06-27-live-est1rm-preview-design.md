# Design: Live est1RM Preview (this-week, pre-advance)

**Date:** 2026-06-27
**Status:** Approved — implementing directly (small change)
**Parent:** `2026-06-27-sbs-local-webapp-redesign-design.md`

## Goal

When the user fills a lift's last-set reps in the plan page (autosaved to `week_log`), immediately show **that set's estimated 1RM** and the **delta vs the historical best est1RM** — without waiting for the end-of-week advance. So week 1 shows a live estimate the day the user trains, and later weeks show whether today's set beat the prior best.

## Approach

Extend the existing autosave endpoint (`POST /log/save`, already fires on input `change` via HTMX). After saving the rep to `week_log`, compute the preview server-side and return a small HTML snippet that HTMX swaps into the `.save-ok` span next to the input.

**Why server-side:** reuses the engine's `estimate_1rm` (Epley/Brzycki/Wathan average) and `_est1rm_from_history` — no formula duplication (DRY). Single HTMX request already in place; no new endpoint, no client-side JS.

## Components

- **`webapp/services/preview.py`** (new, one responsibility): `live_preview(conn, lift_id, reps) -> dict`
  - working weight: `sbs` → `round_weight(tm × intensity, rounding)`; `t2`/`t3` → `state.weight` (mirrors the plan display).
  - `est1rm = estimate_1rm(weight, reps)`.
  - `best = _est1rm_from_history(history)` (None if no history).
  - `delta = est1rm - best` (None if no history).
  - returns `{weight, est1rm, best, delta}`. Read-only; writes nothing.
- **`webapp/routes/plan.py` `save_log()`**: after `repo.save_log(...)`, call `live_preview`, render the snippet, return it (200). On empty/clear: `204` (span clears, no preview).
- **Template/CSS**: `.save-ok` already swapped; add `.up` (green) / `.down` (red) for the delta. Format: `≈{est1rm:.1f} {delta}` — delta `+3.0` green, `-2.0` red, no-history → `(首次)`.

## Distinction from stored est1RM

The plan row's meta line shows the **committed historical-best** est1RM (from `lift_state.est1rm`, updated only on advance). The `.save-ok` span shows the **this-week live** estimate. Different location + `≈` prefix + delta label keeps them unambiguous.

## Testing

- `tests/test_preview_service.py`: `live_preview` math correct; positive/negative delta vs history; `(首次)` when no history.
- `tests/test_routes_plan.py`: `/log/save` returns the snippet with the est1RM; clearing returns 204.

## Out of scope (YAGNI)

- Next-week TM/weight projection (option B, not chosen).
- Client-side JS computation.
- Accuracy correction for high-rep sets (caveat already in USAGE).
