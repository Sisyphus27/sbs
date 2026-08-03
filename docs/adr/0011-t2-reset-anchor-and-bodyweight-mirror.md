# 0011 — T2 reset anchored below the failing weight; bodyweight T2 mirrors last reps

Two defects in the `linear_t2` progression were resolved together; both stem from the reset
term using `est1rm` drawn from the **whole** history.

## Defect 1 — barbell T2 reset could loop forever

`t2_next` reset to `round(est1rm × reset_pct)`. `est1rm` is `best_1rm` over the entire history
(ADR 0004 seam), i.e. the **strongest set ever**, which usually predates the slump. After `fail`
consecutive misses at some weight, resetting to `old_peak × 0.75` can land at/above the weight
that just failed — so the lifter fails again, the peak never leaves the history, and the reset
repeats the same weight indefinitely. Fix: anchor the reset strictly below the failing weight —

```
reset = round(min(est1rm × reset_pct, max(weight − incr, 0)), quantum)
```

No lower-bound floor is applied beyond the `≥ 0` guard: a too-light reset is harmless because
every hit adds `incr` and climbs back. The lifter confirmed this is the desired behavior.

## Defect 2 — bodyweight T2 reset is meaningless

For a bodyweight lift (`bodyweight_pct > 0`, e.g. Chin-ups) the stored `weight` is the *added*
weight, normally `0`. There is no weight to deload, so "reset to est1RM × 0.75" is incoherent —
and under the new anchor it would clamp the added weight to `0` anyway. The user ruled that a
bodyweight T2 needs no miss/reset machinery at all, only an approximate rep target.

Chosen behavior for `bodyweight_pct > 0` `linear_t2`:

- **No reset, no 8→6→4 cascade, no streak.** The ladder only ever lowers the target; with no
  climb-back it could never rise again, which the user flagged as wrong.
- **Target reps mirror the last logged set, clamped to `[4, 10]`** (`clamp_bodyweight_target`).
  This self-adjusts both down (bad day → lower target) and up (recovery → higher target), which
  a pure descend-only cascade cannot.
- `weight` stays at `start` (added weight, typically 0); `est1rm` keeps using the working-weight
  seam unchanged.

Barbell T2 (`bodyweight_pct == 0`) is unaffected and keeps the cascade + the Defect-1 anchored
reset.

## Considered Options

- **Period-scoped est1rm (user's original idea)**: compute the reset's est1rm only from the
  current miss-period, excluding old peaks. Rejected as more machinery (period-boundary tracking
  in both `advance` and `recompute_state`) for the same effect as the `min(weight − incr)` anchor.
- **Fixed-percentage deload (`weight × 0.9`)**: simpler still, but discards the individualized
  `est1rm × reset_pct` term the program already computes.
- **Bodyweight: descend-only cascade that just never resets**: rejected — the target could never
  climb back (the code documents "no climb-back"), so reps would ratchet down permanently.

## Consequences

- `t2_next` signature unchanged; both the live path (`LinearT2Mode.advance`) and the replay path
  (`recompute_state`) pick up the anchor automatically because both call `t2_next`.
- The bodyweight branch lives in `LinearT2Mode.advance` and `recompute_state`, keyed off
  `lift.bodyweight_pct > 0`, and bypasses `t2_next` entirely.
- `derive_on_switch` (mode-switch preview/apply) for bodyweight `linear_t2` still derives a
  weight from `est1rm × t2_reset_pct`; unifying that with the mirror rule is explicitly deferred.
