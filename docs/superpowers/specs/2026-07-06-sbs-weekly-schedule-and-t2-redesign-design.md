# Design: SBS weekly progression schedule + T2 1-strike cascade + reset-to-default

**Date:** 2026-07-06
**Status:** Approved (post-grilling) — pending implementation plan
**Parent:** `2026-06-27-sbs-local-webapp-redesign-design.md`; supersedes the T2 portion of
`2026-06-28-t2-4x8-cascade-redesign-design.md` (cascade rule revised here)

## Problem (from analysis)

Two gaps surfaced when week 2 did not match the reference `SBS RTF filled GZCLP.xlsx`:

1. **SBS main/aux tier has no weekly progression.** `lifts.intensity / reps / repout` are static
   columns read directly every week. Only `tm` auto-regulates by rep-out performance, so the working
   weight barely moves and `reps` / `repout` never change. The real SBS RTF program is a **fixed
   21-week schedule** where intensity ramps in a 3-week wave and `reps` / `repout` decrease each
   week (e.g. Squat W1 = 70%/5/10, W2 = 75%/4/8, W3 = 80%/3/6, W4 wave-back to 72.5%/5/9). The app
   shows W1 values forever. **Sets are correctly fixed** (main = 5, aux = 4) — SBS RTF never changes
   set count.

2. **T2 cascade rule is wrong for the user's intent and drifts from its own spec.** Engine
   `t2_next` runs 8→6→4→reset with a **3-strike** gate per level. The user wants **1-strike**: each
   miss drops one level immediately; after `t2_fail` misses, reset. The chin-ups observation
   (`streak=1`, reps still 8) is correct under the old 3-strike rule but wrong under the intended
   1-strike rule.

Side note (not a bug): the "0.0kg x 8 x **3**" display came from the legacy CLI reading
`state.yaml` (`sets: 3`). The webapp reads `sbs.db` (`sets = 4`) and correctly shows "8 x 4".

## Goal

Make SBS main/aux lifts follow the real SBS RTF 21-week weekly schedule, make T2 drop one rep
level per miss, add cycle-boundary reseeding, and add reset-to-default controls for non-weight
configuration.

## Scope

**In:**
- New `sbs_schedule` table (21 weeks × 2 kinds), seeded from standard SBS RTF values, editable.
- `lifts.lift_kind` column (`main` / `aux` for sbs; NULL for t2/t3); set explicitly in the lift form.
- Engine + webapp plan/preview/recompute read (intensity, reps, repout) from the schedule, keyed by
  `(lift_kind, schedule_week)`.
- T2 `t2_next` rewritten to 1-strike cascade through `[8, 6, 4]`, reset after `t2_fail` misses.
- Cycle-boundary **reseed**: at the start of a new cycle (program week 22, 43, …), prompt per sbs
  lift to set `TM = newly tested max`; skippable.
- `/schedule` editor page; `/reseed` page (or modal) driven by a `/plan` banner.
- Per-field "reset to default" buttons on `/settings` for non-weight params, and a "reset schedule"
  button on `/schedule`.
- Central defaults module (settings defaults + main/aux 21-week ladders).
- One-shot migration script: create schedule, backfill `lift_kind`, replay T2 state under the new rule.

**Out (YAGNI):**
- Per-lift schedules (all mains share one ladder, all auxs share another).
- Custom deload logic — deload weeks are simply rows 7/14/21 in the standard schedule.
- Retiring the now-vestigial `lifts.intensity / reps / repout` columns (kept; code stops reading
  them for sbs; the sbs form hides their inputs).
- Freezing per-history-row repout for `recompute_sbs_tm` (chose current-schedule replay instead;
  see "Decisions" Q6). Add later if history grows and schedule edits become frequent.

## Decisions resolved during grilling

| # | Decision | Choice | Rationale |
|---|---|---|---|
| Q1 | Cycle boundary (W21→W22) | **Prompt to reseed** | Real SBS RTF retests max after 21 weeks; surface it explicitly |
| Q2 | Reseed semantics | **Per-lift; TM = new tested max; skippable; history kept** | Retest is a measured 1RM; per-lift because retests happen on different days; skip = escape hatch |
| Q3 | `lift_kind` for new sbs lifts | **Explicit main/aux selector in the form** | Explicit > inferred; avoids NULL-kind breakage |
| Q4 | sbs form `intensity/reps/repout` inputs | **Hide for sbs** | Schedule is the only source; dead editable inputs mislead |
| Q5 | T2 state at migration | **Replay history through new rule** | State must match "new rule if it had always been active"; forward-only breaks 1-strike semantics |
| Q6 | `recompute_sbs_tm` contract | **Use current schedule; signature gains `schedule`** | Retroactivity only on explicit recompute (gated double action); user has minimal history now |

See ADR 0002 for the cycle/reseed decision (hard-to-reverse + surprising + real trade-off).

## Data model

New table:

```sql
CREATE TABLE sbs_schedule (
  kind      TEXT NOT NULL,      -- 'main' | 'aux'
  week      INTEGER NOT NULL,   -- 1..21
  intensity REAL NOT NULL,      -- 0 < intensity < 1
  reps      INTEGER NOT NULL,   -- > 0
  repout    INTEGER NOT NULL,   -- > 0
  PRIMARY KEY (kind, week)
);
```

`lifts` gains `lift_kind TEXT NULL` (set by the form for sbs; NULL for t2/t3).

`lift_state` gains `reseeded_cycle INTEGER NOT NULL DEFAULT 0` (the cycle number this sbs lift was
last reseeded, or skipped; 0 = never).

Program-week → schedule-week (pure helper): `schedule_week(pw) = ((pw - 1) % 21) + 1`.
Cycle number: `cycle_number(pw) = ((pw - 1) // 21) + 1`.

## Engine changes (`sbs_cli/`)

**`engine/progression.py`** — rewrite `t2_next` (1-strike):

```
t2_next(state, actual, est1rm, fail=3, incr=2.5, reset_pct=0.75, quantum=2.5):
  if actual is None:                       -> unchanged
  LADDER = [8, 6, 4]
  if actual >= state.target:               # HIT: stay, +incr, streak 0
      return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
  # MISS
  new_streak = state.streak + 1
  if new_streak >= fail:                   # Nth consecutive miss -> reset
      return T2State(8, 0, round_weight(est1rm * reset_pct, quantum))
  idx = LADDER.index(state.target)
  next_target = LADDER[min(idx + 1, len(LADDER) - 1)]   # drop one level, floor at 4
  return T2State(next_target, new_streak, state.weight)
```

`t2_fail` keeps meaning: reset depth (`fail=3` → 8→6→4→reset; `fail=2` → 8→6→reset). Edge: `fail=1`
collapses the cascade — any miss resets to 8 at `reset_pct × est1RM`. Documented; reset-default
restores 3.

**`program.py`** — schedule-driven paths:

```python
# week_plan (sbs branch):
sw = schedule_week(week)
sc = schedule_lookup(lift.lift_kind, sw)
w = round_weight((ls.tm or 0) * sc.intensity, profile.rounding)
PlanItem(..., reps=sc.reps, sets=lift.sets, repout=sc.repout, ...)

# advance_lift (sbs TM autoreg uses the scheduled repout):
state.tm = sbs_next(state.tm, sc.repout, actual_reps)

# recompute_sbs_tm: signature (lift, history) -> (lift, history, schedule);
# per-row repout from the schedule at each history row's program week:
tm = lift.max
for h in sorted(history, key=lambda x: x.week):
    sc = schedule_lookup(lift.lift_kind, schedule_week(h.week))
    tm = sbs_next(tm, sc.repout, h.reps)
```

`sets` still comes from `lifts.sets`. `recompute_state` (t2 path) picks up the new `t2_next`
automatically; no signature change.

The CLI (`sbs_cli/`) reads legacy YAML, not `sbs.db`; the schedule feature is webapp-only this work
item. Pure helpers (`schedule_week`, `schedule_lookup`, `t2_next`) live in the engine and are reusable.

## Cycle boundary & reseed

At program week `pw`, an sbs lift is **due for reseed** iff:
`schedule_week(pw) == 1 AND pw > 1 AND lift_state.reseeded_cycle < cycle_number(pw)`.

`/plan` shows a banner listing due sbs lifts when any is due. Each links to `/reseed` (page or
modal): enter a new tested max per lift → on submit, `lift.max = X; lift_state.tm = X;
lift_state.reseeded_cycle = cycle_number(pw)`. Each lift has a **Skip** action → sets
`reseeded_cycle = cycle_number(pw)` without touching `tm` (TM keeps autoregulating across the
boundary). History is preserved (est1RM trend unaffected). Reseed is sbs-only (T2/T3 have no TM).

## Webapp changes (`webapp/`)

- **`routes/plan.py` + `services/preview.py`**: sbs working weight / displayed reps / repout come
  from `sbs_schedule` via `(lift_kind, schedule_week(settings.week))`. Preview uses
  `schedule_week(settings.week + 1)`. `/plan` renders the reseed banner when a lift is due.
- **`routes/schedule.py`** (new): `GET/POST /schedule` (edit 21-week tables); `POST /schedule/reset`
  restores default ladders. Validate `0 < intensity < 1`, `reps > 0`, `repout > 0`.
- **`routes/reseed.py`** (new): `GET/POST /reseed` (per-lift new-max entry + skip).
- **`routes/lifts.py`**: `create_lift` / update accept `lift_kind`; the form shows a main/aux
  selector for sbs and **hides** `intensity / reps / repout` inputs for sbs.
- **`routes/settings.py`**: add `POST /settings/<field>/reset` for each non-weight field.
- **`defaults.py`** (new): single source for `DEFAULT_SETTINGS` and `DEFAULT_SCHEDULE`; used by
  migration seed, `/schedule/reset`, and settings reset endpoints.

## UI

- `/schedule`: two 21-row tables (Main, Aux), cols intensity/reps/repout, editable; "Restore default
  schedule" button.
- `/reseed` (from `/plan` banner): lists due sbs lifts with new-max input + Skip each.
- `/settings`: per-field "↺ default" buttons for `days_per_week`, `t2_reset_pct`, `t2_fail`,
  `t3_target`. **No** button for `rounding`, `incr`.
- Lift form (new + edit): sbs shows `lift_kind` selector (main/aux) and hides intensity/reps/repout.

## Defaults (standard SBS RTF 21-week ladders)

Seed for `sbs_schedule` and restore-default target. Weeks 7/14/21 are deload weeks.

```
MAIN (sets = 5):
 (1, 0.70, 5, 10), (2, 0.75, 4, 8),  (3, 0.80, 3, 6),  (4, 0.725, 5, 9), (5, 0.775, 4, 7),
 (6, 0.825, 3, 5), (7, 0.60, 7, 14), (8, 0.75, 4, 8),  (9, 0.80, 3, 6),  (10,0.85, 2, 4),
 (11,0.775,4, 7),  (12,0.825, 3, 5), (13,0.875, 2, 3), (14,0.60, 7, 14), (15,0.80, 3, 6),
 (16,0.85, 2, 4),  (17,0.90, 1, 2),  (18,0.85, 2, 4),  (19,0.90, 1, 2),  (20,0.95, 1, 1),
 (21,0.60, 7, 14)

AUX (sets = 4):
 (1, 0.60, 7, 14), (2, 0.65, 6, 12), (3, 0.70, 5, 10), (4, 0.625, 7, 13), (5, 0.675, 6, 11),
 (6, 0.725,5, 9),  (7, 0.50, 8, 18), (8, 0.65, 6, 12), (9, 0.70, 5, 10), (10,0.75, 4, 8),
 (11,0.675,6, 11), (12,0.725, 5, 9), (13,0.775, 4, 7), (14,0.50, 8, 18), (15,0.70, 5, 10),
 (16,0.75, 4, 8),  (17,0.80, 3, 6),  (18,0.75, 4, 8),  (19,0.80, 3, 6),  (20,0.85, 2, 4),
 (21,0.50, 8, 18)
```

`DEFAULT_SETTINGS`: `days_per_week = 4`, `t2_reset_pct = 0.75`, `t2_fail = 3`, `t3_target = 15`.
(`rounding`, `incr` excluded from reset.)

## Migration (one-shot `migrate_schedule.py`)

Backup `sbs.db` → `backups/sbs-schedule.db.bak`, then:

1. Create `sbs_schedule`; seed 42 rows from `DEFAULT_SCHEDULE`.
2. `ALTER TABLE lifts ADD COLUMN lift_kind TEXT`.
3. Backfill `lift_kind` for existing sbs lifts: `sets = 5 → 'main'`, `sets = 4 → 'aux'`.
4. `ALTER TABLE lift_state ADD COLUMN reseeded_cycle INTEGER NOT NULL DEFAULT 0`.
5. Replay every T2 lift's state with the new `t2_next` via `recompute_state` (history-driven).
   Chin-ups currently `target=8, streak=1` (old 3-strike); its logged miss must drop it to
   `target=6` under the new rule — the replay corrects this.
6. Leave `lifts.intensity / reps / repout` in place (vestigial for sbs after migration).

(User is at program week 2 = cycle 1; no reseed is due at migration.)

## Tests

- **`tests/test_progression.py`**:
  - `schedule_week`: 1→1, 21→21, 22→1, 43→1; `cycle_number`: 1→1, 21→1, 22→2.
  - `schedule_lookup(('main', 1..21))`, `(('aux', 1..21))` return the tables above.
  - `t2_next`: HIT stays + `+incr` + streak 0; MISS `@8→6`, `@6→4`; 3rd consecutive MISS resets to
    `8 @ round(est1rm*0.75, q)`; `fail=2` resets after `8→6`; HIT at `target=6` does not climb.
- **`tests/test_plan_route.py`**: at `settings.week = 2`, an sbs main lift renders intensity 0.75 /
  reps 4 / repout 8 from `sbs_schedule`.
- **`tests/test_reseed.py`**: at `settings.week = 22`, a main lift with `reseeded_cycle = 1` is due;
  POST new max → `tm = max = X`, `reseeded_cycle = 2`; Skip → `reseeded_cycle = 2`, tm unchanged.
- **`tests/test_migration.py`**: post-migration `sbs_schedule` has 42 rows; every sbs lift has
  non-null `lift_kind`; a T2 lift with one logged miss reports `target=6`.
- **`tests/test_settings_route.py`**: each reset endpoint restores the documented default;
  `rounding` / `incr` have no reset endpoint (404).

## Notes

- **Deload weeks (7/14/21) participate in TM autoregulation** like any week — faithful to the SBS
  RTF template (the delta table is uniform across all 21 weeks). A big rep-out on an easy deload
  week can nudge TM up; this matches the source.
- **Bodyweight T2 (chin-ups)**: `est1RM = 0` (history weight 0), so a reset yields
  `round(0 × 0.75, q) = 0` — i.e. the lift sheds any added weight and returns to bodyweight target
  8. Coherent: a "reset" for a bodyweight lift = drop added load, rebuild at 8 reps BW.
- **`recompute_sbs_tm` retroactivity**: editing the schedule then manually recomputing reshapes the
  stored TM trajectory (replay uses the current schedule). This is gated behind an explicit
  recompute action; normal advance freezes each week's delta at log time.
- `t2_fail` remains a meaningful knob (reset depth), so it keeps its reset-to-default button.
- The T2 portion of `2026-06-28-t2-4x8-cascade-redesign-design.md` is superseded by the 1-strike
  rule here; mark that doc superseded when this ships.
- TM full-precision (ADR 0001) is independent and unaffected.
