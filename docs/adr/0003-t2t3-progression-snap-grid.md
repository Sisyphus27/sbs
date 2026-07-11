# 0003 — T2/T3 progression snaps to the per-lift effective-step grid

- **Date:** 2026-07-11
- **Status:** accepted

## Context

ADR 0001 states the rounding quantum governs "all loaded weight — including T2/T3
increments and resets." That wording is barbell-shaped. Cable/attachment lifts (face pulls,
pull-downs) are loaded from a machine stack whose minimum jump (e.g. 5 kg) is a property of
the machine, independent of the gym's barbell plate increment (rounding, default 2.5 kg).
Introducing a per-lift `incr` (so a cable lift can progress 5 kg/week) exposes the mismatch:
if that lift's reset / tier-switch start weight snaps to the global rounding, the result
(e.g. `round_weight(52.5, 2.5) = 52.5`) is not loadable on a 5 kg stack — the opposite of
what rounding is for (keeping weights loadable).

## Decision

1. **T2/T3 hit progression is pure arithmetic.** A hit adds the effective step with no
   further snap: `weight + eff_incr`.
2. **T2 reset and tier-switch-derived T2/T3 starting weights snap to the effective-step
   grid** `round_weight(·, eff_incr)`, not the global rounding.
3. **The rounding quantum's behavioural scope narrows to sbs.** Only the sbs working weight
   `round_weight(TM × intensity, rounding)` snaps to it. (The setting stays global; renaming
   it is out of scope.)
4. **effective_step = per-lift `lifts.incr` ?? global `settings.incr`.** It is resolved at
   the engine entry points (`advance_lift`, `recompute_state`, `derive_state`). It is both
   the hit-add Δ and the snap grid for that lift's derived weights. Each T2/T3 lift carries
   its own snap grid.

## Why

Each lift is loaded by its own apparatus, which has its own minimum increment. Snapping a
cable lift's derived weight to a barbell grid yields a value the machine cannot load —
defeating the purpose of snapping. Default `incr = rounding = 2.5` makes every existing
result identical (add-path snap was a no-op, reset grid was already 2.5), so the change is
invisible unless a lift sets `incr ≠ rounding`.

## Considered Options

- **B (chosen)** — each lift snaps to its own eff_incr grid; default stays compatible.
- **A** — keep snapping reset/derived T2/T3 weights to global rounding. Rejected: cable T2
  (e.g. Pull-downs) resets come out non-loadable.
- **A′** — force `incr` to be a multiple of rounding. Rejected: couples a machine property
  to the barbell plate grid — exactly the category error this change fixes.
- **C** — don't snap derived T2/T3 weights at all (leave `est1rm × pct` raw float).
  Rejected: produces un-loadable fractional weights.

## Consequences

- `rounding` becomes behaviourally sbs-only (still a global setting; rename is out of
  scope). Each T2/T3 lift has its own snap grid (its eff_incr).
- Default `incr = rounding = 2.5` is fully backward-compatible.
- ADR 0001's "T2/T3 increments and resets" wording is superseded for T2/T3 by this ADR.
  ADR 0001 remains authoritative for TM accumulation and the sbs loaded weight.
