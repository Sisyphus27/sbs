# Design: SBS weekly progression schedule + T2 1-strike cascade + reset-to-default

**Date:** 2026-07-06
**Status:** Approved — pending implementation plan
**Parent:** `2026-06-27-sbs-local-webapp-redesign-design.md`, supersedes the T2 portion of `2026-06-28-t2-4x8-cascade-redesign-design.md` (whose cascade rule is revised here)

## Problem (from analysis)

Two gaps surfaced when week 2 did not match the reference `SBS RTF filled GZCLP.xlsx`:

1. **SBS main/aux tier has no weekly progression.** `lifts.intensity / reps / repout` are
   static columns read directly every week. Only `tm` auto-regulates (±a few %) by rep-out
   performance, so the working weight barely moves and `reps` / `repout` never change. The real
   SBS RTF program is a **fixed 21-week schedule** where intensity ramps in a 3-week wave, and
   `reps` / `repout` decrease each week (e.g. Squat W1 = 70%/5/10, W2 = 75%/4/8, W3 = 80%/3/6,
   W4 deload-wave back to 72.5%/5/9). The app shows W1 values forever. **Sets are correctly
   fixed** (main = 5, aux = 4) — SBS RTF never changes set count.

2. **T2 cascade rule is wrong for the user's intent and drifts from its own spec.** Engine
   `t2_next` runs an 8→6→4→reset cascade with a **3-strike** gate per level (a level only drops
   after `t2_fail` consecutive misses at that level). The user wants **1-strike**: each miss
   drops one level immediately; after `t2_fail` (default 3) misses, reset. The chin-ups
   observation (`streak=1`, reps still 8) is correct under the old 3-strike rule but wrong under
   the intended 1-strike rule. (`2026-06-28-t2-4x8-cascade-redesign-design.md` specified 8→6 only;
   that spec was never implemented and is itself superseded by the rule below.)

Side note (not a bug): the "0.0kg x 8 x **3**" display the user saw comes from the legacy CLI
reading `state.yaml` / `profile.yaml` (`sets: 3`). The webapp reads `sbs.db` (`sets = 4`) and
correctly shows "8 x 4". No code change needed for the set count; the legacy YAML files are no
longer the source of truth.

## Goal

Make SBS main/aux lifts follow the real SBS RTF 21-week weekly schedule, make T2 drop one rep
level per miss, and add reset-to-default controls for all non-weight configuration.

## Scope

**In:**
- New `sbs_schedule` table (21 weeks × 2 kinds), seeded from the standard SBS RTF values.
- `lifts.lift_kind` column (`main` / `aux` for sbs lifts; NULL for t2/t3).
- Engine + webapp plan/preview read (intensity, reps, repout) from the schedule, keyed by
  `(lift_kind, program-week)`.
- T2 `t2_next` rewritten to 1-strike cascade through `[8, 6, 4]`, reset after `t2_fail` misses.
- `/schedule` editor page (edit 21-week tables for main and aux).
- Per-field "reset to default" buttons on `/settings` for non-weight params, and a "reset
  schedule" button on `/schedule`.
- Central defaults module (settings defaults + main/aux 21-week ladders) used by migration and
  reset buttons.
- One-shot migration script: create schedule, backfill `lift_kind`, replay T2 state under the new
  rule.

**Out (YAGNI):**
- Per-lift schedules (all mains share one ladder, all auxs share another — by design).
- Custom deload logic — deload weeks are simply rows 7/14/21 in the standard schedule.
- Automatic TM reseed at cycle end — cycling returns to W1 with the persisted TM; retesting max is
  manual via existing `lift.max` + `recompute_sbs_tm`.
- Retiring the now-unused `lifts.intensity / reps / repout` columns (kept to avoid a destructive
  schema change; code simply stops reading them for sbs).
- A `lift_kind` selector in the new-lift form (kind is assigned by `sets`: 5 → main, 4 → aux at
  migration; manually editable in DB thereafter).

## Design decisions (locked)

| Decision | Choice |
|---|---|
| Schedule storage | DB table, editable |
| Schedule granularity | Per kind (main / aux), shared across all lifts of that kind |
| Editing surface | New `/schedule` page |
| Program-week → schedule-week | `sched_week = ((settings.week - 1) % 21) + 1` (cyclic) |
| T2 cascade | 1-strike drop `8→6→4`; reset after `t2_fail` misses |
| T2 on a hit | Stay at current target, `+incr` weight, `streak = 0` (no climb-back; reset is the only way back to 8) |
| `t2_reset_pct` default | **0.75** (derived by user from rep/1RM table; the `0.7` in legacy `profile.yaml` is stale) |
| Reset-to-default scope | `days_per_week`, `t2_reset_pct`, `t2_fail`, `t3_target`, and the schedule tables. **Excludes** `rounding`, `incr` (weight settings) |

## Data model

New table:

```sql
CREATE TABLE sbs_schedule (
  kind      TEXT NOT NULL,      -- 'main' | 'aux'
  week      INTEGER NOT NULL,   -- 1..21
  intensity REAL NOT NULL,
  reps      INTEGER NOT NULL,
  repout    INTEGER NOT NULL,
  PRIMARY KEY (kind, week)
);
```

`lifts` gains `lift_kind TEXT NULL`.

Program-week mapping (a pure helper, e.g. `schedule_week(program_week) -> int`):
`sched_week = ((program_week - 1) % 21) + 1`. Week 22 wraps to schedule week 1; TM persists.

## Engine changes (`sbs_cli/`)

**`engine/progression.py`** — rewrite `t2_next`:

```
t2_next(state, actual, est1rm, fail=3, incr=2.5, reset_pct=0.75, quantum=2.5):
  if actual is None:                       -> unchanged (skip unlogged)
  LADDER = [8, 6, 4]
  if actual >= state.target:               # HIT
      return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
  # MISS
  new_streak = state.streak + 1
  if new_streak >= fail:                   # Nth consecutive miss -> reset
      return T2State(8, 0, round_weight(est1rm * reset_pct, quantum))
  idx = LADDER.index(state.target)
  next_target = LADDER[min(idx + 1, len(LADDER) - 1)]   # drop one level, floor at 4
  return T2State(next_target, new_streak, state.weight)
```

`t2_fail` retains meaning: it is the number of misses before reset (and thus indirectly the depth
of the cascade that gets traversed: `fail=3` → 8→6→4→reset; `fail=2` → 8→6→reset).

**`program.py`** — `week_plan` and `advance_lift` sbs branches stop reading `lift.intensity /
reps / repout` and instead look up the schedule:

```python
sw = schedule_week(week)                                   # ((week-1)%21)+1
sc = schedule_lookup(lift.lift_kind, sw)                   # (intensity, reps, repout)
# week_plan:
w = round_weight((ls.tm or 0) * sc.intensity, profile.rounding)
PlanItem(..., reps=sc.reps, sets=lift.sets, repout=sc.repout, ...)
# advance_lift (TM auto-regulation unchanged, but uses the scheduled repout):
state.tm = sbs_next(state.tm, sc.repout, actual_reps)
```

`sets` still comes from `lifts.sets` (5 for main, 4 for aux) — unchanged.

`recompute_state` (t2 path) is already history-driven and picks up the new `t2_next` automatically;
no signature change.

The CLI (`sbs_cli/`) reads legacy YAML, not `sbs.db`, and is not the focus of the redesign; the
schedule feature is webapp-only. The pure helpers (`schedule_week`, `schedule_lookup`,
`t2_next`) live in the engine and are reusable, but the CLI is not wired to the schedule table in
this work item.

## Webapp changes (`webapp/`)

- **`routes/plan.py` + `services/preview.py`**: sbs working weight / displayed reps / repout come
  from `sbs_schedule` via `(lift_kind, schedule_week(settings.week))`. Preview (next-week preview
  after a TM edit) uses `schedule_week(settings.week + 1)`.
- **`routes/schedule.py`** (new): `GET /schedule` renders two 21-row tables (main, aux); `POST
  /schedule` saves edits; `POST /schedule/reset` restores default ladders.
- **`routes/settings.py`**: add `POST /settings/<field>/reset` for each non-weight field, restoring
  the default from the defaults module.
- **`defaults.py`** (new): the single source for `DEFAULT_SETTINGS` (`days_per_week=4`,
  `t2_reset_pct=0.75`, `t2_fail=3`, `t3_target=15`) and `DEFAULT_SCHEDULE` (the main/aux 21-week
  ladders below). Used by migration seed and all reset endpoints.

## UI

`/schedule` page:
- Two tables titled **Main** and **Aux**, 21 rows each (week 1–21), columns: intensity, reps,
  repout. Editable inputs, one Save button per table (or one combined Save).
- "Restore default schedule" button → `POST /schedule/reset`.

`/settings` page:
- Each of `days_per_week`, `t2_reset_pct`, `t2_fail`, `t3_target` gets a small "↺ default" button
  next to its input. `rounding` and `incr` do **not** get one.

## Defaults (standard SBS RTF 21-week ladders)

These are the seed values for `sbs_schedule` and the restore-default target. Extracted from the
`Setup` sheet of `SBS RTF filled GZCLP.xlsx`. Weeks 7, 14, 21 are deload weeks.

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
(`rounding` and `incr` are intentionally excluded from reset.)

## Migration (one-shot `migrate_schedule.py`)

Backup `sbs.db` → `backups/sbs-schedule.db.bak`, then:

1. Create `sbs_schedule`; seed the 42 rows from `DEFAULT_SCHEDULE`.
2. `ALTER TABLE lifts ADD COLUMN lift_kind TEXT`.
3. Backfill `lift_kind` for sbs lifts: `sets = 5 → 'main'`, `sets = 4 → 'aux'`.
4. Replay every T2 lift's state with the new `t2_next` via `recompute_state` (history-driven), so
   `target` / `streak` / `weight` reflect 1-strike semantics. (Chin-ups currently `target=8,
   streak=1` under the old 3-strike rule; its logged miss must drop it to `target=6` under the new
   rule — the replay corrects this.)
5. Leave `lifts.intensity / reps / repout` in place (unused after migration).

## Tests

- **`tests/test_progression.py`** (engine):
  - `schedule_week`: 1→1, 21→21, 22→1, 43→1.
  - `schedule_lookup(('main', 1..21))` and `(('aux', 1..21))` return the table above.
  - `t2_next` new rule: HIT stays + `+incr` + streak 0; MISS `@8→6`, `@6→4`; 3rd consecutive MISS
    resets to `8 @ round(est1rm*0.75, q)`; `fail=2` resets after `8→6`; a HIT at `target=6` does
    not climb back to 8.
- **`tests/test_plan_route.py`** (add): at `settings.week = 2`, an sbs main lift renders
  intensity 0.75 / reps 4 / repout 8 from `sbs_schedule`, not from `lifts` static columns.
- **`tests/test_migration.py`** (add): post-migration `sbs_schedule` has 42 rows; every sbs lift
  has a non-null `lift_kind`; a T2 lift with one logged miss reports `target=6`.
- **`tests/test_settings_route.py`** (add): each reset endpoint restores the documented default;
  `rounding` / `incr` have no reset endpoint (404).

## Notes

- `t2_fail` remains a meaningful knob (reset depth), so it keeps its reset-to-default button.
- The T2 portion of `2026-06-28-t2-4x8-cascade-redesign-design.md` is superseded by the 1-strike
  rule here; that doc should be marked superseded when this ships.
- TM rounding fix (ADR 0001) is independent and unaffected — `sbs_next` keeps TM full-precision;
  only the scheduled `repout` feeds the delta.
