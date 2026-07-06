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

**Loaded weight vs bookkeeping value**:
A load-bearing distinction. A *loaded weight* is put on the bar (working weight, T2/T3
increments and resets) and is therefore always rounded to the rounding quantum. A
*bookkeeping value* (TM) is internal state that drives future calculation but is never loaded,
and is therefore never rounded. Conflating the two is the root cause of the TM-rounding bug
(see ADR 0001).
_Avoid_: "round everything"

**Rounding quantum**:
The gym's minimum plate increment (default 2.5 kg, configurable at `/settings`). The single
parameter governing snap-to-grid for every loaded weight. Explicitly NOT applied to TM.
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
Which progression rule a lift follows: `sbs` (TM autoregulation by rep-out), `t2` (GZCLP
4×8→4×6→4×4 cascade with est1RM-based reset), or `t3` (threshold accessories). A lift can be
switched between tiers; history is preserved across switches.
