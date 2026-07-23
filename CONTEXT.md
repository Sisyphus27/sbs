# SBS

A strength-training program tracker combining the SBS RTF (Reps-to-Failure) main/auxiliary
progression with GZCLP-style T2/T3 linear progression. The engine lives in `sbs_cli/`; the
Flask/HTMX webapp in `webapp/`.
This glossary defines the program-domain terms shared across both; it is deliberately free of
implementation detail.

## Language

**Lift**:
A single scheduled instance of an exercise on a specific day — the atomic unit of progression,
logging, and state. The same exercise scheduled on two different days (e.g. Face Pull on Day 2
and Day 4) is **two lifts**, each with its own working weight, tier state, and history. All
per-lift comparisons (e.g. tonnage WoW) are per lift-row, never aggregated by exercise name.
_Avoid_: exercise, movement (those name the movement pattern; a lift is one scheduled instance
of it); 动作 (colloquial — maps to a lift-row here, not the exercise name)

**Training Max (TM)**:
The internal reference ceiling for an sbs lift, from which each week's working weight derives
(`working weight = MROUND(TM × intensity, rounding)`). Seeded from the lift's `max` on week 1
(or back-calculated as `repout_target / 0.9` when a rep-out target is supplied instead), then
auto-regulated weekly by the rep-out delta. A bookkeeping value — never loaded onto the bar,
kept at full float precision.
_Avoid_: 1RM, max (the lift's `max` is the seed, not the TM itself)

**Working Weight**:
The weight actually moved for a set — the value fed to every engine computation (est1RM,
tonnage, progression resets). For sbs = `MROUND(TM × intensity, rounding)`; for T2/T3 = the
lift's own progressing weight; for a bodyweight lift = `Added weight + bodyweight × bodyweight_pct`.
Snapped to the rounding quantum where it is a loaded bar weight.
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

**Added weight (附加)**:
The extra external load on a bodyweight lift beyond the lifter's own body — a weighted belt,
dumbbell, vest, etc. What a bodyweight lift's `weight` / `start` field and `history.weight`
store. Zero for purely bodyweight reps. Distinct from Working Weight, which adds the bodyweight
component back in at the computation seam (ADR 0004).
_Avoid_: load, total weight

**Bodyweight**:
The lifter's measured body mass (kg) — a single global value (`settings.bodyweight` /
`Profile.bodyweight`), held static across history. Combined with a lift's bodyweight_pct to form
the bodyweight component of its working weight. Stored added weights are stable against
bodyweight drift by design (ADR 0004).
_Avoid_: body mass, user weight

**Bodyweight percentage (bodyweight_pct)**:
The fraction of the lifter's bodyweight that a bodyweight lift actually moves: ~1.0 for
pull-ups / dips / chin-ups, ~0.64 for push-ups, 0.0 for an ordinary barbell lift (no bodyweight
component). Stored per lift. The working weight's bodyweight term = `bodyweight × bodyweight_pct`.
_Avoid_: bodyweight fraction, load factor

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

**Training volume (tonnage)**:
The total load lifted by one lift in one week: working weight × total reps across all sets,
in kg. Computed as `weight × ((sets−1) × plannedReps + lastSetReps)` — every set but the last
is taken at its planned rep count (sbs: the scheduled reps; t2: target; t3: t3_target), and the
last set uses the reps actually logged for that week (the 末组 entry, whatever was filled in).
A per-lift, per-week quantity; the plan view shows each lift's tonnage against the previous
program week (WoW Δ%). An indicator of training load, not of progress — volume rises and falls
deliberately across a cycle (e.g. deload weeks).
_Avoid_: load (the weight on the bar for a single set), intensity

**Progression Mode (mode)**:
Which progression rule a lift follows: `sbs` (TM autoregulation by rep-out), `linear_t2`
(1-strike rep cascade with est1RM-based reset), `linear_t3` (threshold accessories), or `none`
(record-only — no automatic progression, used for pure-bodyweight lifts). A lift can be
switched between modes within the same load-model family; history is preserved across switches.
Replaces the old `tier` + `progression` pair (which overlapped: `progression="none"` was a
patch on top of tier). See ADR 0005.
_Avoid_: tier (the old field, which conflated progression rule with load bookkeeping), level

**Load Model (load_model)**:
How a lift's working weight is composed from its stored weight: `barbell` (working weight =
added weight only), `bodyweight` (working weight = added + bodyweight × bodyweight_pct, ADR
0004), or `pure_bodyweight` (added ≡ 0; working weight = bodyweight × bodyweight_pct). Fixed
at lift creation — switching the load model would reinterpret every history row's stored
weight and corrupt historical est1RM, so changing it means creating a new lift. Orthogonal to
Progression Mode except for the legal-combination constraints (ADR 0005).
_Avoid_: load type, weight model

**Pure Bodyweight**:
A lift moved by bodyweight alone, with no added external load (no weighted belt, dumbbell, or
vest). Modelled as `load_model = pure_bodyweight` bound one-to-one to `mode = none`: the engine
records history and est1RM but applies no automatic progression. Its working weight is entirely
the bodyweight term (bodyweight × bodyweight_pct). Distinguished from a `bodyweight` lift,
which carries added load and therefore must follow a progression mode.
_Avoid_: calisthenics (too broad — a weighted pull-up is bodyweight-with-load, not pure), unweighted

**Kind (main / aux)**:
Which of the two sbs progression tracks a lift follows, selecting its schedule ladder. Main
lifts run a 5-set, higher-intensity track; aux lifts a 4-set, lower-intensity track. A
property of an sbs lift, independent of mode (both tracks are `mode: sbs`); fixed when the
lift is created.
_Avoid_: mode (that selects the progression *rule family*, not the track)

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
