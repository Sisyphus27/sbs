# Design: Start-Weight Recompute + T2 8→6→4 Cascade

**Date:** 2026-07-01
**Status:** Approved (brainstorming lock) — pending implementation plan
**Parent:** `2026-06-27-sbs-local-webapp-redesign-design.md`, `2026-06-28-t2-4x8-cascade-redesign-design.md`

## Problem (root cause)

User edited Barbell rows `start` weight 85→65 in 动作管理 (lift CRUD); the plan view kept showing 85.

Two weight columns diverge after lift creation:

- `lifts.start` — config column, "t2/t3 starting weight" (spec §5 of the redesign).
- `lift_state.weight` — engine-written "current working weight" (what the plan view reads for t2/t3).

At creation, `repo._init_lift_state` seeds `lift_state.weight` from `start` (they are equal). After creation, `repo.update_lift` (called by `lifts.py:edit`) updates **only** `lifts.start`; `lift_state.weight` is never re-synced. The plan view (`plan.py:_by_day`) reads `lift_state.weight` for t2/t3 → stale. (sbs plan weight derives from `lift_state.tm × lift.intensity`, not `start`, so sbs is unaffected.)

DB evidence: Barbell rows `lifts.start`=65.0 but `lift_state.weight`=85.0 (streak=0, no history — the 85 was the creation seed). All other t2/t3 lifts have `start == weight` because they were never edited post-creation.

## Desired behavior

`start` is the **progression basis** for t2/t3. Editing `start` at any week recomputes the current working weight by **replaying the progression from the new start through the history** (the per-week reps), arriving at the current week's plan.

Decision (confirmed with user):

- **History is immutable fact.** History rows `(week, weight, reps)` stay as the actual lifted weights. The replay uses only the `reps` to decide hit/miss/cascade at each step. `est1rm` stays derived from the real history weights — it does **not** change. Only `lift_state.weight/target/streak` are recomputed. (Chosen over rewriting history, which would fabricate `est1rm` and contradict the tier-switch design §6.3 "history is the truth of past performance.")
- **sbs is out of scope** — sbs has no start-based progression (uses `max`/`intensity`/`tm` autoregulation). Editing `start` for an sbs lift stores the value but performs no recompute.
- **Approach: pure engine replay function** (Approach A), not a derive-on-read projection (Approach C, deferred as over-scope) and not a service loop over `advance_lift` (Approach B, ruled out because `advance_lift` appends the fresh working weight into a throwaway history, yielding `est1rm` from the new weights = rewrite semantics, contradicting the immutable-history decision).

## §1. T2 engine change (orthogonal, ship together)

Extend the T2 failure cascade from `8→6` to **`8→6→4`**, and raise the reset percentage from 70% to **75%**.

`sbs_cli/engine/progression.py::t2_next`:

```
actual is None              -> unchanged (skip unlogged)
actual >= state.target      -> hit: weight +incr, streak 0, stay at target
state.streak + 1 >= fail    -> Nth consecutive miss:
    target == 8             ->   downgrade to 4×6 (target 6, weight unchanged, streak 0)
    target == 6             ->   downgrade to 4×4 (target 4, weight unchanged, streak 0)   [NEW]
    target == 4 (bottom)    ->   reset: weight = round(est1rm * reset_pct, quantum), back to target 8
else                        -> miss under threshold: streak + 1, weight/target unchanged
```

`reset_pct` default `0.70` → `0.75` (function signature default). `sbs_cli/data/schema.py::Profile.t2_reset_pct` default `0.70` → `0.75`. `webapp/db.py::_DEFAULT_SETTINGS["t2_reset_pct"]` `0.70` → `0.75`.

`initial_state` / `_init_lift_state` T2 init target stays `8` (unchanged — the cascade still begins at 8). `sets` unchanged (per-lift data).

Existing T2 rows are all `target=8, streak=0`; adding the 4 level requires **no target migration**. The `reset_pct` change is a global settings value update (see §5).

## §2. Engine replay function (core)

`sbs_cli/program.py::recompute_state(lift, history, profile) -> LiftState` — pure function.

- **t3**: `weight = lift.start or 0.0`; for each history row apply `t3_next(weight, h.reps, target=profile.t3_target, incr=profile.incr, quantum=profile.rounding)`. Return `LiftState(tier="t3", weight, target=None, streak=0, est1rm=_est1rm_from_history(history))`.
- **t2**: seed `(target=8, streak=0, weight=lift.start or 0.0)`; for each history row (in order): `est_k = _est1rm_from_history(history[:k+1]) or 0.0` (real weights, includes the current week — mirrors `advance_lift` which appends then derives), apply `t2_next(T2State(target, streak, weight), h.reps, est_k, fail=profile.t2_fail, incr=profile.incr, reset_pct=profile.t2_reset_pct, quantum=profile.rounding)`, update `(target, streak, weight)`. Return `LiftState(tier="t2", weight, target, streak, est1rm=_est1rm_from_history(history))`.
- **sbs**: raise `ValueError` — caller must not invoke for sbs (no start-based progression). The service guards on tier before calling.
- **Empty history**: loop body does not run; t2 → `(8, 0, start)`, t3 → `start`. This is the Barbell rows case.
- History rows correspond 1:1 with logged weeks (skipped/unlogged weeks produce no history row, same as `advance_lift` which appends only when `actual_reps is not None`); iterating history rows therefore replays exactly the logged weeks.

## §3. Service

`webapp/services/recompute.py::recompute_on_start_change(conn, lid, new_start) -> LiftState`:

1. `lift = repo.get_lift(conn, lid)`. If `lift["tier"]` not in `("t2","t3")`: return `None` (no-op for sbs).
2. `settings = repo.get_settings(conn)`; `history = [SetEntry(...) for h in repo.list_history(conn, lid)]`.
3. Assemble the engine dataclasses by **reusing** `webapp.services.advance._lift_from_row(lift)` and `_profile_from_rows(settings, [lift])` (a single-element lift list is fine — `recompute_state` reads only globals from `Profile`). The row already reflects `new_start` (it was just written by `update_lift`), so `_lift_from_row` carries it directly.
4. `ls = recompute_state(lift_obj, history, profile)`.
5. `repo.save_lift_state(conn, lid, tier=ls.tier, tm=None, weight=ls.weight, target=ls.target, streak=ls.streak, est1rm=ls.est1rm)`.
6. Return `ls` (for caller display/logging).

## §4. Trigger

`webapp/routes/lifts.py::edit`: after `repo.update_lift(conn, lid, **fields)`, re-fetch the row (`lift = repo.get_lift(conn, lid)`). If `lift["tier"] in ("t2","t3")` **and** `"start" in fields`: call `recompute_on_start_change(conn, lid, lift["start"])`.

No pre/post comparison is needed — **recompute is idempotent**: `recompute_state` is a pure function of `(start, history, settings)`, so re-submitting an unchanged `start` writes back the same state it already had (a harmless no-op). This also makes the trigger self-healing: any latent `start`/`weight` divergence is corrected whenever a t2/t3 lift's row is saved with a `start` field present, even if the user did not intend to change the weight.

No flash; the HTMX row swap already shows the new `start` in `_lift_row.html` meta, and the plan page reflects the new working weight on next load. (A flash would require a redirect that the partial-swap response path does not perform; skipped as YAGNI.)

Tier edits via the inline edit form are pre-existing behavior and out of scope for this change; the recompute keys off the **post-update** tier, so an inline tier change to t2/t3 with a present `start` recomputes from that start — acceptable and consistent.

## §5. Migration (light)

History table is empty (week 1, nothing advanced); all T2 lifts are `target=8, streak=0`. So:

1. **Backup** `sbs.db` → `backups/sbs-start-recompute-<ts>.db.bak`.
2. `UPDATE settings SET t2_reset_pct = 0.75 WHERE id = 1` (the live row is 0.7).
3. **Backfill**: for every t2/t3 lift, run `recompute_on_start_change(conn, lid, lifts.start)`. With empty history this sets `lift_state.weight = start`, clearing the Barbell rows 85→65 residual and any other latent divergence. (Equivalent to a one-shot resync; safe because history is empty — no replay side effects.)

Shipped as a small script `migrate_recompute.py` (mirrors the existing one-shot migration pattern), or invoked once from a Python shell against `sbs.db`. Idempotent: running it again re-derives the same state from the same (start, history).

## §6. Tests

**Engine (`tests/test_progression.py`, `tests/test_program.py`):**

- Rewrite the T2 cascade cases in `test_progression.py` for `8→6→4` with reset-from-4 at 75% (the `8→6`-only cases added in the prior cascade change now gain the `6→4` step). Assert default `reset_pct == 0.75`.
- `test_program.py::test_recompute_state_t3`: seed `start`, feed a history of reps (mix of hits/misses vs `t3_target`), assert `weight == start + incr * (#hits)` and `est1rm` equals `_est1rm_from_history(real history weights)`.
- `test_program.py::test_recompute_state_t2`: seed `start`, feed a history long enough to trigger the cascade and a reset, assert final `(target, streak, weight)` matches a hand-computed replay; assert `est1rm` unchanged from real history.
- `test_program.py::test_recompute_state_empty_history`: empty history → t2 `(8,0,start)`, t3 `start`.
- `test_program.py::test_recompute_state_sbs_raises`: sbs lift → `ValueError`.

**Service (`tests/test_recompute_service.py`, new):**

- t2/t3 recompute writes `lift_state` with replayed values; sbs lift → no-op (returns None, state unchanged).
- est1rm preserved (equals pre-recompute value derived from history).

**Route (`tests/test_routes_lifts.py`):**

- `test_edit_start_t2_recomputes_weight`: create a t2 lift (start=85), POST `/lifts/<id>/edit` with `start=65`, assert `lift_state.weight == 65` (no history).
- `test_edit_start_sbs_no_recompute`: sbs lift, edit `start`, assert `lift_state.tm` unchanged.

**Migration:**

- One-off verification (script or manual): after migration, `settings.t2_reset_pct == 0.75` and every t2/t3 `lift_state.weight == lifts.start`.

## Out of scope (YAGNI)

- Derive-on-read projection for t2/t3 state (Approach C) — revisit only if start/state divergence recurs.
- Rewriting history weights on recompute (Option B) — rejected; fabricates est1rm.
- Preview/confirm flow for start-edit recompute — auto-recompute is the asked behavior; the row swap is sufficient feedback.
- Flash message for the recompute delta — partial-swap response path has no redirect; skipped.
- Tier-aware inline-edit form behavior — pre-existing; recompute keys off post-update tier.
- Making `start` meaningful for sbs — sbs uses `max`/`intensity`/`tm`; explicitly unchanged.

## Open items (deferred to implementation plan)

- Exact migration script location/invocation (`migrate_recompute.py` vs shell snippet) and whether to wire it into `migrate.py`.
- Whether `_profile_from_rows` should be generalized to accept a single lift cleanly (it already handles a list; the single-element call is a minor readability nit, resolved during implementation).
