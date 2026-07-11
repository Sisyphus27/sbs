# SBS

A strength-training program tracker combining the SBS RTF (Reps-to-Failure) main/auxiliary
tier with GZCLP T2/T3 tiers. The engine lives in `sbs_cli/`; the Flask/HTMX webapp in `webapp/`.
This glossary defines the program-domain terms shared across both; it is deliberately free of
implementation detail.

## Language

**Training Max (TM)**:
The internal reference ceiling for an sbs lift, from which each week's working weight derives
(`working weight = MROUND(TM × intensity, rounding)`). Seeded from the lift's `max` on week 1
(or back-calculated as `repout_target / 0.9` when a rep-out target is supplied instead), then
auto-regulated weekly by the rep-out delta. A bookkeeping value — never loaded onto the bar,
kept at full float precision.
_Avoid_: 1RM, max (the lift's `max` is the seed, not the TM itself)

**Working Weight**:
The weight actually loaded for a set. Always snapped to the rounding quantum. For sbs =
`MROUND(TM × intensity, rounding)`; for T2/T3 = the lift's own progressing weight.
_Avoid_: load, target weight

**Progression step**:
The weekly increment added to a T2/T3 lift's working weight on a hit (global default
`settings.incr`, overridable per lift via `lifts.incr`; NULL = inherit global live).
Distinct from the rounding quantum — a cable/attachment lift's step is a property of
the machine's plate stack (e.g. 5 kg jumps), not of the barbell plate grid.
_Avoid_: increment (ambiguous — see effective step / rounding quantum)

**Effective step (eff_incr)**:
The resolved progression step actually applied for a given lift: `lifts.incr` when set,
else the global `settings.incr`. It is both the Δ added on a T2/T3 hit (no further
rounding — self-quantising arithmetic) AND the grid that lift's T2 resets and tier-switch
starting weights snap to. Every lift therefore carries its own snap grid.
_Avoid_: increment (ambiguous)

**Loaded weight vs bookkeeping value**:
A load-bearing distinction. A *loaded weight* is put on the bar — the sbs working weight (rounded to the
rounding quantum) and T2/T3 increments and resets (rounded to that lift's
effective step). The two grids differ only when a lift sets a per-lift incr that
differs from the global rounding. A
*bookkeeping value* (TM) is internal state that drives future calculation but is never loaded,
and is therefore never rounded. Conflating the two is the root cause of the TM-rounding bug
(see ADR 0001).
_Avoid_: "round everything"

**Rounding quantum**:
The gym's minimum plate increment (default 2.5 kg, configurable at `/settings`). The parameter governing snap-to-grid for **sbs** loaded weights (working weight).
Explicitly NOT applied to TM, and NOT applied to T2/T3 increments/resets — those snap to
the effective step (per-lift incr ?? global incr). Kept as a single global setting for
configuration continuity; its behavioural scope was narrowed to sbs by ADR 0003.
_Avoid_: min increment, plate step, gym step

**Rep-out (repout target)**:
The target rep count for the last (AMRAP) set of an sbs lift; the baseline against which the
week's TM delta is measured (`delta = actual_reps − repout`).
_Avoid_: AMRAP target

**est1RM**:
Estimated one-rep max — the mean of the Epley, Brzycki, and Wathan formulas over the best
historical set. Used to seed T2 resets (`reset_pct × est1RM`) and displayed for trend tracking.
Full-precision in storage; displayed to 2 decimals.
_Avoid_: 1RM (that denotes an actual, measured max — a different concept)

**Tier**:
Which progression rule a lift follows: `sbs` (TM autoregulation by rep-out), `t2` (1-strike
rep cascade with est1RM-based reset), or `t3` (threshold accessories). A lift can be
switched between tiers; history is preserved across switches.

**Kind (main / aux)**:
Which of the two sbs progression tracks a lift follows, selecting its schedule ladder. Main
lifts run a 5-set, higher-intensity track; aux lifts a 4-set, lower-intensity track. A
property of an sbs lift, independent of tier (both tracks are `tier: sbs`); fixed when the
lift is created.
_Avoid_: tier (that selects the progression *rule family*, not the track)

**Schedule (21-week progression)**:
The fixed table of weekly (intensity, reps, repout) values that an sbs lift follows, one row
per week, organised by kind. The working weight is derived from the scheduled intensity, and
the displayed reps / repout come from the same row. Seeded from the SBS RTF template and
editable.
_Avoid_: progression table (too generic), weekly plan (that is the rendered output, not the input)

**Program week vs schedule week**:
Program week is the absolute, ever-incrementing counter (`settings.week`: 1, 2, 3, …). Schedule
week is the cyclic 1–21 row index that selects the current schedule row. TM autoregulation
persists across program weeks; the schedule repeats every 21 program weeks.
_Avoid_: bare "week" when the distinction matters

**Cycle**:
One 21-week pass through the schedule. Cycle 1 = program weeks 1–21; cycle 2 = 22–42; and so on.
The cycle boundary is where a max retest is expected (see Reseed).

**Deload week**:
Schedule weeks 7, 14, and 21 — low-intensity, high-rep rows interspersed every seventh week.
They participate in TM autoregulation like any other week, matching the SBS RTF template.
_Avoid_: rest week, unload

**Reseed**:
The optional, per-lift action at the start of a new cycle of setting `TM = a newly tested max`,
starting that cycle's autoregulation fresh. Prompted (not forced) and skippable; a skipped reseed
leaves TM autoregulating continuously across the boundary. History is preserved.
_Avoid_: TM reset (that implies a failure-driven event, like T2's), max update (that is the
mechanism, not the cycle-boundary event)

**1-strike cascade (T2)**:
The T2 progression rule: each rep miss drops the target one level (8 → 6 → 4); after a
configurable number of consecutive misses the lift resets to target 8 at a lower weight derived
from est1RM. A hit adds weight and stays at the current level. Replaces an earlier 3-strike
per-level cascade.
_Avoid_: GZCLP cascade (ambiguous — several variants exist)
