# Design: T2 → 4×8 cascade (8→6) + back-lift day swap

**Date:** 2026-06-28
**Status:** Approved — pending implementation plan
**Parent:** `2026-06-27-sbs-local-webapp-redesign-design.md`

## Goal

Two changes the user requested:

1. **T2 tier rule change**: all T2 (back) lifts move from the current GZCLP 3×10 → 3×8 → 3×6 cascade to a **modified 4×8**: fixed 4 sets × 8 reps, with the failure cascade shifted to **8 → 6** (drop the 10 level), reset back to 8 at the bottom.
2. **Back-lift swap**: Barbell rows (day 1) and DB rows (day 2) trade days, each carrying its own weight/state/history. End state: Day 1 = DB rows @ 65 kg, Day 2 = Barbell rows @ 85 kg.

## T2 progression rule (new)

Replaces `sbs_cli/engine/progression.py::t2_next`. Same structure as today, with the 10 level removed and the reset target changed from 10 to 8:

```
t2_next(state, actual, est1rm, fail=3, incr=2.5, reset_pct=0.70, quantum=2.5):
  actual is None              -> unchanged (skip unlogged)
  actual >= state.target      -> hit: weight +incr, streak 0, stay at target
  state.streak + 1 >= fail:   -> Nth consecutive miss:
      target == 8             ->   downgrade to 4×6 (target 6, weight unchanged, streak 0)
      target == 6 (bottom)    ->   reset: weight = round(est1rm * reset_pct, quantum), back to target 8
  else                        -> miss under threshold: streak + 1, weight/target unchanged
```

`fail`, `incr`, `reset_pct`, `quantum` (all from settings/profile) are unchanged. Reset still uses `est1rm × reset_pct`; est1rm is populated from history by the time a reset can trigger (3 consecutive misses at target 6), so the None case does not arise in practice.

## Engine / code changes

- **`sbs_cli/engine/progression.py::t2_next`**: cascade `10→8→6` becomes `8→6`; reset target `10` becomes `8`.
- **`sbs_cli/program.py::initial_state`**: T2 init `target=10` → `target=8` (used by migrate/xlsx cold-start).
- **`webapp/repo.py::_init_lift_state`**: T2 branch `target=10` → `target=8` (used when adding T2 lifts via UI / migrate).
- No change to `sets` in code — `sets` is per-lift data (lifts.sets), not an init default. The 4 existing T2 lifts get `sets=4` via the data migration below. New T2 lifts added via the UI keep the form's generic sets default (user enters 4); making the form tier-aware is out of scope (YAGNI).

## Data migration (one-shot script against `sbs.db`)

Backup `sbs.db` → `backups/sbs-t2-4x8.db.bak` first, then:

1. **All T2 lifts** (`Barbell rows`, `DB rows`, `Pull-downs`, `Chin-ups`):
   - `lifts.sets`: 3 → 4.
   - `lift_state.target`: 10 → 8.
   - `weight`, `start`, `streak` (0), history (empty — week 1) unchanged.
2. **Back-lift day swap**: exchange `day` + `sort_order` between `Barbell rows` (day 1) and `DB rows` (day 2). Each lift keeps its own row (name/weight/state/history follow it).
   - Result: Day 1 lists DB rows @ 65; Day 2 lists Barbell rows @ 85.

Pull-downs (day 3) and Chin-ups (day 4) get the sets/target change but no day swap.

## Tests to update

- **`tests/test_progression.py`** (engine): the T2 cascade cases that assert `10→8→6` must be rewritten for `8→6` with reset-to-8. (These are among the original 74 engine tests; updating them is expected because the rule intentionally changed.)
- **`tests/test_repo.py::test_create_lift_t2_inits_weight_target`**: assert `target == 8` (was 10).
- **`tests/test_advance_service.py`** t2-hit case: reps=10 ≥ new target 8 → still hits, +incr, weight 87.5 — assertion unchanged; update the comment only.
- Add a small script-test (or one-off verification, not necessarily a kept test) confirming the migrated DB shows T2 sets=4, target=8, and the back lifts on the correct days.

## Out of scope (YAGNI)

- Configurable cascade levels / T2 sets via settings (a fixed rule change is all that was asked for).
- A new tier (`t2b`).
- Tier-aware default `sets` in the `/lifts/new` form.
- Re-migrating from `profile.yaml` (the legacy `state.yaml`/`profile.yaml` would still carry the old 3×10 target; not worth syncing — `sbs.db` is the source of truth).

## Notes

- The earlier "engine frozen" constraint was self-imposed to preserve proven logic during the redesign. The user explicitly requested this T2 rule change, so modifying `t2_next` / `initial_state` is now in-scope and approved.
- `profile.yaml` remains on the old 3×10 scheme; it is no longer the data source and is only used by a fresh `migrate --force` (rare). Acceptable drift.
