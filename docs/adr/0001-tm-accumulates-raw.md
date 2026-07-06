# 0001 — SBS Training Max accumulates raw; rounding applies only to loaded weights

- **Date:** 2026-07-06
- **Status:** accepted

## Context

The SBS RTF xlsx keeps each lift's Training Max (TM) at full precision and rounds only the
weekly working weight to the gym increment (`MROUND(TM × intensity, 2.5)`). The engine had been
rounding the TM itself every week (`round_weight(tm × (1 + delta), quantum)` in `sbs_next`),
which discards sub-quantum weekly deltas before they can accumulate. This **stalls upward
progression entirely** for any lift whose TM is below ~250 kg: a steady +0.5 %/week (beat the
rep target by one — the most common outcome) leaves the displayed working weight frozen
indefinitely.

## Decision

1. **TM is a bookkeeping value.** It accumulates raw (full float precision), never rounded.
   `sbs_next` returns `tm × (1 + delta)` with no `quantum` parameter.
2. **The `rounding` quantum applies ONLY to loaded weights** — sbs working weight, T2/T3
   increments and resets. It is never passed into TM calculation. The one mis-application
   (`program.py:48`, `quantum=profile.rounding` into `sbs_next`) is removed.
3. **Existing rounded TMs in the DB are corrected by a one-shot migration** that replays TM
   from `lift.max` over each lift's immutable history. This is xlsx-faithful: in the xlsx,
   editing `Max` recomputes every downstream TM from that `Max` (formulas reference the cell).

## Why

The project's north star is faithfulness to the SBS RTF template, verified cell-by-cell against
`SBS RTF filled GZCLP.xlsx` (TM rows `B4/I4/P4…` never `MROUND`; weight rows `B5/I5/P5…`
always `MROUND(·, rounding)`). It also matches the physical reality that the gym's 2.5 kg
minimum constrains what is *loaded*, not internal bookkeeping.

## Considered Options

- **A′ (chosen)** — migrate by replaying TM from `lift.max`; no guard. Matches xlsx behavior.
  Simple, idempotent.
- **A″** — also unify the tier-switch-into-sbs seed (currently `est1rm`) to a `max`-replay.
  Rejected: scope creep; tier-switch seeding is separate design debt.
- **D** — skip migrated lifts that were switched into sbs. Rejected: detection complexity for
  zero current-user benefit.
- **Guarded A** — skip lifts whose rounded replay mismatches the stored TM (heuristic for an
  edited `max`). Rejected: the guard would skip exactly the lifts xlsx semantics say to
  recompute — anti-faithful.

## Consequences

- Stored TM is a long float (e.g. `128.8875`). Display code rounds for presentation only
  (CLI `show`: 1 decimal; the value is never loaded so gym-increment rounding does not apply).
- **Two TM-seeding conventions now coexist.** Engine/migration seed TM from `lift.max`;
  tier-switch-into-sbs (`webapp/services/tier.py`) seeds TM from `est1rm`. A lift switched into
  sbs via the webapp and then touched by the migration will have its est1rm-seeded TM
  overwritten by a `max`-replay. Accepted for now; unification is a recorded follow-up.
- **Editing an sbs lift's `max` does not recompute its TM** (unlike the xlsx, where editing
  `Max` live-recomputes all TMs). Recorded follow-up — the migration's service wrapper
  (`recompute_sbs_tm`) is positioned to serve this when wired to the edit route.
