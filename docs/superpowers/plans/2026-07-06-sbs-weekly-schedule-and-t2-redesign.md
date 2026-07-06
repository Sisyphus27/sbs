# SBS Weekly Schedule + T2 1-Strike Cascade + Reset-to-Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sbs main/aux lifts follow the real SBS RTF 21-week weekly schedule, rewrite T2 to a 1-strike rep cascade, add cycle-boundary TM reseeding, and add reset-to-default controls for non-weight settings.

**Architecture:** A new `sbs_schedule` table (21 weeks × 2 kinds) becomes the single source for sbs `intensity/reps/repout`. Pure engine helpers (`schedule_week`, `cycle_number`, `lookup_schedule`) read an in-memory schedule carried on `Profile`. The webapp loads the schedule from SQLite into `Profile` and passes it through `advance` / `preview` / `recompute` / `plan view`. T2's `t2_next` is rewritten to drop one rep level per miss. A one-shot migration seeds the schedule, backfills `lift_kind`, and replays T2 state. New `/schedule` and `/reseed` pages plus per-field reset buttons on `/settings`.

**Tech Stack:** Python 3.12, Flask + HTMX, SQLite (stdlib `sqlite3`), Jinja2, pytest. Engine (`sbs_cli/`) is pure; webapp (`webapp/`) is Flask.

## Global Constraints

Copied verbatim from `2026-07-06-sbs-weekly-schedule-and-t2-redesign-design.md` + ADRs:

- **TM accumulates raw, full float precision — never rounded.** Rounding quantum applies ONLY to loaded weights (sbs working weight, T2/T3 increments/resets). (ADR 0001)
- **`rounding` and `incr` are weight settings — excluded from reset-to-default.** Reset targets: `days_per_week=4`, `t2_reset_pct=0.75`, `t2_fail=3`, `t3_target=15`.
- **Schedule = 21 weeks × 2 kinds (`main`, `aux`).** Program-week → schedule-week: `((pw-1) % 21) + 1`. Cycle number: `((pw-1) // 21) + 1`. TM persists across the cycle boundary.
- **T2 ladder is fixed `[8, 6, 4]`.** 1-strike: each miss drops one level; after `t2_fail` consecutive misses, reset to target 8 at `round(est1rm × 0.75, quantum)`. A hit adds `incr` and stays at the current level.
- **Reseed is per-lift, skippable, sbs-only.** At cycle start (`schedule_week(pw)==1 AND pw>1`), a lift is due while `reseeded_cycle < cycle_number(pw)`. Reseed sets `tm = max = newly tested max`; skip stamps `reseeded_cycle` only. (ADR 0002)
- **`lift_kind` is explicit on the lift form for sbs** (`main`/`aux`); the sbs form hides the `intensity/reps/repout` inputs (schedule is the only source).
- All test/run commands use the `sbs` conda env: `conda run -n sbs pytest ...`. Python 3.12.
- Commit style: Conventional Commits. **Never `git add -A`** — stage explicit paths.
- Tests: AAA pattern, descriptive names. Engine tests are pure functions; route tests use the `client`/`app` fixtures from `tests/conftest.py`.

---

## File Structure

**Engine (`sbs_cli/`) — pure, no DB:**
- `sbs_cli/data/schema.py` — add `ScheduleRow` dataclass; add `lift_kind` to `Lift`; add `schedule` to `Profile`.
- `sbs_cli/engine/progression.py` — add `schedule_week`, `cycle_number`, `lookup_schedule`; rewrite `t2_next` (1-strike).
- `sbs_cli/program.py` — `week_plan` / `advance_lift` sbs branches read schedule; `recompute_sbs_tm` gains a `schedule` parameter.
- `sbs_cli/defaults.py` (new) — `DEFAULT_SETTINGS`, `MAIN_LADDER`, `AUX_LADDER`, `DEFAULT_SCHEDULE`.

**Webapp (`webapp/`):**
- `webapp/db.py` — add `sbs_schedule` table, `lifts.lift_kind`, `lift_state.reseeded_cycle`; seed schedule in `init_schema`.
- `webapp/repo.py` — schedule CRUD; `create_lift`/`update_lift` accept `lift_kind`; `save_lift_state` accepts `reseeded_cycle`; reseed helpers.
- `webapp/defaults.py` (new) — re-export from `sbs_cli.defaults` (single source).
- `webapp/services/{advance,preview,recompute}.py` — carry schedule through to the engine.
- `webapp/routes/plan.py` — schedule-driven display + reseed banner.
- `webapp/routes/schedule.py` (new) — `/schedule` editor + reset.
- `webapp/routes/reseed.py` (new) — `/reseed` page + actions.
- `webapp/routes/settings.py` — per-field reset endpoints.
- `webapp/routes/lifts.py` — `lift_kind` in create/edit.
- `webapp/app.py` — register the two new blueprints.
- `webapp/templates/{schedule,reseed}.html` (new); edit `plan.html`, `settings.html`, `_lift_row.html`, `lifts.html`.

**Migration + tests:**
- `migrate_schedule.py` (new) — one-shot.
- `tests/test_schedule.py` (new); edits to `test_progression.py`, `test_program.py`, `test_repo.py`, `test_db.py`, `test_advance_service.py`, `test_preview_service.py`, `test_recompute_service.py`, `test_routes_plan.py`, `test_routes_lifts.py`, `test_routes_settings.py`; new `test_routes_schedule.py`, `test_routes_reseed.py`, `test_migrate_schedule.py`.

---

## Task 1: Engine schedule helpers + data model fields

**Files:**
- Modify: `sbs_cli/data/schema.py`
- Modify: `sbs_cli/engine/progression.py`
- Test: `tests/test_schedule.py` (new)

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `schema.ScheduleRow` — `@dataclass(frozen=True)` with `kind: str`, `week: int`, `intensity: float`, `reps: int`, `repout: int`.
  - `schema.Lift.lift_kind: Optional[str]` (new field, default `None`).
  - `schema.Profile.schedule: list[ScheduleRow]` (new field, default empty list).
  - `progression.schedule_week(program_week: int) -> int`
  - `progression.cycle_number(program_week: int) -> int`
  - `progression.lookup_schedule(schedule, kind: str, program_week: int) -> ScheduleRow` — raises `KeyError` if the `(kind, schedule_week)` row is absent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule.py`:

```python
import pytest
from sbs_cli.data.schema import ScheduleRow, Lift, Profile
from sbs_cli.engine.progression import schedule_week, cycle_number, lookup_schedule


def test_schedule_week_cyclic():
    assert schedule_week(1) == 1
    assert schedule_week(21) == 21
    assert schedule_week(22) == 1
    assert schedule_week(43) == 1
    assert schedule_week(42) == 21


def test_cycle_number():
    assert cycle_number(1) == 1
    assert cycle_number(21) == 1
    assert cycle_number(22) == 2
    assert cycle_number(43) == 3


def test_lookup_schedule_returns_row_for_current_schedule_week():
    sched = [ScheduleRow("main", 1, 0.70, 5, 10), ScheduleRow("main", 2, 0.75, 4, 8)]
    # program week 2 -> schedule week 2
    assert lookup_schedule(sched, "main", 2) == ScheduleRow("main", 2, 0.75, 4, 8)


def test_lookup_schedule_wraps_after_21():
    sched = [ScheduleRow("aux", 1, 0.60, 7, 14)]  # only week 1 present
    # program week 22 -> schedule week 1
    assert lookup_schedule(sched, "aux", 22).repout == 14


def test_lookup_schedule_missing_row_raises():
    sched = [ScheduleRow("main", 1, 0.70, 5, 10)]
    with pytest.raises(KeyError):
        lookup_schedule(sched, "main", 2)  # schedule week 2 absent


def test_lift_and_profile_carry_new_fields():
    l = Lift(name="Squat", tier="sbs", day=1, lift_kind="main")
    assert l.lift_kind == "main"
    p = Profile(schedule=[ScheduleRow("main", 1, 0.70, 5, 10)])
    assert len(p.schedule) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_schedule.py -v`
Expected: FAIL — `ImportError: cannot import name 'ScheduleRow'` (and the functions do not exist).

- [ ] **Step 3: Add the dataclass fields**

In `sbs_cli/data/schema.py`, add the `ScheduleRow` dataclass after the imports and extend `Lift` and `Profile`:

```python
@dataclass(frozen=True)
class ScheduleRow:
    kind: str            # "main" | "aux"
    week: int            # 1..21
    intensity: float
    reps: int
    repout: int
```

Add to `Lift` (after `start`):
```python
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None for t2/t3
```

Add to `Profile` (after `lifts`):
```python
    schedule: List[ScheduleRow] = field(default_factory=list)
```
(`List` is already imported.)

- [ ] **Step 4: Add the pure helpers**

Append to `sbs_cli/engine/progression.py`:

```python
def schedule_week(program_week: int) -> int:
    """Cyclic 1..21 schedule-row index for an absolute program week."""
    return ((program_week - 1) % 21) + 1


def cycle_number(program_week: int) -> int:
    """Which 21-week cycle a program week falls in (1-based)."""
    return ((program_week - 1) // 21) + 1


def lookup_schedule(schedule, kind: str, program_week: int):
    """Return the ScheduleRow for (kind, schedule_week(program_week)).

    Raises KeyError if that row is not present in `schedule`.
    """
    sw = schedule_week(program_week)
    for row in schedule:
        if row.kind == kind and row.week == sw:
            return row
    raise KeyError(f"no schedule row for kind={kind!r} week={sw}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_schedule.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add sbs_cli/data/schema.py sbs_cli/engine/progression.py tests/test_schedule.py
git commit -m "feat(engine): schedule helpers + ScheduleRow/Lift.lift_kind/Profile.schedule"
```

---

## Task 2: defaults module (settings + 21-week ladders)

**Files:**
- Create: `sbs_cli/defaults.py`
- Test: `tests/test_defaults.py` (new)

**Interfaces:**
- Consumes: `schema.ScheduleRow` (Task 1).
- Produces:
  - `defaults.DEFAULT_SETTINGS: dict` — `{"days_per_week": 4, "t2_reset_pct": 0.75, "t2_fail": 3, "t3_target": 15}` (NO `rounding`/`incr`).
  - `defaults.MAIN_LADDER: list[tuple]` and `defaults.AUX_LADDER: list[tuple]` — 21 `(week, intensity, reps, repout)` tuples each.
  - `defaults.DEFAULT_SCHEDULE: list[ScheduleRow]` — 42 rows built from the two ladders.
  - `defaults.RESETTABLE_FIELDS: tuple` — `("days_per_week", "t2_reset_pct", "t2_fail", "t3_target")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_defaults.py`:

```python
from sbs_cli.defaults import (DEFAULT_SETTINGS, MAIN_LADDER, AUX_LADDER,
                              DEFAULT_SCHEDULE, RESETTABLE_FIELDS)


def test_default_settings_exclude_weight_params():
    assert DEFAULT_SETTINGS == {"days_per_week": 4, "t2_reset_pct": 0.75,
                                 "t2_fail": 3, "t3_target": 15}
    assert "rounding" not in DEFAULT_SETTINGS
    assert "incr" not in DEFAULT_SETTINGS


def test_resettable_fields_match():
    assert RESETTABLE_FIELDS == ("days_per_week", "t2_reset_pct", "t2_fail", "t3_target")


def test_ladders_have_21_weeks():
    assert len(MAIN_LADDER) == 21
    assert len(AUX_LADDER) == 21
    assert [w for w, *_ in MAIN_LADDER] == list(range(1, 22))
    assert [w for w, *_ in AUX_LADDER] == list(range(1, 22))


def test_main_week1_and_deloads():
    # (week, intensity, reps, repout)
    assert MAIN_LADDER[0] == (1, 0.70, 5, 10)
    assert MAIN_LADDER[1] == (2, 0.75, 4, 8)
    assert MAIN_LADDER[6] == (7, 0.60, 7, 14)   # deload
    assert MAIN_LADDER[20] == (21, 0.60, 7, 14)  # deload


def test_aux_week1_and_deloads():
    assert AUX_LADDER[0] == (1, 0.60, 7, 14)
    assert AUX_LADDER[1] == (2, 0.65, 6, 12)
    assert AUX_LADDER[6] == (7, 0.50, 8, 18)    # deload


def test_default_schedule_is_42_rows():
    assert len(DEFAULT_SCHEDULE) == 42
    kinds = {r.kind for r in DEFAULT_SCHEDULE}
    assert kinds == {"main", "aux"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_defaults.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sbs_cli.defaults'`.

- [ ] **Step 3: Write the module**

Create `sbs_cli/defaults.py`:

```python
"""Single source for reset-to-default settings + the standard SBS RTF 21-week ladders.

Ladders extracted from the `Setup` sheet of `SBS RTF filled GZCLP.xlsx`. Weeks 7/14/21
are deload weeks. Each tuple is (week, intensity, reps, repout).
"""
from .data.schema import ScheduleRow

# Excluded: rounding, incr (weight settings).
DEFAULT_SETTINGS = {
    "days_per_week": 4,
    "t2_reset_pct": 0.75,
    "t2_fail": 3,
    "t3_target": 15,
}
RESETTABLE_FIELDS = ("days_per_week", "t2_reset_pct", "t2_fail", "t3_target")

MAIN_LADDER = [
    (1, 0.70, 5, 10), (2, 0.75, 4, 8), (3, 0.80, 3, 6), (4, 0.725, 5, 9), (5, 0.775, 4, 7),
    (6, 0.825, 3, 5), (7, 0.60, 7, 14), (8, 0.75, 4, 8), (9, 0.80, 3, 6), (10, 0.85, 2, 4),
    (11, 0.775, 4, 7), (12, 0.825, 3, 5), (13, 0.875, 2, 3), (14, 0.60, 7, 14),
    (15, 0.80, 3, 6), (16, 0.85, 2, 4), (17, 0.90, 1, 2), (18, 0.85, 2, 4),
    (19, 0.90, 1, 2), (20, 0.95, 1, 1), (21, 0.60, 7, 14),
]

AUX_LADDER = [
    (1, 0.60, 7, 14), (2, 0.65, 6, 12), (3, 0.70, 5, 10), (4, 0.625, 7, 13),
    (5, 0.675, 6, 11), (6, 0.725, 5, 9), (7, 0.50, 8, 18), (8, 0.65, 6, 12),
    (9, 0.70, 5, 10), (10, 0.75, 4, 8), (11, 0.675, 6, 11), (12, 0.725, 5, 9),
    (13, 0.775, 4, 7), (14, 0.50, 8, 18), (15, 0.70, 5, 10), (16, 0.75, 4, 8),
    (17, 0.80, 3, 6), (18, 0.75, 4, 8), (19, 0.80, 3, 6), (20, 0.85, 2, 4),
    (21, 0.50, 8, 18),
]


def _rows(kind, ladder):
    return [ScheduleRow(kind=kind, week=w, intensity=i, reps=r, repout=ro)
            for (w, i, r, ro) in ladder]


DEFAULT_SCHEDULE = _rows("main", MAIN_LADDER) + _rows("aux", AUX_LADDER)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_defaults.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/defaults.py tests/test_defaults.py
git commit -m "feat: defaults module — reset settings + main/aux 21-week ladders"
```

---

## Task 3: T2 1-strike cascade rewrite

**Files:**
- Modify: `sbs_cli/engine/progression.py` (`t2_next`)
- Test: `tests/test_progression.py` (rewrite the T2 cases)

**Interfaces:**
- Consumes: `T2State` (unchanged signature).
- Produces: `t2_next(state, actual, est1rm, fail=3, incr=2.5, reset_pct=0.75, quantum=2.5) -> T2State` with 1-strike semantics (same call signature, different behavior).

- [ ] **Step 1: Rewrite the T2 tests**

In `tests/test_progression.py`, replace every test in the `# --- T2 ...` section (from `test_t2_hit_adds_weight_keeps_tier` through the end of the T2 block) with:

```python
# --- T2 (1-strike cascade: 8 -> 6 -> 4, reset after `fail` misses @75% est1rm) ---
def test_t2_hit_adds_weight_stays_at_target():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=52.5)


def test_t2_miss_at_8_drops_to_6_same_weight():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=1, weight=50)


def test_t2_miss_at_6_drops_to_4_same_weight():
    s = t2_next(T2State(target=6, streak=1, weight=50), actual=5, est1rm=100)
    assert s == T2State(target=4, streak=2, weight=50)


def test_t2_third_miss_resets_to_8_at_est1rm_pct():
    # streak 2 -> +1 = 3 >= fail(3) -> reset: target 8, weight round(100*0.75, 2.5)=75
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=75.0)


def test_t2_fail_2_resets_after_two_misses():
    # fail=2: miss @8 -> streak1 (<2) drop to 6; miss @6 -> streak2 (>=2) reset
    s1 = t2_next(T2State(target=8, streak=0, weight=50), actual=6, est1rm=100, fail=2)
    assert s1 == T2State(target=6, streak=1, weight=50)
    s2 = t2_next(s1, actual=5, est1rm=100, fail=2)
    assert s2 == T2State(target=8, streak=0, weight=75.0)


def test_t2_hit_at_6_does_not_climb_back_to_8():
    s = t2_next(T2State(target=6, streak=1, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=0, weight=52.5)


def test_t2_miss_at_4_under_fail_floor_keeps_target():
    # at bottom (4), streak not yet at fail -> stay 4, streak increments
    s = t2_next(T2State(target=4, streak=1, weight=50), actual=3, est1rm=100, fail=4)
    assert s == T2State(target=4, streak=2, weight=50)


def test_t2_no_log_unchanged():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=None, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=50)
```

- [ ] **Step 2: Run T2 tests to verify they fail**

Run: `conda run -n sbs pytest tests/test_progression.py -k t2 -v`
Expected: FAIL — old `t2_next` still has 3-strike behavior.

- [ ] **Step 3: Rewrite `t2_next`**

In `sbs_cli/engine/progression.py`, replace the existing `t2_next` function body with:

```python
def t2_next(state: T2State, actual, est1rm: float, fail: int = 3,
            incr: float = 2.5, reset_pct: float = 0.75, quantum: float = 2.5) -> T2State:
    """T2 1-strike cascade: each miss drops one rep level (8 -> 6 -> 4); after `fail`
    consecutive misses, reset to target 8 at round(est1rm * reset_pct, quantum).
    A hit adds `incr` and stays at the current level (no climb-back)."""
    if actual is None:
        return state
    if actual >= state.target:                                   # HIT
        return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
    new_streak = state.streak + 1                                # MISS
    if new_streak >= fail:                                       # Nth consecutive miss -> reset
        return T2State(8, 0, round_weight(est1rm * reset_pct, quantum))
    ladder = [8, 6, 4]
    idx = ladder.index(state.target) if state.target in ladder else 0
    next_target = ladder[min(idx + 1, len(ladder) - 1)]          # drop one level, floor at 4
    return T2State(next_target, new_streak, state.weight)
```

- [ ] **Step 4: Run T2 tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_progression.py -k t2 -v`
Expected: PASS (8 T2 tests).

- [ ] **Step 5: Run the full progression suite to confirm nothing else regressed**

Run: `conda run -n sbs pytest tests/test_progression.py -v`
Expected: PASS (round/sbs/t3/t2 cases; the 3-strike cases are gone, replaced by the 1-strike set).

- [ ] **Step 6: Commit**

```bash
git add sbs_cli/engine/progression.py tests/test_progression.py
git commit -m "feat(t2): 1-strike cascade — miss drops one level, reset after t2_fail misses"
```

---

## Task 4: Engine reads schedule in week_plan / advance_lift / recompute_sbs_tm

**Files:**
- Modify: `sbs_cli/program.py`
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: `progression.lookup_schedule` (Task 1); `Lift.lift_kind`, `Profile.schedule` (Task 1).
- Produces:
  - `week_plan(profile, state, day)` — sbs branch reads `(intensity, reps, repout)` from `lookup_schedule(profile.schedule, lift.lift_kind, state.week)`.
  - `advance_lift(profile, lift, state, actual_reps, week)` — sbs TM autoreg uses the scheduled repout.
  - `recompute_sbs_tm(lift, history, schedule) -> float` — **signature change**: third arg is the schedule list; replays using each history row's scheduled repout.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_program.py` (keep existing tests; add these). The tests build a `Profile` carrying a small schedule:

```python
from sbs_cli.data.schema import Lift, LiftState, Profile, ProgramState, SetEntry, ScheduleRow
from sbs_cli.program import week_plan, advance_lift, recompute_sbs_tm


def _profile_with_schedule():
    sched = [ScheduleRow("main", w, i, r, ro) for (w, i, r, ro) in
             [(1, 0.70, 5, 10), (2, 0.75, 4, 8), (3, 0.80, 3, 6)]]
    lifts = [Lift(name="Squat", tier="sbs", day=1, max=100.0, sets=5, lift_kind="main")]
    return Profile(rounding=2.5, lifts=lifts, schedule=sched)


def test_week_plan_uses_scheduled_intensity_reps_repout_at_week_2():
    p = _profile_with_schedule()
    st = ProgramState(week=2, lifts={"Squat": LiftState(name="Squat", tier="sbs", tm=100.0)})
    items = week_plan(p, st, day=1)
    squat = items[0]
    # week 2 schedule: 0.75 / 4 / 8 ; weight = MROUND(100*0.75, 2.5) = 75.0
    assert squat.weight == 75.0
    assert squat.reps == 4
    assert squat.repout == 8
    assert squat.sets == 5


def test_advance_lift_uses_scheduled_repout_for_tm_delta():
    p = _profile_with_schedule()
    lift = p.lift("Squat")
    st = LiftState(name="Squat", tier="sbs", tm=100.0)
    # week 2 scheduled repout = 8; actual 11 -> beat by 3 -> +1.5% -> 101.5
    advance_lift(p, lift, st, actual_reps=11, week=2)
    assert st.tm == 101.5


def test_recompute_sbs_tm_uses_schedule_repout_per_week():
    p = _profile_with_schedule()
    lift = p.lift("Squat")
    hist = [SetEntry(week=1, weight=70.0, reps=12),   # W1 repout 10 -> beat by 2 -> +1% -> 101.0
            SetEntry(week=2, weight=75.0, reps=10)]   # W2 repout 8 -> beat by 2 -> +1% -> 102.01
    tm = recompute_sbs_tm(lift, hist, p.schedule)
    assert tm == round(100.0 * 1.01 * 1.01, 10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n sbs pytest tests/test_program.py -k "week_plan_uses_scheduled or advance_lift_uses_scheduled or recompute_sbs_tm_uses_schedule" -v`
Expected: FAIL — current code reads `lift.intensity / reps / repout` and `recompute_sbs_tm` has a 2-arg signature.

- [ ] **Step 3: Update `week_plan` sbs branch**

In `sbs_cli/program.py`, replace the sbs branch inside `week_plan` (the `if l.tier == "sbs":` block) with:

```python
        if l.tier == "sbs":
            sc = lookup_schedule(profile.schedule, l.lift_kind, state.week)
            w = round_weight((ls.tm or 0) * sc.intensity, profile.rounding)
            out.append(PlanItem(l.name, "sbs", w, sc.reps, l.sets, sc.repout, None, 0, ls.est1rm))
```

Add `lookup_schedule` to the import line at the top of `program.py`:
```python
from .engine.progression import sbs_next, t3_next, t2_next, T2State, round_weight, lookup_schedule
```

- [ ] **Step 4: Update `advance_lift` sbs branch**

In `advance_lift`, compute the schedule row once and use it for both the working weight and the TM repout. Replace the body from the working-weight line through the end of the `if lift.tier == "sbs":` progression block with:

```python
    # working weight this week (before progression)
    if lift.tier == "sbs":
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, sc.repout, actual_reps)
    elif lift.tier == "t3":
        state.weight = t3_next(state.weight, actual_reps,
                               target=profile.t3_target, incr=profile.incr, quantum=profile.rounding)
    elif lift.tier == "t2":
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                     fail=profile.t2_fail, incr=profile.incr,
                     reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight
```

- [ ] **Step 5: Update `recompute_sbs_tm` signature + body**

Replace the existing `recompute_sbs_tm` with:

```python
def recompute_sbs_tm(lift: Lift, history: List[SetEntry], schedule) -> float:
    """Replay an sbs lift's TM from ``lift.max`` over its history (raw, no rounding),
    using each week's SCHEDULED repout as the rep-out target. ``schedule`` is the list
    of ScheduleRow passed from the caller (webapp loads it from sbs_schedule).
    History rows are immutable facts; only their reps + the scheduled repout drive the
    replay. See ADR 0001 (TM raw) and the schedule spec (Q6: current-schedule replay)."""
    from .engine.progression import lookup_schedule
    tm = lift.max
    for h in sorted(history, key=lambda x: x.week):
        sc = lookup_schedule(schedule, lift.lift_kind, h.week)
        tm = sbs_next(tm, sc.repout, h.reps)
    return tm
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_program.py -k "week_plan_uses_scheduled or advance_lift_uses_scheduled or recompute_sbs_tm_uses_schedule" -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the full program suite**

Run: `conda run -n sbs pytest tests/test_program.py -v`
Expected: PASS. (If older tests in this file build sbs lifts without `lift_kind` or without a schedule, update them to include `lift_kind="main"` and a `schedule=[...]` on the Profile — these are pre-schedule tests now obsolete; rewrite them to the new model rather than delete.)

- [ ] **Step 8: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "feat(engine): week_plan/advance/recompute read intensity+repout from schedule"
```

---

## Task 5: DB schema + repo for schedule, lift_kind, reseeded_cycle

**Files:**
- Modify: `webapp/db.py`
- Modify: `webapp/repo.py`
- Test: `tests/test_db.py`, `tests/test_repo.py`
- Also: update existing sbs-lift test fixtures repo-wide (see Step 6).

**Interfaces:**
- Consumes: `sbs_cli.defaults.DEFAULT_SCHEDULE` (Task 2).
- Produces:
  - `db.init_schema` creates `sbs_schedule`, `lifts.lift_kind`, `lift_state.reseeded_cycle`, and seeds the schedule when empty.
  - `repo.get_schedule(conn) -> list[sqlite3.Row]`
  - `repo.replace_schedule(conn, rows)` — wipe + insert (used by /schedule save + reset).
  - `repo.reset_schedule(conn)` — replace with `DEFAULT_SCHEDULE`.
  - `repo.create_lift` / `update_lift` accept `lift_kind`.
  - `repo.save_lift_state` accepts `reseeded_cycle` (default 0).
  - `repo.set_reseed(conn, lift_id, *, new_max=None, cycle)` — writes `reseeded_cycle`; if `new_max` given, also sets `lifts.max` and `lift_state.tm`.

- [ ] **Step 1: Write the failing repo/db tests**

Append to `tests/test_repo.py`:

```python
from sbs_cli.defaults import DEFAULT_SCHEDULE


def test_init_schema_seeds_schedule(app, ):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        rows = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
        assert rows == 42


def test_get_and_replace_schedule(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        from webapp import repo
        assert len(repo.get_schedule(conn)) == 42
        # replace with a single edited row
        repo.replace_schedule(conn, [("main", 1, 0.71, 5, 10)])
        got = repo.get_schedule(conn)
        assert len(got) == 1 and got[0]["intensity"] == 0.71


def test_reset_schedule_restores_defaults(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        from webapp import repo
        repo.replace_schedule(conn, [("main", 1, 0.99, 1, 1)])
        repo.reset_schedule(conn)
        assert len(repo.get_schedule(conn)) == 42


def test_create_lift_accepts_lift_kind(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        from webapp import repo
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        assert repo.get_lift(conn, lid)["lift_kind"] == "main"


def test_set_reseed_writes_max_tm_and_cycle(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        from webapp import repo
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_reseed(conn, lid, new_max=120.0, cycle=2)
        assert repo.get_lift(conn, lid)["max"] == 120.0
        st = repo.get_lift_state(conn, lid)
        assert st["tm"] == 120.0
        assert st["reseeded_cycle"] == 2


def test_set_reseed_skip_keeps_tm_advances_cycle(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        from webapp import repo
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_reseed(conn, lid, cycle=2)  # no new_max -> skip
        st = repo.get_lift_state(conn, lid)
        assert st["tm"] == 100.0            # unchanged
        assert st["reseeded_cycle"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n sbs pytest tests/test_repo.py -v`
Expected: FAIL — `sbs_schedule` table absent; `create_lift` does not accept `lift_kind`.

- [ ] **Step 3: Extend the DB schema + seed**

In `webapp/db.py`, add to `_SCHEMA` (after the `week_log` table):

```sql
CREATE TABLE IF NOT EXISTS sbs_schedule (
    kind      TEXT NOT NULL,
    week      INTEGER NOT NULL,
    intensity REAL NOT NULL,
    reps      INTEGER NOT NULL,
    repout    INTEGER NOT NULL,
    PRIMARY KEY (kind, week)
);
```

Add `lift_kind TEXT` to the `lifts` table definition (after `start REAL`) and `reseeded_cycle INTEGER NOT NULL DEFAULT 0` to `lift_state` (after `est1rm REAL`).

Add a seeding step inside `init_schema`, after the settings seed block:

```python
    from sbs_cli.defaults import DEFAULT_SCHEDULE
    if conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r.kind, r.week, r.intensity, r.reps, r.repout) for r in DEFAULT_SCHEDULE],
        )
    conn.commit()
```

(Note: `init_schema` runs `CREATE TABLE IF NOT EXISTS`, so adding columns to an existing `sbs.db` does NOT migrate it — the one-shot `migrate_schedule.py` in Task 7 handles the live DB via `ALTER TABLE`. `init_schema` only bootstraps fresh DBs, including test fixtures.)

- [ ] **Step 4: Extend `repo.py`**

Add `lift_kind` to the lifts column list and the create/insert path:

```python
_LIFT_COLS = ("name", "tier", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start", "lift_kind")
```

Change `create_lift` to accept `lift_kind=None` and include it in the INSERT (add `lift_kind` to both the column list and values). Change `update_lift` to use the new `_LIFT_COLS` (it already validates against `_LIFT_COLS`, so `lift_kind` becomes settable automatically).

Add `reseeded_cycle` handling: change `save_lift_state` to accept `reseeded_cycle: int = 0` and include it in both the INSERT column list and the `ON CONFLICT` update. (`_STATE_COLS` is informational; update it too: `("tier", "tm", "weight", "target", "streak", "est1rm", "reseeded_cycle")`.)

Add the schedule + reseed functions at the bottom of `repo.py`:

```python
# ---------- schedule ----------
def get_schedule(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT * FROM sbs_schedule ORDER BY kind, week"
    ).fetchall()


def replace_schedule(conn: sqlite3.Connection, rows) -> None:
    """Wipe + insert. `rows` is an iterable of (kind, week, intensity, reps, repout)."""
    conn.execute("DELETE FROM sbs_schedule")
    conn.executemany(
        "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
        "VALUES (?, ?, ?, ?, ?)",
        list(rows),
    )
    conn.commit()


def reset_schedule(conn: sqlite3.Connection) -> None:
    from sbs_cli.defaults import DEFAULT_SCHEDULE
    replace_schedule(conn, [(r.kind, r.week, r.intensity, r.reps, r.repout)
                            for r in DEFAULT_SCHEDULE])


# ---------- reseed ----------
def set_reseed(conn: sqlite3.Connection, lift_id: int, *, cycle: int, new_max=None) -> None:
    """Stamp reseeded_cycle; if new_max given, also set lifts.max and lift_state.tm."""
    conn.execute(
        "UPDATE lift_state SET reseeded_cycle = ? WHERE lift_id = ?", (cycle, lift_id))
    if new_max is not None:
        conn.execute("UPDATE lifts SET max = ? WHERE id = ?", (new_max, lift_id))
        conn.execute("UPDATE lift_state SET tm = ? WHERE lift_id = ?", (new_max, lift_id))
    conn.commit()
```

- [ ] **Step 5: Run repo tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_repo.py -v`
Expected: PASS (existing + 6 new).

- [ ] **Step 6: Update existing sbs-lift test fixtures repo-wide**

Existing tests create sbs lifts without `lift_kind` and without a populated schedule context. They now break because the plan view / advance look up `lift_kind`. Find and fix them:

Run: `grep -rn "tier=\"sbs\"" tests/` and `grep -rn "tier='sbs'" tests/`

For every `repo.create_lift(... tier="sbs" ...)` call site in `tests/`, add `lift_kind="main"` (use `"aux"` if the lift is a variation like Front Squat). Files to check: `test_routes_plan.py`, `test_routes_lifts.py`, `test_advance_service.py`, `test_preview_service.py`, `test_recompute_service.py`, `test_tier_service.py`, `test_columns.py`, `test_db.py`. Then re-run:

Run: `conda run -n sbs pytest tests/ -v`
Expected: PASS (all tests). If a service test asserts week-1 static intensity values, update it to the schedule-driven values from `DEFAULT_SCHEDULE`.

- [ ] **Step 7: Commit**

```bash
git add webapp/db.py webapp/repo.py tests/test_repo.py tests/test_db.py tests/
git commit -m "feat(db): sbs_schedule table, lift_kind, reseeded_cycle + schedule/reseed repo"
```
(Stage the specific test files you edited; do not `git add -A`.)

---

## Task 6: Wire schedule through advance / preview / recompute / plan view

**Files:**
- Modify: `webapp/services/advance.py`
- Modify: `webapp/services/preview.py`
- Modify: `webapp/services/recompute.py`
- Modify: `webapp/routes/plan.py` (the `_by_day` display path)
- Test: `tests/test_advance_service.py`, `tests/test_preview_service.py`, `tests/test_recompute_service.py`, `tests/test_routes_plan.py`

**Interfaces:**
- Consumes: `repo.get_schedule` (Task 5); engine schedule helpers (Tasks 1, 4).
- Produces: all sbs read paths derive `intensity/reps/repout` from the loaded schedule; `advance_week` builds a `Profile` that carries the schedule.

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_routes_plan.py`:

```python
def test_plan_view_shows_week2_schedule_values(client, app):
    """At week 2, an sbs main lift renders intensity->weight for W2 (75%), reps 4, repout 8."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_week(conn, 2)
        # week 2 main schedule: 0.75/4/8 ; weight MROUND(100*0.75,2.5)=75.0
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert "75.0 kg" in html
    assert "x 4 x 5" in html          # reps 4 x sets 5
    assert "rep-out 8" in html or "repout 8" in html.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_plan.py::test_plan_view_shows_week2_schedule_values -v`
Expected: FAIL — `_by_day` still reads `r["intensity"] / r["reps"] / r["repout"]`.

- [ ] **Step 3: Carry the schedule through `advance.py`**

In `webapp/services/advance.py`, build the schedule on the `Profile`. Modify `_profile_from_rows` to accept and attach it, and `_lift_from_row` to read `lift_kind`:

```python
def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"],
    )


def _profile_from_rows(settings, lift_rows, schedule_rows) -> Profile:
    from sbs_cli.data.schema import ScheduleRow
    schedule = [ScheduleRow(kind=sr["kind"], week=sr["week"], intensity=sr["intensity"],
                            reps=sr["reps"], repout=sr["repout"]) for sr in schedule_rows]
    return Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
        lifts=[_lift_from_row(r) for r in lift_rows],
        schedule=schedule,
    )
```

In `advance_week`, load the schedule and pass it through:

```python
    profile = _profile_from_rows(settings, lift_rows, repo.get_schedule(conn))
```

(`advance_lift(profile, lift, ls, actual, week=week)` now finds the schedule via `profile.schedule`.)

- [ ] **Step 4: Update `preview.py`**

In `webapp/services/preview.py`, replace any `(state["tm"] or 0) * lift["intensity"]` with a schedule lookup. Load settings + schedule and compute the working weight for the current program week:

```python
from sbs_cli.engine.progression import round_weight, lookup_schedule
from sbs_cli.data.schema import ScheduleRow

def _schedule(conn):
    return [ScheduleRow(kind=r["kind"], week=r["week"], intensity=r["intensity"],
                        reps=r["reps"], repout=r["repout"]) for r in repo.get_schedule(conn)]

# inside live_preview(conn, lid, reps):
    settings = repo.get_settings(conn)
    week = settings["week"]
    sc = lookup_schedule(_schedule(conn), lift["lift_kind"], week)
    w = round_weight((state["tm"] or 0) * sc.intensity, settings["rounding"])
    # ... rest of est1RM math unchanged, using w
```

(Keep the existing est1RM/`delta` logic; only the working-weight source changes.)

- [ ] **Step 5: Update `recompute.py`**

In `webapp/services/recompute.py`, pass the schedule into `recompute_sbs_tm`:

```python
    from sbs_cli.data.schema import ScheduleRow
    schedule = [ScheduleRow(kind=r["kind"], week=r["week"], intensity=r["intensity"],
                            reps=r["reps"], repout=r["repout"]) for r in repo.get_schedule(conn)]
    tm = recompute_sbs_tm(lift, history, schedule)
```

(Update the import line and the existing call site, which previously passed only `(lift, history)`.)

- [ ] **Step 6: Update the plan view `_by_day`**

In `webapp/routes/plan.py::_by_day`, replace the sbs branch's static `r["intensity"] / r["reps"] / r["repout"]` with a schedule lookup. Add near the top of the function:

```python
    from sbs_cli.engine.progression import lookup_schedule
    from sbs_cli.data.schema import ScheduleRow
    schedule = [ScheduleRow(kind=r["kind"], week=r["week"], intensity=r["intensity"],
                            reps=r["reps"], repout=r["repout"]) for r in repo.get_schedule(conn)]
```

Then the sbs branch:

```python
        if r["tier"] == "sbs":
            sc = lookup_schedule(schedule, r["lift_kind"], settings["week"])
            w = round_weight((st["tm"] or 0) * sc.intensity, settings["rounding"])
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="sbs", weight=w,
                                   reps=sc.reps, sets=r["sets"], repout=sc.repout,
                                   target=None, streak=0, est1rm=est1rm)
```

- [ ] **Step 7: Run the new + service tests**

Run: `conda run -n sbs pytest tests/test_routes_plan.py tests/test_advance_service.py tests/test_preview_service.py tests/test_recompute_service.py -v`
Expected: PASS. Update assertions in these files that hard-coded week-1 static intensity to the schedule-driven values where needed.

- [ ] **Step 8: Commit**

```bash
git add webapp/services/advance.py webapp/services/preview.py webapp/services/recompute.py webapp/routes/plan.py tests/
git commit -m "feat(webapp): carry schedule through advance/preview/recompute/plan display"
```

---

## Task 7: One-shot migration script

**Files:**
- Create: `migrate_schedule.py`
- Test: `tests/test_migrate_schedule.py` (new)

**Interfaces:**
- Consumes: `db.connect`, `repo`, `sbs_cli.defaults.DEFAULT_SCHEDULE`, `recompute_state` (engine, already history-driven).
- Produces: idempotent script that upgrades a live `sbs.db` to the new schema + replays T2 state.

- [ ] **Step 1: Write the failing migration test**

Create `tests/test_migrate_schedule.py`:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_legacy_db(path):
    """A pre-migration DB: lifts/lift_state with NO lift_kind, NO reseeded_cycle, NO schedule."""
    import sqlite3
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    # minimal legacy schema (pre-migration)
    c.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id=1), week INTEGER, days_per_week INTEGER,
            rounding REAL, incr REAL, t2_reset_pct REAL, t2_fail INTEGER, t3_target INTEGER);
        CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, tier TEXT, day INTEGER,
            sort_order INTEGER, sets INTEGER, max REAL, intensity REAL, reps INTEGER, repout INTEGER, start REAL);
        CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT, tm REAL, weight REAL,
            target INTEGER, streak INTEGER, est1rm REAL);
        CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INTEGER, week INTEGER,
            weight REAL, reps INTEGER, ts TEXT);
        CREATE TABLE week_log (lift_id INTEGER, week INTEGER, reps INTEGER, PRIMARY KEY (lift_id, week));
        INSERT INTO settings VALUES (1, 2, 4, 2.5, 2.5, 0.75, 3, 15);
    """)
    # a main sbs lift (sets 5) and a t2 lift with one logged miss
    c.execute("INSERT INTO lifts (name,tier,day,sort_order,sets,max,intensity,reps,repout,start) "
              "VALUES ('Squat','sbs',1,0,5,135.0,0.7,5,10,NULL)")
    squat_id = c.execute("SELECT id FROM lifts WHERE name='Squat'").fetchone()["id"]
    c.execute("INSERT INTO lift_state (lift_id,tier,tm) VALUES (?, 'sbs', 135.0)", (squat_id,))
    c.execute("INSERT INTO lifts (name,tier,day,sort_order,sets,start) "
              "VALUES ('Chin-ups','t2',4,0,3,0.0)")
    chin_id = c.execute("SELECT id FROM lifts WHERE name='Chin-ups'").fetchone()["id"]
    c.execute("INSERT INTO lift_state (lift_id,tier,weight,target,streak,est1rm) "
              "VALUES (?, 't2', 0.0, 8, 1, 0.0)", (chin_id,))
    c.execute("INSERT INTO history (lift_id,week,weight,reps,ts) VALUES (?, 1, 0.0, 6, 't')",
              (chin_id,))
    c.commit()
    c.close()


def test_migration_creates_schedule_backfills_kind_replays_t2(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    _build_legacy_db(db_path)
    import migrate_schedule
    migrate_schedule.run(db_path, backup_dir=str(tmp_path / "bak"))

    import sqlite3
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    assert c.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 42
    squat = c.execute("SELECT lift_kind FROM lifts WHERE name='Squat'").fetchone()
    assert squat["lift_kind"] == "main"
    chin = c.execute("SELECT target, streak FROM lift_state "
                     "WHERE lift_id=(SELECT id FROM lifts WHERE name='Chin-ups')").fetchone()
    # the one logged miss -> under 1-strike, target must have dropped 8 -> 6
    assert chin["target"] == 6
    assert chin["streak"] == 1
    # backup created
    assert any(p.startswith("sbs-schedule") for p in os.listdir(str(tmp_path / "bak")))
    c.close()


def test_migration_is_idempotent(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    _build_legacy_db(db_path)
    import migrate_schedule
    migrate_schedule.run(db_path, backup_dir=str(tmp_path / "bak"))
    migrate_schedule.run(db_path, backup_dir=str(tmp_path / "bak"))  # second run: no error
    import sqlite3
    c = sqlite3.connect(db_path)
    assert c.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 42
    c.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n sbs pytest tests/test_migrate_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_schedule'`.

- [ ] **Step 3: Write the migration script**

Create `migrate_schedule.py`:

```python
"""One-shot: upgrade sbs.db to the weekly-schedule schema + replay T2 under the 1-strike rule.

Idempotent. Backs up to <backup_dir>/sbs-schedule-<ts>.db.bak first.
"""
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sbs_cli.defaults import DEFAULT_SCHEDULE  # noqa: E402
from sbs_cli.data.schema import ScheduleRow      # noqa: E402


def _add_column(conn, table, col, decl):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _create_schedule_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sbs_schedule ("
        "kind TEXT NOT NULL, week INTEGER NOT NULL, intensity REAL NOT NULL, "
        "reps INTEGER NOT NULL, repout INTEGER NOT NULL, PRIMARY KEY (kind, week))"
    )


def _seed_schedule_if_empty(conn):
    if conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) VALUES (?, ?, ?, ?, ?)",
            [(r.kind, r.week, r.intensity, r.reps, r.repout) for r in DEFAULT_SCHEDULE],
        )


def _backfill_lift_kind(conn):
    """sets=5 -> main, sets=4 -> aux, for sbs lifts only."""
    conn.execute(
        "UPDATE lifts SET lift_kind = CASE "
        "WHEN sets = 5 THEN 'main' WHEN sets = 4 THEN 'aux' ELSE lift_kind END "
        "WHERE tier = 'sbs' AND lift_kind IS NULL"
    )


def _replay_t2(conn, profile_globals):
    """Recompute every t2 lift's target/streak/weight by replaying its history."""
    from sbs_cli.program import recompute_state
    from sbs_cli.data.schema import Lift
    rows = conn.execute("SELECT * FROM lifts WHERE tier = 't2'").fetchall()
    for r in rows:
        lid = r["id"]
        hist_rows = conn.execute(
            "SELECT week, weight, reps FROM history WHERE lift_id = ? ORDER BY id", (lid,)
        ).fetchall()
        lift = Lift(name=r["name"], tier="t2", day=r["day"], start=r["start"], sets=r["sets"])
        from sbs_cli.data.schema import SetEntry
        history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"]) for h in hist_rows]
        ls = recompute_state(lift, history, profile_globals)
        conn.execute(
            "UPDATE lift_state SET target = ?, streak = ?, weight = ?, est1rm = ? "
            "WHERE lift_id = ?",
            (ls.target, ls.streak, ls.weight, ls.est1rm, lid),
        )


def run(db_path: str, backup_dir: str) -> None:
    ts = "manual"  # keep deterministic; tests assert prefix only
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, f"sbs-schedule-{ts}.db.bak")
    if not os.path.exists(backup):
        shutil.copy2(db_path, backup)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_schedule_table(conn)
    _seed_schedule_if_empty(conn)
    _add_column(conn, "lifts", "lift_kind", "TEXT")
    _add_column(conn, "lift_state", "reseeded_cycle", "INTEGER NOT NULL DEFAULT 0")
    _backfill_lift_kind(conn)

    s = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    from sbs_cli.data.schema import Profile
    profile_globals = Profile(
        rounding=s["rounding"], days_per_week=s["days_per_week"], incr=s["incr"],
        t2_reset_pct=s["t2_reset_pct"], t2_fail=s["t2_fail"], t3_target=s["t3_target"],
    )
    _replay_t2(conn, profile_globals)
    conn.commit()
    conn.close()
    print(f"migrated {db_path} (backup -> {backup})")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "sbs.db"
    bdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(db), "backups")
    run(db, bdir)
```

- [ ] **Step 4: Run migration tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_migrate_schedule.py -v`
Expected: PASS (2 tests), including the idempotency check.

- [ ] **Step 5: Run it against the real DB (manual verification)**

Run: `conda run -n sbs python migrate_schedule.py sbs.db backups`
Expected output: `migrated sbs.db (backup -> .../sbs-schedule-manual.db.bak)`.

Then verify: `conda run -n sbs python -c "import sqlite3; c=sqlite3.connect('sbs.db'); print('schedule', c.execute('select count(*) from sbs_schedule').fetchone()[0]); print('chin-ups', c.execute(\"select target,streak from lift_state where lift_id=(select id from lifts where name='Chin-ups')\").fetchone())"`
Expected: `schedule 42` and `chin-ups (6, 1)`.

- [ ] **Step 6: Commit**

```bash
git add migrate_schedule.py tests/test_migrate_schedule.py
git commit -m "feat(migrate): one-shot schedule + lift_kind backfill + T2 1-strike replay"
```

---

## Task 8: `/schedule` editor page + reset

**Files:**
- Create: `webapp/routes/schedule.py`
- Create: `webapp/templates/schedule.html`
- Modify: `webapp/app.py`
- Test: `tests/test_routes_schedule.py` (new)

**Interfaces:**
- Consumes: `repo.get_schedule`, `repo.replace_schedule`, `repo.reset_schedule` (Task 5).
- Produces: `GET /schedule` (render editor), `POST /schedule` (save edits), `POST /schedule/reset` (restore defaults).

- [ ] **Step 1: Write the failing route test**

Create `tests/test_routes_schedule.py`:

```python
from sbs_cli.defaults import DEFAULT_SCHEDULE


def test_schedule_view_lists_42_rows(client):
    rv = client.get("/schedule")
    assert rv.status_code == 200
    assert b"Main" in rv.data and b"Aux" in rv.data


def test_schedule_save_edits_a_row(client, app):
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        conn.close()
    # post an edit for main week 1 -> intensity 0.71
    rv = client.post("/schedule", data={"main_1_intensity": "0.71",
                                        "main_1_reps": "5", "main_1_repout": "10"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT intensity FROM sbs_schedule WHERE kind='main' AND week=1").fetchone()
        assert row["intensity"] == 0.71
        conn.close()


def test_schedule_reset_restores_defaults(client, app):
    client.post("/schedule", data={"main_1_intensity": "0.99", "main_1_reps": "1", "main_1_repout": "1"})
    rv = client.post("/schedule/reset")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT * FROM sbs_schedule WHERE kind='main' AND week=1").fetchone()
        assert (row["intensity"], row["reps"], row["repout"]) == (0.70, 5, 10)
        conn.close()


def test_schedule_save_rejects_bad_intensity(client):
    rv = client.post("/schedule", data={"main_1_intensity": "1.5", "main_1_reps": "5", "main_1_repout": "10"})
    assert rv.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_schedule.py -v`
Expected: FAIL — no `/schedule` route.

- [ ] **Step 3: Create the blueprint**

Create `webapp/routes/schedule.py`:

```python
"""21-week schedule editor (main + aux) + reset-to-default."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from sbs_cli.defaults import DEFAULT_SCHEDULE

bp = Blueprint("schedule", __name__)

_KINDS = ("main", "aux")


@bp.route("/schedule")
def view():
    conn = get_db()
    rows = repo.get_schedule(conn)
    by_kind = {k: {} for k in _KINDS}
    for r in rows:
        by_kind[r["kind"]][r["week"]] = r
    return render_template("schedule.html", by_kind=by_kind, kinds=_KINDS,
                           weeks=range(1, 22))


def _parse_form():
    """Collect {kind: {week: (intensity, reps, repout)}} from form fields <kind>_<week>_<field>."""
    out = {k: {} for k in _KINDS}
    for key, val in request.form.items():
        parts = key.split("_")
        if len(parts) != 3:
            continue
        kind, week_s, field = parts
        if kind not in _KINDS or field not in ("intensity", "reps", "repout"):
            continue
        out[kind].setdefault(int(week_s), {})[field] = val
    return out


@bp.route("/schedule", methods=["POST"])
def save():
    conn = get_db()
    parsed = _parse_form()
    new_rows = []
    for kind in _KINDS:
        for week in range(1, 22):
            f = parsed[kind].get(week, {})
            try:
                intensity = float(f.get("intensity", 0))
                reps = int(f.get("reps", 0))
                repout = int(f.get("repout", 0))
            except ValueError:
                flash(f"非法值: {kind} week {week}")
                return ("bad value", 400)
            if not (0 < intensity < 1) or reps <= 0 or repout <= 0:
                flash(f"范围错误: {kind} week {week} (强度须 0~1, 次数/repout 须 >0)")
                return ("out of range", 400)
            new_rows.append((kind, week, intensity, reps, repout))
    repo.replace_schedule(conn, new_rows)
    flash("进度表已更新")
    return redirect(url_for("schedule.view"))


@bp.route("/schedule/reset", methods=["POST"])
def reset():
    conn = get_db()
    repo.reset_schedule(conn)
    flash("进度表已恢复默认")
    return redirect(url_for("schedule.view"))
```

- [ ] **Step 4: Create the template**

Create `webapp/templates/schedule.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>21 周进度表</h2>
<form action="{{ url_for('schedule.save') }}" method="post">
  {% for kind in kinds %}
  <h3>{{ kind | capitalize }}</h3>
  <table>
    <tr><th>周</th><th>强度</th><th>次数</th><th>repout</th></tr>
    {% for w in weeks %}
    {% set r = by_kind[kind][w] %}
    <tr>
      <td>{{ w }}</td>
      <td><input type="number" step="0.025" name="{{ kind }}_{{ w }}_intensity"
                 value="{{ '%.3f'|format(r.intensity) }}" style="width:70px"></td>
      <td><input type="number" name="{{ kind }}_{{ w }}_reps" value="{{ r.reps }}" style="width:60px"></td>
      <td><input type="number" name="{{ kind }}_{{ w }}_repout" value="{{ r.repout }}" style="width:60px"></td>
    </tr>
    {% endfor %}
  </table>
  {% endfor %}
  <button type="submit">保存</button>
</form>
<form action="{{ url_for('schedule.reset') }}" method="post" style="margin-top:8px">
  <button type="submit">恢复默认进度表</button>
</form>
{% with msgs = get_flashed_messages() %}
  {% if msgs %}<div class="flash">{{ msgs[0] }}</div>{% endif %}
{% endwith %}
{% endblock %}
```

- [ ] **Step 5: Register the blueprint**

In `webapp/app.py`, inside `create_app` after the settings blueprint registration:

```python
    from .routes.schedule import bp as schedule_bp
    app.register_blueprint(schedule_bp)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_schedule.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add webapp/routes/schedule.py webapp/templates/schedule.html webapp/app.py tests/test_routes_schedule.py
git commit -m "feat(webapp): /schedule editor + reset-to-default for the 21-week tables"
```

---

## Task 9: Lift form — `lift_kind` selector, hide sbs intensity/reps/repout

**Files:**
- Modify: `webapp/routes/lifts.py`
- Modify: `webapp/templates/_lift_row.html`
- Modify: `webapp/templates/lifts.html`
- Test: `tests/test_routes_lifts.py`

**Interfaces:**
- Consumes: `repo.create_lift` / `update_lift` now accept `lift_kind` (Task 5).
- Produces: sbs lifts get an explicit main/aux selector; the `intensity/reps/repout` inputs are hidden for sbs.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routes_lifts.py`:

```python
def test_create_sbs_lift_persists_lift_kind(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Squat", "tier": "sbs", "day": "1", "sets": "5", "max": "100",
        "lift_kind": "main"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT lift_kind FROM lifts WHERE name='Squat'").fetchone()
        assert row["lift_kind"] == "main"
        conn.close()


def test_edit_sbs_lift_changes_kind(client, app):
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        conn.close()
    rv = client.post(f"/lifts/{lid}/edit", data={"lift_kind": "aux"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT lift_kind FROM lifts WHERE id=?", (lid,)).fetchone()
        assert row["lift_kind"] == "aux"
        conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_lifts.py -k lift_kind -v`
Expected: FAIL — `lift_kind` not read from the form.

- [ ] **Step 3: Read `lift_kind` in the lifts route**

In `webapp/routes/lifts.py::new`, add `lift_kind` to the `create_lift` call:

```python
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float),
            lift_kind=request.form.get("lift_kind") if tier == "sbs" else None)
```

In `edit`, add `("lift_kind", str)` to the loop tuple so it is settable.

- [ ] **Step 4: Update the templates**

In `webapp/templates/_lift_row.html`, add a `lift_kind` selector shown only for sbs, and wrap the `intensity/reps/repout` inputs so they render only for non-sbs (in practice they were only meaningful for sbs; hide them for sbs now that the schedule owns those values). Example diff for the sbs params block:

```html
{% if lift.tier == 'sbs' %}
  <select name="lift_kind">
    <option value="main" {{ 'selected' if lift.lift_kind == 'main' }}>main</option>
    <option value="aux"  {{ 'selected' if lift.lift_kind == 'aux' }}>aux</option>
  </select>
{% else %}
  {# intensity/reps/repout inputs remain here for any non-sbs path that used them;
     sbs now reads these from the schedule, so they are NOT shown for sbs #}
{% endif %}
```

Remove (or move into the `{% else %}` above) the existing `intensity` / `reps` / `repout` inputs so they no longer appear for an sbs lift. Do the equivalent in `lifts.html` (the new-lift form): show the `lift_kind` select for sbs, hide the three inputs.

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_lifts.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/lifts.py webapp/templates/_lift_row.html webapp/templates/lifts.html tests/test_routes_lifts.py
git commit -m "feat(webapp): explicit lift_kind selector; hide intensity/reps/repout for sbs"
```

---

## Task 10: `/settings` per-field reset-to-default buttons

**Files:**
- Modify: `webapp/routes/settings.py`
- Modify: `webapp/templates/settings.html`
- Test: `tests/test_routes_settings.py`

**Interfaces:**
- Consumes: `sbs_cli.defaults.DEFAULT_SETTINGS`, `RESETTABLE_FIELDS` (Task 2); `repo.update_settings`.
- Produces: `POST /settings/<field>/reset` for each field in `RESETTABLE_FIELDS`; `rounding`/`incr` have no such route (404).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routes_settings.py`:

```python
def test_reset_t2_fail_restores_default(client, app):
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        repo.update_settings(conn, t2_fail=5)
        conn.close()
    rv = client.post("/settings/t2_fail/reset")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert conn.execute("SELECT t2_fail FROM settings WHERE id=1").fetchone()["t2_fail"] == 3
        conn.close()


def test_reset_rounding_is_not_a_route(client):
    # rounding is a weight setting — no reset endpoint
    rv = client.post("/settings/rounding/reset")
    assert rv.status_code == 404


def test_reset_unknown_field_is_404(client):
    rv = client.post("/settings/nope/reset")
    assert rv.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_settings.py -k reset -v`
Expected: FAIL — no reset route.

- [ ] **Step 3: Add the reset route**

In `webapp/routes/settings.py`, add:

```python
from sbs_cli.defaults import DEFAULT_SETTINGS, RESETTABLE_FIELDS


@bp.route("/settings/<field>/reset", methods=["POST"])
def reset_field(field):
    if field not in RESETTABLE_FIELDS:
        return ("not resettable", 404)
    repo.update_settings(get_db(), **{field: DEFAULT_SETTINGS[field]})
    flash(f"{field} 已恢复默认 ({DEFAULT_SETTINGS[field]})")
    return redirect(url_for("settings.view"))
```

- [ ] **Step 4: Add reset buttons to the template**

In `webapp/templates/settings.html`, next to each of `days_per_week`, `t2_reset_pct`, `t2_fail`, `t3_target`, add a small form:

```html
<form action="{{ url_for('settings.reset_field', field='t2_fail') }}" method="post" style="display:inline">
  <button type="submit">↺ 默认</button>
</form>
```

Repeat for `days_per_week`, `t2_reset_pct`, `t3_target`. Do **not** add one for `rounding` or `incr`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_settings.py -v`
Expected: PASS (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/settings.py webapp/templates/settings.html tests/test_routes_settings.py
git commit -m "feat(webapp): per-field reset-to-default for non-weight settings"
```

---

## Task 11: `/reseed` page + `/plan` banner

**Files:**
- Create: `webapp/routes/reseed.py`
- Create: `webapp/templates/reseed.html`
- Modify: `webapp/routes/plan.py`
- Modify: `webapp/templates/plan.html`
- Modify: `webapp/app.py`
- Test: `tests/test_routes_reseed.py` (new), `tests/test_routes_plan.py`

**Interfaces:**
- Consumes: `progression.schedule_week`, `cycle_number` (Task 1); `repo.set_reseed` (Task 5).
- Produces:
  - `GET /reseed` — list sbs lifts due for reseed at the current program week.
  - `POST /reseed/<lid>` — apply: set `max` + `tm` + `reseeded_cycle`.
  - `POST /reseed/<lid>/skip` — stamp `reseeded_cycle`, leave `tm`.
  - `plan.view` passes `due_reseeds` to `plan.html`, which shows a banner linking to `/reseed`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_routes_reseed.py`:

```python
from sbs_cli.engine.progression import schedule_week, cycle_number


def _seed_squat_at(app, week):
    from webapp.db import connect
    from webapp import repo
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        repo.set_week(conn, week)
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        conn.close()
        return lid


def test_reseed_not_due_in_cycle_1(client, app):
    _seed_squat_at(app, 2)            # cycle 1, schedule week 2 -> not due
    rv = client.get("/reseed")
    assert rv.status_code == 200
    assert b"Squat" not in rv.data    # not listed as due


def test_reseed_due_at_cycle_2_week_22(client, app):
    lid = _seed_squat_at(app, 22)     # schedule_week(22)=1, cycle 2, reseeded_cycle 0 -> due
    rv = client.get("/reseed")
    assert b"Squat" in rv.data


def test_reseed_apply_sets_max_and_tm(client, app):
    lid = _seed_squat_at(app, 22)
    rv = client.post(f"/reseed/{lid}", data={"max": "120"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT max FROM lifts WHERE id=?", (lid,)).fetchone()
        st = conn.execute("SELECT tm, reseeded_cycle FROM lift_state WHERE lift_id=?", (lid,)).fetchone()
        assert row["max"] == 120.0
        assert st["tm"] == 120.0
        assert st["reseeded_cycle"] == 2
        conn.close()


def test_reseed_skip_keeps_tm_advances_cycle(client, app):
    lid = _seed_squat_at(app, 22)
    rv = client.post(f"/reseed/{lid}/skip")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        st = conn.execute("SELECT tm, reseeded_cycle FROM lift_state WHERE lift_id=?", (lid,)).fetchone()
        assert st["tm"] == 100.0      # unchanged
        assert st["reseeded_cycle"] == 2
        conn.close()


def test_plan_banner_lists_due_reseed(client, app):
    _seed_squat_at(app, 22)
    html = client.get("/").get_data(as_text=True)
    assert "reseed" in html.lower() or "重测" in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `conda run -n sbs pytest tests/test_routes_reseed.py -v`
Expected: FAIL — no `/reseed` route.

- [ ] **Step 3: Create the reseed blueprint**

Create `webapp/routes/reseed.py`:

```python
"""Cycle-boundary TM reseed: per-lift, skippable (ADR 0002)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from sbs_cli.engine.progression import schedule_week, cycle_number

bp = Blueprint("reseed", __name__)


def _due_lifts(conn):
    """sbs lifts due for reseed at the current program week."""
    week = repo.get_settings(conn)["week"]
    if schedule_week(week) != 1 or week == 1:
        return [], cycle_number(week)
    cyc = cycle_number(week)
    out = []
    for r in repo.list_lifts(conn):
        if r["tier"] != "sbs":
            continue
        st = repo.get_lift_state(conn, r["id"])
        if (st["reseeded_cycle"] or 0) < cyc:
            out.append((r, st))
    return out, cyc


@bp.route("/reseed")
def view():
    conn = get_db()
    due, cyc = _due_lifts(conn)
    return render_template("reseed.html", due=due, cycle=cyc)


@bp.route("/reseed/<int:lid>", methods=["POST"])
def apply(lid):
    conn = get_db()
    raw = (request.form.get("max") or "").strip()
    try:
        new_max = float(raw)
    except ValueError:
        flash("max 必须是数字")
        return redirect(url_for("reseed.view"))
    cyc = cycle_number(repo.get_settings(conn)["week"])
    repo.set_reseed(conn, lid, new_max=new_max, cycle=cyc)
    flash("已重测并重置 TM")
    return redirect(url_for("reseed.view"))


@bp.route("/reseed/<int:lid>/skip", methods=["POST"])
def skip(lid):
    conn = get_db()
    cyc = cycle_number(repo.get_settings(conn)["week"])
    repo.set_reseed(conn, lid, cycle=cyc)
    flash("已跳过 (TM 保持当前值)")
    return redirect(url_for("reseed.view"))
```

- [ ] **Step 4: Create the reseed template**

Create `webapp/templates/reseed.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>第 {{ cycle }} 周期 — 重测 max</h2>
{% if not due %}
  <p>当前无需重测。</p>
{% else %}
  {% for r, st in due %}
  <div>
    <strong>{{ r.name }}</strong> (当前 TM {{ '%.1f'|format(st.tm or 0) }})
    <form action="{{ url_for('reseed.apply', lid=r.id) }}" method="post" style="display:inline">
      <input type="number" step="0.5" name="max" placeholder="新 max">
      <button type="submit">重测并重置</button>
    </form>
    <form action="{{ url_for('reseed.skip', lid=r.id) }}" method="post" style="display:inline">
      <button type="submit">跳过</button>
    </form>
  </div>
  {% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Show the banner on `/plan`**

In `webapp/routes/plan.py::view`, compute due lifts and pass them to the template:

```python
@bp.route("/")
def view():
    conn = get_db()
    week, by_day = _by_day(conn)
    from ..routes.reseed import _due_lifts
    due, _cyc = _due_lifts(conn)
    return render_template("plan.html", week=week, by_day=by_day,
                           due_reseeds=[r["name"] for r, _st in due])
```

In `webapp/templates/plan.html`, near the top of the content block, add:

```html
{% if due_reseeds %}
<div class="reseed-banner">
  新周期开始 — 待重测: {{ due_reseeds | join(", ") }}
  <a href="{{ url_for('reseed.view') }}">去重测</a>
</div>
{% endif %}
```

- [ ] **Step 6: Register the blueprint**

In `webapp/app.py`, inside `create_app`:

```python
    from .routes.reseed import bp as reseed_bp
    app.register_blueprint(reseed_bp)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_reseed.py tests/test_routes_plan.py -v`
Expected: PASS.

- [ ] **Step 8: Run the whole suite as a final gate**

Run: `conda run -n sbs pytest tests/ -v`
Expected: PASS (every test, including the rewritten T2 + schedule-driven cases).

- [ ] **Step 9: Commit**

```bash
git add webapp/routes/reseed.py webapp/templates/reseed.html webapp/routes/plan.py webapp/templates/plan.html webapp/app.py tests/test_routes_reseed.py tests/test_routes_plan.py
git commit -m "feat(webapp): /reseed page + /plan cycle-boundary banner (ADR 0002)"
```

---

## Self-Review (completed)

**1. Spec coverage:**
- §Data model (`sbs_schedule`, `lift_kind`, `reseeded_cycle`) → Task 5.
- §Engine (`t2_next`, `week_plan`, `advance_lift`, `recompute_sbs_tm`, schedule helpers) → Tasks 1, 3, 4.
- §Cycle boundary & reseed → Task 11 (+ ADR 0002).
- §Webapp plan/preview/recompute → Task 6.
- §`/schedule` editor + reset → Task 8.
- §`/reseed` page + banner → Task 11.
- §Lift form `lift_kind` + hidden inputs → Task 9.
- §`/settings` reset buttons (exclude `rounding`/`incr`) → Task 10.
- §Defaults module → Task 2.
- §Migration (seed, backfill, T2 replay) → Task 7.
- §Tests (schedule helpers, T2 cases, plan W2, reseed due/apply/skip, migration, reset endpoints) → embedded in each task.
- §Notes (deload autoreg, bodyweight T2, recompute retroactivity) → behavioral, covered by the schedule-driven recompute (Task 4) and the 1-strike rule (Task 3); no separate task needed.

**2. Placeholder scan:** none. Every step has concrete code or an exact command.

**3. Type consistency:**
- `ScheduleRow(kind, week, intensity, reps, repout)` — used identically in Tasks 1, 2, 5, 6.
- `lookup_schedule(schedule, kind, program_week)` — same name in Tasks 1, 4, 6.
- `recompute_sbs_tm(lift, history, schedule)` — defined in Task 4, called with that signature in Task 6.
- `repo.set_reseed(conn, lift_id, *, cycle, new_max=None)` — defined Task 5, called Tasks 7 (no — migration doesn't reseed), 11.
- `repo.create_lift(..., lift_kind=...)` / `update_lift` — Task 5 adds it; Tasks 9 + fixtures use it.
- `RESETTABLE_FIELDS` / `DEFAULT_SETTINGS` — Task 2 defines, Task 10 consumes.

No drift found.
