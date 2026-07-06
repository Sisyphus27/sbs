# 0002 — Cycle-boundary TM reseed: prompt, per-lift, skippable

- **Date:** 2026-07-06
- **Status:** accepted

## Context

The SBS RTF program is a fixed 21-week schedule. Once the weekly-progression schedule lands
(see `2026-07-06-sbs-weekly-schedule-and-t2-redesign-design.md`), program week 22 maps back to
schedule week 1 with the lift's TM still auto-regulating continuously across the boundary. The
real program calls for **retesting your max** at the end of each 21-week cycle and starting the
next cycle from that new measured max. The engine had no concept of a cycle boundary — TM would
just keep drifting on rep-out deltas forever, which slowly decouples TM from reality across
multiple cycles and never surfaces the retest moment.

## Decision

At the start of each new cycle (program week 22, 43, … — i.e. `schedule_week(pw) == 1 AND pw > 1`),
each sbs lift is **due for reseed** until `lift_state.reseeded_cycle >= cycle_number(pw)`. The
`/plan` view surfaces a banner per due lift leading to `/reseed`, where the user either:

1. **Reseed** — enters a newly tested max `X`: `lift.max = X`, `lift_state.tm = X`,
   `lift_state.reseeded_cycle = cycle_number(pw)`. The new cycle's autoregulation starts fresh
   from the measured max.
2. **Skip** — `lift_state.reseeded_cycle = cycle_number(pw)`, TM unchanged. TM continues
   autoregulating across the boundary (the pre-reseed behavior).

Reseed is **per-lift and skippable** because retests happen on different days and a forced,
blocking, all-lifts-at-once reseed would be hostile. History is preserved (est1RM trend is
unaffected). Reseed is sbs-only — T2/T3 have no TM.

A pure helper `cycle_number(pw) = ((pw - 1) // 21) + 1` defines the cycle; `reseeded_cycle`
(default 0) records the last cycle a lift was reseeded-or-skipped.

## Why

The project's north star is faithfulness to the SBS RTF template, and that template's cycle
ends with a retest. Auto-applying a reseed would be dangerous (a guessed or stale max corrupts
TM); never surfacing it lets TM drift untethered across cycles. A **prompted, per-lift,
skippable** reseed is the only option that both honors the retest moment and leaves the human in
control of the one number (max) that should never be auto-derived. Per-lift matches how people
actually retest (one lift per session, not all four at once).

## Considered Options

- **B (chosen)** — prompted reseed per the decision above.
- **A** — pure cyclic wrap, TM persists, no prompt; reseed only via the existing manual
  `lift.max` + `recompute_sbs_tm` path. Rejected: hides the retest moment; a careful user still
  does it manually, a careless user never does and TM drifts.
- **C** — hard stop at program week 21 (program "completes"); no automatic cycle 2. Rejected:
  forces a manual restart ceremony; the schedule + autoreg model is naturally cyclic.

Within B, two sub-choices were settled:

- **TM = new tested max** (chosen) vs **TM = back-calc(repout_target / 0.9)** (first-week seed
  formula). The back-calc path is for "I have no measured max"; a retest is by definition a
  measured max, so `TM = max` directly.
- **Per-lift** (chosen) vs **global** reseed flag. Global is too coarse when retests land on
  different days.

## Consequences

- New `lift_state.reseeded_cycle` column + `/reseed` route + `/plan` banner.
- Reseed is non-blocking and idempotent: skipping just stamps `reseeded_cycle`; re-reseed
  overwrites `tm` and `lift.max` again.
- `recompute_sbs_tm` (which replays from `lift.max` over all history) does **not** know about
  mid-history reseeds — it treats `lift.max` as a single seed for the whole history. This is
  acceptable because recompute is a manual recovery action, not the normal path; a reseeded lift
  that is later "recomputed" would replay from the new max over old history. Documented as a
  known interaction in the spec's Notes; revisit if recomputing post-reseed becomes common.
