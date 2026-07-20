# Bodyweight Working-Weight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bodyweight lifts (Dips, Chin-ups, High Crunch) compute tonnage / est1RM / progression correctly by routing every engine weight-reading through a single `working_weight()` seam (`added + bodyweight × bodyweight_pct`), eliminating the `weight`-field semantic overload (ADR 0004).

**Architecture:** Store **added weight** (history stays stable against bodyweight drift); derive **working weight** at one pure seam `sbs_cli/engine/load.py::working_weight()`; feed it to all engine math. `Lift.bodyweight_pct` (0.0 = ordinary, 1.0 = full-bodyweight, 0.64 = pushup) + `Lift.progression` (`"weight"` default | `"none"`) are new per-lift fields; `Profile.bodyweight` is a new global. Engine pure functions keep their signatures; call sites pass working weight, never raw added.

**Tech Stack:** Python 3, Flask + HTMX, SQLite, pytest, PyYAML. Engine in `sbs_cli/` (pure), webapp in `webapp/`.

## Global Constraints

- All dev/test runs in conda env `sbs`: `conda run -n sbs pytest ...` / `conda run -n sbs python ...`
- Engine functions stay pure (no I/O, no mutation of shared state) — ADR 0001 discipline
- **Never `git add -A`** — stage exact files per task commit step
- Conventional commits: `feat:` / `refactor:` / `test:` / `docs:` / `chore:`
- `bodyweight_pct` semantics: `0.0` ordinary lift (working weight = added, unchanged behavior); `> 0` bodyweight lift
- Spec: `docs/superpowers/specs/2026-07-20-bodyweight-load-design.md` · ADR: `docs/adr/0004-bodyweight-working-weight-seam.md` · Glossary: `CONTEXT.md`

---

### Task 1: `working_weight()` seam

**Files:**
- Create: `sbs_cli/engine/load.py`
- Test: `tests/test_load.py`

**Interfaces:**
- Consumes: nothing (foundational pure function)
- Produces: `working_weight(added: float, bodyweight: float, bodyweight_pct: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_load.py
from sbs_cli.engine.load import working_weight


def test_ordinary_lift_pct_zero_returns_added_unchanged():
    # ordinary barbell lift: no bodyweight component
    assert working_weight(100.0, 75.0, 0.0) == 100.0


def test_full_bodyweight_zero_added():
    # chin-up, no belt: working weight = full bodyweight
    assert working_weight(0.0, 75.0, 1.0) == 75.0


def test_weighted_bodyweight_added_plus_bw():
    # chin-up +2.5 kg belt
    assert working_weight(2.5, 75.0, 1.0) == 77.5


def test_partial_bodyweight_pushup():
    # push-up moves ~64% of bodyweight
    assert working_weight(0.0, 75.0, 0.64) == 48.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_load.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sbs_cli.engine.load'`

- [ ] **Step 3: Write minimal implementation**

```python
# sbs_cli/engine/load.py
"""Working-weight seam: the single translation point from stored added weight
to the working weight fed to all engine math. See ADR 0004.

Every call site that feeds estimate_1rm / tonnage / t2_next-reset MUST pass
through here — never a raw .weight / .start / history.weight. Enforced by
behavior-guard tests (Task 16).
"""


def working_weight(added: float, bodyweight: float, bodyweight_pct: float) -> float:
    """added + bodyweight × bodyweight_pct.

    bodyweight_pct == 0.0 for an ordinary lift, so this returns ``added``
    unchanged. For a bodyweight lift the bodyweight term is added back in.
    """
    return added + bodyweight * bodyweight_pct
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_load.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/engine/load.py tests/test_load.py
git commit -m "feat(engine): add working_weight() seam for bodyweight lifts"
```

---

### Task 2: Schema fields + YAML roundtrip

**Files:**
- Modify: `sbs_cli/data/schema.py` (Profile, Lift)
- Modify: `sbs_cli/data/io.py` (`profile_to_dict`, `profile_from_dict`)
- Test: `tests/test_io.py`

**Interfaces:**
- Consumes: Task 1 (not actually — schema is independent)
- Produces: `Profile.bodyweight: float`; `Lift.bodyweight_pct: float`; `Lift.progression: str`; YAML keys `bodyweight` (top-level), `bodyweight_pct` + `progression` (per lift)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_io.py  (append)
import tempfile, os
from sbs_cli.data.schema import Profile, Lift
from sbs_cli.data.io import save_profile, load_profile


def test_profile_bodyweight_and_lift_bodyweight_pct_roundtrip():
    p = Profile(bodyweight=75.0, lifts=[
        Lift(name="Chin-ups", tier="t2", day=2, start=0.0,
             bodyweight_pct=1.0, progression="none"),
        Lift(name="Squat", tier="sbs", day=1, max=135.0),  # ordinary: pct 0
    ])
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    try:
        save_profile(p, path)
        back = load_profile(path)
    finally:
        os.remove(path)
    assert back.bodyweight == 75.0
    chin = back.lift("Chin-ups")
    assert chin.bodyweight_pct == 1.0
    assert chin.progression == "none"
    squat = back.lift("Squat")
    assert squat.bodyweight_pct == 0.0           # default for ordinary lifts
    assert squat.progression == "weight"         # default


def test_legacy_yaml_without_bodyweight_fields_loads_defaults():
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, b"rounding: 2.5\nlifts:\n- name: Squat\n  tier: sbs\n  day: 1\n  max: 100\n")
    os.close(fd)
    try:
        back = load_profile(path)
    finally:
        os.remove(path)
    assert back.bodyweight == 0.0
    assert back.lift("Squat").bodyweight_pct == 0.0
    assert back.lift("Squat").progression == "weight"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_io.py::test_profile_bodyweight_and_lift_bodyweight_pct_roundtrip -v`
Expected: FAIL — `AttributeError: 'Profile' object has no attribute 'bodyweight'` (or dataclass arg error)

- [ ] **Step 3: Add fields to schema**

In `sbs_cli/data/schema.py`, add fields to `Lift` (after `incr`, line ~30):

```python
    incr: Optional[float] = None      # t2/t3 per-lift progression step; None = inherit global incr
    # bodyweight lift modeling (ADR 0004). bodyweight_pct == 0.0 -> ordinary lift
    # (working weight == added, unchanged). >0 -> fraction of bodyweight moved
    # (1.0 pull-up/dip, ~0.64 push-up). progression "none" skips auto-progression
    # (pure-bodyweight lifts like crunches progressed by hand).
    bodyweight_pct: float = 0.0
    progression: str = "weight"
```

Add field to `Profile` (after `t3_target`, line ~40):

```python
    t3_target: int = 15
    bodyweight: float = 0.0   # user bodyweight (kg), global; feeds working_weight()
```

- [ ] **Step 4: Extend YAML roundtrip in io.py**

In `sbs_cli/data/io.py::profile_to_dict`, add `bodyweight` to the top-level dict and the two lift fields:

```python
def profile_to_dict(p: Profile) -> dict:
    return {
        "rounding": p.rounding, "days_per_week": p.days_per_week, "incr": p.incr,
        "t2_reset_pct": p.t2_reset_pct, "t2_fail": p.t2_fail, "t3_target": p.t3_target,
        "bodyweight": p.bodyweight,
        "lifts": [
            {k: v for k, v in {
                "name": l.name, "tier": l.tier, "day": l.day, "max": l.max,
                "intensity": l.intensity, "reps": l.reps, "repout": l.repout,
                "sets": l.sets, "start": l.start, "lift_kind": l.lift_kind,
                "bodyweight_pct": l.bodyweight_pct, "progression": l.progression,
            }.items() if v is not None and v != 0}
            for l in p.lifts
        ],
    }
```

> Note: the existing `if v is not None and v != 0` filter drops `bodyweight_pct=0.0` and `bodyweight=0.0` (defaults) — desired: legacy YAML stays clean. `progression="weight"` is also dropped (non-zero/non-None filter keeps `"none"` since it's a non-empty string; `"weight"` is truthy so it IS kept — to match the filter's intent, accept that `"weight"` writes out; roundtrip still works). If you want `"weight"` omitted too, change the filter to also drop `v == "weight"`, but that complicates the comprehension — leaving it written is harmless.

In `profile_from_dict`, read the new fields with defaults:

```python
        lifts = [Lift(
            name=x["name"], tier=x["tier"], day=x["day"],
            max=x.get("max"), intensity=x.get("intensity", 0.0), reps=x.get("reps", 0),
            repout=x.get("repout", 0), sets=x.get("sets", 3), start=x.get("start"),
            lift_kind=x.get("lift_kind") or ("main" if x.get("tier") == "sbs" else None),
            bodyweight_pct=x.get("bodyweight_pct", 0.0),
            progression=x.get("progression", "weight"),
        ) for x in d.get("lifts", [])]
    return Profile(
        rounding=d.get("rounding", 2.5), days_per_week=d.get("days_per_week", 4),
        incr=d.get("incr", 2.5), t2_reset_pct=d.get("t2_reset_pct", 0.70),
        t2_fail=d.get("t2_fail", 3), t3_target=d.get("t3_target", 15), lifts=lifts,
        bodyweight=d.get("bodyweight", 0.0),
        schedule=list(DEFAULT_SCHEDULE),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_io.py -v`
Expected: PASS (both new tests + existing io tests unchanged)

- [ ] **Step 6: Commit**

```bash
git add sbs_cli/data/schema.py sbs_cli/data/io.py tests/test_io.py
git commit -m "feat(schema): add bodyweight / bodyweight_pct / progression fields + YAML roundtrip"
```

---

### Task 3: Engine `best_1rm` + `_est1rm_from_history` use working weight

**Files:**
- Modify: `sbs_cli/program.py:8-21` (`best_1rm`, `_est1rm_from_history`)
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: Task 1 `working_weight(added, bodyweight, bodyweight_pct)`
- Produces: `best_1rm(history, bodyweight=0.0, bodyweight_pct=0.0) -> (working_weight, reps) | None`; `_est1rm_from_history(history, bodyweight=0.0, bodyweight_pct=0.0) -> float | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_program.py  (append)
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import best_1rm, _est1rm_from_history
from sbs_cli.engine.onerm import estimate_1rm


def test_best_1rm_bodyweight_uses_working_weight_not_added():
    # chin-up: added 0, bw 75, pct 1.0, reps 5 -> working weight 75
    hist = [SetEntry(week=1, weight=0.0, reps=5)]
    bw, reps = best_1rm(hist, bodyweight=75.0, bodyweight_pct=1.0)
    assert bw == 75.0
    assert reps == 5


def test_est1rm_from_history_bodyweight_nonzero():
    hist = [SetEntry(week=1, weight=0.0, reps=5)]
    est = _est1rm_from_history(hist, bodyweight=75.0, bodyweight_pct=1.0)
    assert est == estimate_1rm(75.0, 5)
    assert est > 0.0


def test_est1rm_from_history_ordinary_lift_unchanged():
    # pct 0 -> working weight == added; legacy behavior preserved
    hist = [SetEntry(week=1, weight=100.0, reps=5)]
    est = _est1rm_from_history(hist, bodyweight=75.0, bodyweight_pct=0.0)
    assert est == estimate_1rm(100.0, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_program.py::test_est1rm_from_history_bodyweight_nonzero -v`
Expected: FAIL — returns `estimate_1rm(0.0, 5)` ≈ 0 (uses raw `h.weight`)

- [ ] **Step 3: Route both through the seam**

In `sbs_cli/program.py`, replace `best_1rm` and `_est1rm_from_history` (lines 8-21). Add import at top (after line 4):

```python
from .engine.onerm import estimate_1rm
from .engine.load import working_weight
```

Replace the two functions:

```python
def best_1rm(history: List[SetEntry], bodyweight: float = 0.0,
             bodyweight_pct: float = 0.0):
    """Return (working_weight, reps) of the history entry with the highest
    estimate_1rm, or None. ``weight`` from each entry is treated as ADDED
    weight and converted to working weight via the seam (ADR 0004)."""
    best = None
    best_e = -1.0
    for h in history:
        w = working_weight(h.weight, bodyweight, bodyweight_pct)
        e = estimate_1rm(w, h.reps)
        if e > best_e:
            best_e, best = e, (w, h.reps)
    return best


def _est1rm_from_history(history: List[SetEntry], bodyweight: float = 0.0,
                         bodyweight_pct: float = 0.0) -> Optional[float]:
    b = best_1rm(history, bodyweight, bodyweight_pct)
    return estimate_1rm(b[0], b[1]) if b else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_program.py -v`
Expected: PASS (new tests green; existing program tests unchanged since default `bodyweight_pct=0.0` → working weight == added)

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "refactor(engine): best_1rm/_est1rm_from_history route through working_weight seam"
```

---

### Task 4: Engine `recompute_state` passes bodyweight to est1RM (incl. T2 reset)

**Files:**
- Modify: `sbs_cli/program.py::recompute_state` (lines ~93-117)
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: Task 3 `_est1rm_from_history(history, bodyweight, bodyweight_pct)`; `recompute_state` already takes `(lift, history, profile)` so it has `lift.bodyweight_pct` + `profile.bodyweight`
- Produces: unchanged signature `recompute_state(lift, history, profile) -> LiftState`, now bodyweight-aware

- [ ] **Step 1: Write the failing test**

```python
# tests/test_program.py  (append)
from sbs_cli.program import recompute_state
from sbs_cli.data.schema import Lift, Profile, SetEntry


def test_recompute_state_t2_bodyweight_reset_uses_working_weight():
    # Chin-ups (t2, pct 1.0). Force 3 consecutive misses -> reset to
    # round(est1rm × 0.75, incr). est1rm must be computed from working weight
    # (75 + added), not added alone — otherwise reset weight collapses toward 0.
    lift = Lift(name="Chin-ups", tier="t2", day=2, start=0.0,
                bodyweight_pct=1.0, incr=2.5)
    profile = Profile(bodyweight=75.0, incr=2.5, t2_fail=3, t2_reset_pct=0.75)
    # 3 misses at target 8 (reps < 8 each)
    hist = [SetEntry(week=1, weight=0.0, reps=5),
            SetEntry(week=2, weight=0.0, reps=5),
            SetEntry(week=3, weight=0.0, reps=5)]
    ls = recompute_state(lift, hist, profile)
    # reset weight should be on the order of est1rm(75, 5) × 0.75 ≈ 63 kg,
    # NOT near 0. Assert it is plainly bodyweight-driven:
    assert ls.weight > 50.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_program.py::test_recompute_state_t2_bodyweight_reset_uses_working_weight -v`
Expected: FAIL — reset weight computed from `estimate_1rm(0, 5)` ≈ 0 → `ls.weight` near 0

- [ ] **Step 3: Pass bodyweight through recompute_state**

In `sbs_cli/program.py::recompute_state`, thread `profile.bodyweight` + `lift.bodyweight_pct` into both `_est1rm_from_history` calls. Replace line 98 and the loop body around line 110:

```python
def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``
    over ``history``. History rows are immutable facts; only their reps drive the
    replay. ``est1rm`` is computed from working weight (added + bodyweight × pct).
    Not applicable to sbs."""
    bw, pct = profile.bodyweight, lift.bodyweight_pct
    est = _est1rm_from_history(history, bw, pct)
    eff_incr = lift.incr if lift.incr is not None else profile.incr
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target, incr=eff_incr)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1], bw, pct) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_program.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "fix(engine): recompute_state threads bodyweight into est1RM + T2 reset"
```

---

### Task 5: Engine `advance_lift` — progression="none" branch + working-weight est1RM

**Files:**
- Modify: `sbs_cli/program.py::advance_lift` (lines ~36-62)
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: Task 3 `_est1rm_from_history(history, bodyweight, bodyweight_pct)`; `profile.bodyweight`, `lift.bodyweight_pct`, `lift.progression`
- Produces: unchanged `advance_lift(profile, lift, state, actual_reps, week)`; new behavior — `progression="none"` skips t2/t3 progression; est1RM uses working weight; history still stores ADDED weight

- [ ] **Step 1: Write the failing test**

```python
# tests/test_program.py  (append)
from sbs_cli.program import advance_lift
from sbs_cli.data.schema import LiftState


def _bw_profile(**kw):
    return Profile(bodyweight=75.0, incr=2.5, t3_target=15, **kw)


def test_advance_lift_progression_none_skips_weight_progression():
    # High Crunch: t3, pct 1.0, progression none. Hit target (15) -> state.weight
    # must NOT gain incr (no phantom added weight).
    lift = Lift(name="High Crunch", tier="t3", day=4, start=0.0,
                bodyweight_pct=1.0, progression="none")
    state = LiftState(name="High Crunch", tier="t3", weight=0.0)
    p = _bw_profile(schedule=[])  # t3 doesn't need schedule
    advance_lift(p, lift, state, actual_reps=20, week=1)
    assert state.weight == 0.0           # unchanged — no +2.5 phantom added
    assert state.est1rm is not None and state.est1rm > 0.0   # est1rm from bw


def test_advance_lift_progression_weight_still_increments_added():
    # Dips: t3, pct 1.0, progression weight (default). Hit target -> +incr to added.
    lift = Lift(name="Dips", tier="t3", day=4, start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="Dips", tier="t3", weight=0.0)
    p = _bw_profile(schedule=[])
    advance_lift(p, lift, state, actual_reps=20, week=1)
    assert state.weight == 2.5           # added grew by incr


def test_advance_lift_bodyweight_history_stores_added_not_working():
    lift = Lift(name="Dips", tier="t3", day=4, start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="Dips", tier="t3", weight=0.0)
    p = _bw_profile(schedule=[])
    advance_lift(p, lift, state, actual_reps=10, week=1)
    assert state.history[-1].weight == 0.0    # added, NOT 75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_program.py::test_advance_lift_progression_none_skips_weight_progression -v`
Expected: FAIL — Crunch `state.weight` becomes 2.5 (t3_next ran)

- [ ] **Step 3: Add progression branch + working-weight est1RM**

In `sbs_cli/program.py::advance_lift`, update the est1RM call and gate progression. Replace lines ~44-62:

```python
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history,
                                            profile.bodyweight, lift.bodyweight_pct)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, sc.repout, actual_reps)
    elif lift.progression == "none":
        pass   # pure bodyweight: record only, no auto weight progression (ADR 0004)
    else:
        # effective step: per-lift incr ?? global incr (ADR 0003).
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        if lift.tier == "t3":
            state.weight = t3_next(state.weight, actual_reps,
                                   target=profile.t3_target, incr=eff_incr)
        elif lift.tier == "t2":
            est = state.est1rm if state.est1rm is not None else 0.0
            ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_program.py -v`
Expected: PASS (new tests + all existing advance tests, since default `progression="weight"` + `bodyweight_pct=0.0` preserve legacy behavior)

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "feat(engine): advance_lift progression=none + working-weight est1RM"
```

---

### Task 6: Engine `week_plan` exposes working weight (CLI display)

**Files:**
- Modify: `sbs_cli/program.py::week_plan` (lines ~73-90)
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: Task 1 `working_weight`; `profile.bodyweight`, `l.bodyweight_pct`
- Produces: `PlanItem.weight` now holds working weight for bodyweight lifts (was raw added = 0)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_program.py  (append)
from sbs_cli.program import week_plan, initial_state
from sbs_cli.data.schema import Lift, Profile, ProgramState


def test_week_plan_bodyweight_t2_shows_working_weight_not_zero():
    lift = Lift(name="Chin-ups", tier="t2", day=2, start=0.0, bodyweight_pct=1.0)
    p = Profile(bodyweight=75.0, incr=2.5, lifts=[lift], schedule=[])
    st = ProgramState(week=1, lifts={"Chin-ups":
        LiftState(name="Chin-ups", tier="t2", weight=0.0, target=8)})
    items = week_plan(p, st, day=2)
    assert len(items) == 1
    assert items[0].weight == 75.0    # working weight, not 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_program.py::test_week_plan_bodyweight_t2_shows_working_weight_not_zero -v`
Expected: FAIL — `items[0].weight == 0.0`

- [ ] **Step 3: Compute working weight in week_plan**

In `sbs_cli/program.py::week_plan`, add the import (if not already from Task 3) and convert t2/t3 display weight. Replace lines ~82-89:

```python
        if l.tier == "sbs":
            sc = lookup_schedule(profile.schedule, l.lift_kind, state.week)
            w = round_weight((ls.tm or 0) * sc.intensity, profile.rounding)
            out.append(PlanItem(l.name, "sbs", w, sc.reps, l.sets, sc.repout, None, 0, ls.est1rm))
        elif l.tier == "t2":
            w = working_weight(ls.weight or 0.0, profile.bodyweight, l.bodyweight_pct)
            out.append(PlanItem(l.name, "t2", w, ls.target, l.sets, None, ls.target, ls.streak, ls.est1rm))
        elif l.tier == "t3":
            w = working_weight(ls.weight or 0.0, profile.bodyweight, l.bodyweight_pct)
            out.append(PlanItem(l.name, "t3", w, profile.t3_target, l.sets, None, profile.t3_target, 0, ls.est1rm))
```

(Ensure `from .engine.load import working_weight` is imported at the top of `program.py` — added in Task 3.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_program.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "feat(engine): week_plan shows working weight for bodyweight lifts"
```

---

### Task 7: webapp DB schema + repo (columns, create_lift, init_schema migration)

**Files:**
- Modify: `webapp/db.py` (`_SCHEMA`, `_DEFAULT_SETTINGS`, `init_schema`)
- Modify: `webapp/repo.py` (`_SETTINGS_COLS`, `_LIFT_COLS`, `create_lift`, `_init_lift_state` unchanged, `update_lift` auto via `_LIFT_COLS`)
- Test: `tests/test_db.py`, `tests/test_repo.py`

**Interfaces:**
- Consumes: nothing (storage layer)
- Produces: `settings.bodyweight` column; `lifts.bodyweight_pct` + `lifts.progression` columns; `create_lift(..., bodyweight_pct=0.0, progression="weight")`; `get_settings()` row includes `bodyweight`; existing DBs auto-migrated via ALTER TABLE

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py  (append)
import sqlite3
from webapp.db import init_schema, _SCHEMA  # noqa: F401


def test_init_schema_adds_bodyweight_columns_to_legacy_db():
    """A DB created with the OLD schema (no bodyweight cols) must gain them on
    the next init_schema call, so existing user DBs upgrade in place."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # build OLD-shape schema (pre-bodyweight)
    conn.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id=1), week INTEGER,
            days_per_week INTEGER, rounding REAL, incr REAL, t2_reset_pct REAL,
            t2_fail INTEGER, t3_target INTEGER);
        CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, tier TEXT,
            day INTEGER, sort_order INTEGER, sets INTEGER, max REAL, intensity REAL,
            reps INTEGER, repout INTEGER, start REAL, lift_kind TEXT, incr REAL);
        CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT, tm REAL,
            weight REAL, target INTEGER, streak INTEGER, est1rm REAL, reseeded_cycle INTEGER);
        CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INTEGER,
            week INTEGER, weight REAL, reps INTEGER, ts TEXT);
        CREATE TABLE week_log (lift_id INTEGER, week INTEGER, reps INTEGER,
            PRIMARY KEY (lift_id, week));
        CREATE TABLE sbs_schedule (kind TEXT, week INTEGER, intensity REAL, reps INTEGER,
            repout INTEGER, PRIMARY KEY (kind, week));
        INSERT INTO settings VALUES (1,1,4,2.5,2.5,0.75,3,15);
    """)
    init_schema(conn)   # should ALTER missing columns into existence
    s_cols = {r["name"] for r in conn.execute("PRAGMA table_info(settings)")}
    l_cols = {r["name"] for r in conn.execute("PRAGMA table_info(lifts)")}
    assert "bodyweight" in s_cols
    assert "bodyweight_pct" in l_cols
    assert "progression" in l_cols
    conn.close()


# tests/test_repo.py  (append)
def test_create_lift_stores_bodyweight_pct_and_progression(conn):  # conn fixture from conftest
    from webapp.repo import create_lift, get_lift
    lid = create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0, progression="none")
    row = get_lift(conn, lid)
    assert row["bodyweight_pct"] == 1.0
    assert row["progression"] == "none"
```

> If `tests/test_db.py` / `tests/test_repo.py` use a different fixture or import style than shown, match the existing file's conventions (check `tests/conftest.py` for the `conn` fixture). The assertions are what matter.

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n sbs pytest tests/test_db.py::test_init_schema_adds_bodyweight_columns_to_legacy_db tests/test_repo.py::test_create_lift_stores_bodyweight_pct_and_progression -v`
Expected: FAIL — columns missing / `create_lift` rejects `bodyweight_pct` kwarg

- [ ] **Step 3: Extend schema + defaults in db.py**

In `webapp/db.py::_SCHEMA`, add columns to the `settings` and `lifts` CREATE statements:

```sql
CREATE TABLE IF NOT EXISTS settings (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    week         INTEGER NOT NULL,
    days_per_week INTEGER NOT NULL,
    rounding     REAL    NOT NULL,
    incr         REAL    NOT NULL,
    t2_reset_pct REAL    NOT NULL,
    t2_fail      INTEGER NOT NULL,
    t3_target    INTEGER NOT NULL,
    bodyweight   REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lifts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    tier           TEXT NOT NULL CHECK (tier IN ('sbs','t2','t3')),
    day            INTEGER NOT NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    sets           INTEGER NOT NULL DEFAULT 3,
    max            REAL,
    intensity      REAL,
    reps           INTEGER,
    repout         INTEGER,
    start          REAL,
    lift_kind      TEXT,
    incr           REAL,
    bodyweight_pct REAL NOT NULL DEFAULT 0.0,
    progression    TEXT NOT NULL DEFAULT 'weight' CHECK (progression IN ('weight','none'))
);
```

Update `_DEFAULT_SETTINGS`:

```python
_DEFAULT_SETTINGS = dict(
    week=1, days_per_week=4, rounding=2.5, incr=2.5,
    t2_reset_pct=0.75, t2_fail=3, t3_target=15, bodyweight=0.0,
)
```

Update the settings INSERT in `init_schema` to include `bodyweight`:

```python
        conn.execute(
            "INSERT INTO settings (id, week, days_per_week, rounding, incr, t2_reset_pct, t2_fail, t3_target, bodyweight) "
            "VALUES (1, :week, :days_per_week, :rounding, :incr, :t2_reset_pct, :t2_fail, :t3_target, :bodyweight)",
            _DEFAULT_SETTINGS,
        )
```

Add a column-migration helper and call it at the top of `init_schema` (after `executescript`, before the settings seed) so live DBs gain the new columns:

```python
def _add_column_if_missing(conn, table, col, decl):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # Migrate pre-bodyweight DBs (ADR 0004). Idempotent — no-op once present.
    _add_column_if_missing(conn, "settings", "bodyweight", "REAL NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "lifts", "bodyweight_pct", "REAL NOT NULL DEFAULT 0.0")
    _add_column_if_missing(conn, "lifts", "progression",
                            "TEXT NOT NULL DEFAULT 'weight' CHECK (progression IN ('weight','none'))")
    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        ...  # existing INSERT, updated above
```

- [ ] **Step 4: Extend repo.py**

In `webapp/repo.py`:

```python
_SETTINGS_COLS = ("week", "days_per_week", "rounding", "incr",
                  "t2_reset_pct", "t2_fail", "t3_target", "bodyweight")
```

```python
_LIFT_COLS = ("name", "tier", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start", "lift_kind", "incr",
              "bodyweight_pct", "progression")


def create_lift(conn: sqlite3.Connection, *, name: str, tier: str, day: int,
                sort_order: int, sets: int, max, intensity, reps, repout,
                start, lift_kind=None, incr=None,
                bodyweight_pct: float = 0.0, progression: str = "weight") -> int:
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr, bodyweight_pct, progression) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr,
         bodyweight_pct, progression),
    )
    lid = cur.lastrowid
    _init_lift_state(conn, lid, tier, max, start)
    conn.commit()
    return lid
```

`_init_lift_state` is unchanged (lift_state table gains no columns). `update_lift` and `update_settings` need no change — they derive from `_LIFT_COLS` / `_SETTINGS_COLS`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_db.py tests/test_repo.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/db.py webapp/repo.py tests/test_db.py tests/test_repo.py
git commit -m "feat(db): bodyweight/bodyweight_pct/progression columns + in-place migration"
```

---

### Task 8: webapp services read new fields (`_lift_from_row`, `_profile_from_rows`)

**Files:**
- Modify: `webapp/services/advance.py` (`_lift_from_row`, `_profile_from_rows`)
- Test: `tests/test_advance_service.py`

**Interfaces:**
- Consumes: Task 7 DB columns
- Produces: `Lift` objects carry `bodyweight_pct` + `progression`; `Profile` carries `bodyweight` — so downstream `advance_lift` / `recompute_state` / preview / volume receive them

- [ ] **Step 1: Write the failing test**

```python
# tests/test_advance_service.py  (append)
def test_lift_from_row_maps_bodyweight_pct_and_progression(conn):
    from webapp.repo import create_lift
    from webapp.services.advance import _lift_from_row
    lid = create_lift(conn, name="Chin-ups", tier="t2", day=2, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0, progression="none")
    from webapp.repo import get_lift
    lift = _lift_from_row(get_lift(conn, lid))
    assert lift.bodyweight_pct == 1.0
    assert lift.progression == "none"


def test_profile_from_rows_maps_bodyweight(conn):
    from webapp.repo import update_settings, get_settings
    from webapp.services.advance import _profile_from_rows
    update_settings(conn, bodyweight=75.0)
    p = _profile_from_rows(get_settings(conn), [], [])
    assert p.bodyweight == 75.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_advance_service.py::test_lift_from_row_maps_bodyweight_pct_and_progression -v`
Expected: FAIL — `lift.bodyweight_pct` defaults to 0.0 (not mapped from row)

- [ ] **Step 3: Map the new fields**

In `webapp/services/advance.py::_lift_from_row`:

```python
def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"],
        incr=r["incr"] if "incr" in r.keys() else None,
        bodyweight_pct=r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0,
        progression=r["progression"] if "progression" in r.keys() else "weight",
    )
```

In `_profile_from_rows`:

```python
def _profile_from_rows(settings, lift_rows, schedule) -> Profile:
    return Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
        bodyweight=settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0,
        lifts=[_lift_from_row(r) for r in lift_rows],
        schedule=schedule,
    )
```

`recompute.py` uses `_lift_from_row` / `_profile_from_rows` and so inherits the new fields automatically — no edit needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_advance_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/services/advance.py tests/test_advance_service.py
git commit -m "feat(webapp): map bodyweight/bodyweight_pct/progression into engine Profile/Lift"
```

---

### Task 9: webapp preview `_working_weight` + `live_preview` use the seam

**Files:**
- Modify: `webapp/services/preview.py` (`_working_weight`)
- Test: `tests/test_preview_service.py`

**Interfaces:**
- Consumes: Task 1 `working_weight`; Task 7 `settings["bodyweight"]`, `lift["bodyweight_pct"]`
- Produces: `_working_weight` returns working weight (was raw `state.weight` for t2/t3); `live_preview` est1RM now bodyweight-correct

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preview_service.py  (append)
def test_live_preview_bodyweight_est1rm_uses_working_weight(conn):
    from webapp.repo import create_lift, update_settings
    from webapp.services.preview import live_preview
    from sbs_cli.engine.onerm import estimate_1rm
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Chin-ups", tier="t2", day=2, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    r = live_preview(conn, lid, 5)
    assert r["weight"] == 75.0                       # working weight, not 0
    assert r["est1rm"] == estimate_1rm(75.0, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_preview_service.py::test_live_preview_bodyweight_est1rm_uses_working_weight -v`
Expected: FAIL — `r["weight"] == 0.0`

- [ ] **Step 3: Route t2/t3 through the seam**

In `webapp/services/preview.py`, import the seam and update `_working_weight`:

```python
from sbs_cli.engine.progression import round_weight, lookup_schedule
from sbs_cli.engine.load import working_weight
from .. import repo


def _working_weight(lift, state, settings, schedule) -> float:
    """Working weight for the current week. sbs = round(TM × intensity);
    t2/t3 = working_weight(state.weight, bodyweight, bodyweight_pct)."""
    if lift["tier"] == "sbs":
        sc = lookup_schedule(schedule, lift["lift_kind"], settings["week"])
        return round_weight((state["tm"] or 0) * sc.intensity, settings["rounding"])
    bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
    pct = lift["bodyweight_pct"] if "bodyweight_pct" in lift.keys() else 0.0
    return working_weight(state["weight"] or 0.0, bw, pct)
```

(`live_preview` already calls `_working_weight` → `estimate_1rm`, so it is fixed transitively.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_preview_service.py -v`
Expected: PASS (existing preview tests still green — ordinary lifts have `bodyweight_pct=0` → working weight == added)

- [ ] **Step 5: Commit**

```bash
git add webapp/services/preview.py tests/test_preview_service.py
git commit -m "fix(preview): working_weight seam for bodyweight est1RM"
```

---

### Task 10: webapp volume — history branch uses the seam

**Files:**
- Modify: `webapp/services/volume.py::lift_week_volume` (history branch, line ~72)
- Test: `tests/test_volume_service.py`

**Interfaces:**
- Consumes: Task 1 `working_weight`; `lift["bodyweight_pct"]`, `settings["bodyweight"]`
- Produces: past-week tonnage for bodyweight lifts uses working weight (was raw `row["weight"]` = added)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_volume_service.py  (append)
def test_lift_week_volume_bodyweight_past_week_uses_working_weight(conn):
    from webapp.repo import create_lift, append_history, update_settings, save_lift_state
    from webapp.services.volume import lift_week_volume
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    # seed a prior-week history row: added 0, reps 12, 3 sets, t3_target 15
    save_lift_state(conn, lid, tier="t3", tm=None, weight=0.0, target=None, streak=0, est1rm=None)
    append_history(conn, lid, week=1, weight=0.0, reps=12)
    # settings.week is 1 by default; query week 1 as PAST (is_current=False)
    tonnage = lift_week_volume(conn, lid, week=1, is_current=False)
    # working weight 75, sets 3, planned 15, last 12 -> 75 × (2×15 + 12) = 75 × 42 = 3150
    assert tonnage == 75.0 * (2 * 15 + 12)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_volume_service.py::test_lift_week_volume_bodyweight_past_week_uses_working_weight -v`
Expected: FAIL — tonnage == 0 (uses `row["weight"]` = 0)

- [ ] **Step 3: Convert history-branch weight**

In `webapp/services/volume.py`, import the seam (add near the top):

```python
from sbs_cli.engine.load import working_weight
```

In `lift_week_volume`, change the past-week branch (currently `weight = row["weight"]`) to derive working weight:

```python
    else:
        row = next((h for h in repo.list_history(conn, lift_id) if h["week"] == week), None)
        if row is None:
            return None
        last_set = row["reps"]
        bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
        pct = lift["bodyweight_pct"] if "bodyweight_pct" in lift.keys() else 0.0
        weight = working_weight(row["weight"], bw, pct)
```

(The `is_current` branch already goes through `preview._working_weight`, which Task 9 fixed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/services/volume.py tests/test_volume_service.py
git commit -m "fix(volume): bodyweight past-week tonnage via working_weight seam"
```

---

### Task 11: webapp plan view — bodyweight display format + wider layout

**Files:**
- Modify: `webapp/routes/plan.py::_by_day` (t2/t3 rows add `working_weight` + `is_bodyweight`)
- Modify: `webapp/templates/plan.html` (meta line format)
- Modify: `webapp/templates/base.html` (`max-width 900px → 1200px`)
- Test: `tests/test_routes_plan.py`

**Interfaces:**
- Consumes: Task 1 `working_weight`; Task 7 columns
- Produces: bodyweight lift rows render `+{{ added }} ({{ working_weight }}) kg`; row no longer wraps

- [ ] **Step 1: Write the failing test**

```python
# tests/test_routes_plan.py  (append)
def test_plan_view_renders_bodyweight_added_plus_working_weight(conn, client):
    from webapp.repo import create_lift, update_settings
    update_settings(conn, bodyweight=75.0)
    create_lift(conn, name="Chin-ups", tier="t2", day=1, sort_order=1, sets=3,
                max=None, intensity=None, reps=None, repout=None, start=0.0,
                bodyweight_pct=1.0)
    rv = client.get("/")
    body = rv.get_data(as_text=True)
    assert "+0" in body              # added shown
    assert "(75" in body             # working weight shown in parens
```

> Match `client` fixture style to existing `tests/test_routes_plan.py` (see `tests/conftest.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_plan.py::test_plan_view_renders_bodyweight_added_plus_working_weight -v`
Expected: FAIL — body shows `0 kg`, no `+0 (75`

- [ ] **Step 3: Add display fields in _by_day**

In `webapp/routes/plan.py::_by_day`, import the seam and attach `added` + `working_weight` to each t2/t3 item. Update the t2 and t3 branches:

```python
from sbs_cli.engine.load import working_weight
...
        elif r["tier"] == "t2":
            bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
            pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
            added = st["weight"] or 0.0
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="t2",
                                   weight=added, working_weight=working_weight(added, bw, pct),
                                   is_bodyweight=pct > 0,
                                   reps=st["target"], sets=r["sets"], repout=None,
                                   target=st["target"], streak=st["streak"], est1rm=est1rm)
        else:  # t3
            bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
            pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
            added = st["weight"] or 0.0
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="t3",
                                   weight=added, working_weight=working_weight(added, bw, pct),
                                   is_bodyweight=pct > 0,
                                   reps=settings["t3_target"], sets=r["sets"], repout=None,
                                   target=settings["t3_target"], streak=0, est1rm=est1rm)
```

(For the sbs branch you may also add `is_bodyweight=False` so the template can branch uniformly — optional.)

- [ ] **Step 4: Render the format in plan.html**

In `webapp/templates/plan.html`, replace the meta span (line ~19) so bodyweight lifts show `+added (working) kg`:

```html
        <span class="meta">{{ it.tier }} |
          {%- if it.is_bodyweight %} +{{ it.weight }} ({{ it.working_weight }}){% else %} {{ it.weight }}{% endif %} kg
          {% if it.tier=='sbs' %} x {{ it.reps }} x {{ it.sets }} | rep-out {{ it.repout }}
          {% elif it.tier=='t2' %} x {{ it.target }} x {{ it.sets }} | streak {{ it.streak }}
          {% else %} x {{ it.target }} x {{ it.sets }}
          {% endif %}
          | est 1RM {{ "%.2f"|format(it.est1rm) if it.est1rm is not none else '—' }}
        </span>
```

- [ ] **Step 5: Widen the layout**

In `webapp/templates/base.html`, change line 8:

```css
    body{font-family:system-ui,sans-serif;margin:16px;max-width:1200px}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_plan.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add webapp/routes/plan.py webapp/templates/plan.html webapp/templates/base.html tests/test_routes_plan.py
git commit -m "feat(plan): bodyweight '+added (working)' display + wider layout"
```

---

### Task 12: Lift CRUD — edit bodyweight_pct + progression

**Files:**
- Modify: `webapp/templates/_lift_row.html` (add inputs)
- Modify: `webapp/routes/lifts.py` (`new`, `edit`) — pass new fields to `create_lift` / `update_lift`
- Test: `tests/test_routes_lifts.py`

**Interfaces:**
- Consumes: Task 7 `create_lift`/`update_lift` accept `bodyweight_pct`, `progression` (via `_LIFT_COLS`)
- Produces: lift edit form can set bodyweight_pct + progression; values persist

- [ ] **Step 1: Write the failing test**

```python
# tests/test_routes_lifts.py  (append)
def test_edit_lift_sets_bodyweight_pct_and_progression(conn, client):
    from webapp.repo import create_lift, get_lift
    lid = create_lift(conn, name="Crunch", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"bodyweight_pct": "1.0",
                                                 "progression": "none"})
    assert rv.status_code == 200
    row = get_lift(conn, lid)
    assert row["bodyweight_pct"] == 1.0
    assert row["progression"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_lifts.py::test_edit_lift_sets_bodyweight_pct_and_progression -v`
Expected: FAIL — fields not in form-processing allowlist; column unchanged

- [ ] **Step 3: Add inputs to _lift_row.html**

In `webapp/templates/_lift_row.html`, add two inputs inside the edit `<form>` (after the `start` input, before `<button>保存</button>`):

```html
    <input name="bodyweight_pct" type="number" step="0.01" min="0" max="1"
           value="{{ lift.bodyweight_pct if lift.bodyweight_pct else '' }}" style="width:80px" placeholder="bw%">
    <select name="progression" style="width:90px">
      <option value="weight" {{ 'selected' if lift.progression != 'none' else '' }}>weight</option>
      <option value="none" {{ 'selected' if lift.progression == 'none' else '' }}>none</option>
    </select>
```

- [ ] **Step 4: Accept the fields in lifts.py**

In `webapp/routes/lifts.py::edit`, add the two columns to the field loop:

```python
    for col, cast in (("name", str), ("tier", str), ("day", int), ("sets", int),
                      ("max", float), ("intensity", float), ("reps", int),
                      ("repout", int), ("start", float), ("lift_kind", str),
                      ("bodyweight_pct", float), ("progression", str)):
        if col in request.form and request.form[col].strip() != "":
            fields[col] = cast(request.form[col])
```

In `new`, pass them to `create_lift`:

```python
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float),
            lift_kind=_f("lift_kind") if tier == "sbs" else None, incr=incr,
            bodyweight_pct=_f("bodyweight_pct", 0.0, float) or 0.0,
            progression=request.form.get("progression", "weight"))
```

(`update_lift` derives allowed columns from `_LIFT_COLS`, already extended in Task 7 — so `edit` needs only the loop change above.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_lifts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/_lift_row.html webapp/routes/lifts.py tests/test_routes_lifts.py
git commit -m "feat(lifts): edit bodyweight_pct + progression"
```

---

### Task 13: Global settings — bodyweight field

**Files:**
- Modify: `webapp/templates/settings.html`
- Modify: `webapp/routes/settings.py` (`_NUM`)
- Test: `tests/test_routes_settings.py`

**Interfaces:**
- Consumes: Task 7 `settings.bodyweight` column + `_SETTINGS_COLS`
- Produces: `/settings` form can set user bodyweight

- [ ] **Step 1: Write the failing test**

```python
# tests/test_routes_settings.py  (append)
def test_update_settings_bodyweight(conn, client):
    from webapp.repo import get_settings
    rv = client.post("/settings", data={"bodyweight": "75.5"})
    assert rv.status_code == 302
    assert get_settings(conn)["bodyweight"] == 75.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_settings.py::test_update_settings_bodyweight -v`
Expected: FAIL — `bodyweight` not in `_NUM` → ignored → stays 0

- [ ] **Step 3: Add to _NUM + template**

In `webapp/routes/settings.py`:

```python
_NUM = {"rounding": float, "incr": float, "t2_reset_pct": float,
        "t2_fail": int, "t3_target": int, "days_per_week": int,
        "bodyweight": float}
```

In `webapp/templates/settings.html`, add an input mirroring the existing numeric fields (match the file's existing field markup; the key is `name="bodyweight"` bound to `s.bodyweight`). Example minimal row:

```html
<label>体重 (kg): <input type="number" step="0.1" name="bodyweight" value="{{ s.bodyweight }}"></label>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_routes_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/routes/settings.py webapp/templates/settings.html tests/test_routes_settings.py
git commit -m "feat(settings): user bodyweight field"
```

---

### Task 14: migrate.py profile→DB sync + profile.yaml

**Files:**
- Modify: `migrate.py` (pass `bodyweight` to settings sync; `bodyweight_pct`/`progression` to `create_lift`)
- Modify: `profile.yaml` (top-level `bodyweight`; three lifts tagged)
- Test: `tests/test_migrate.py`

**Interfaces:**
- Consumes: Task 2 yaml fields; Task 7 `create_lift`/`update_settings` new kwargs
- Produces: running `python migrate.py` seeds bodyweight + bodyweight_pct + progression from profile.yaml into the DB

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate.py  (append)
def test_migrate_seeds_bodyweight_and_lift_bodyweight_fields(tmp_path):
    import migrate
    from webapp.db import init_schema
    import sqlite3
    profile_yaml = tmp_path / "profile.yaml"
    profile_yaml.write_text(
        "bodyweight: 75.0\nrounding: 2.5\nlifts:\n"
        "- name: Chin-ups\n  tier: t2\n  day: 2\n  start: 0.0\n  bodyweight_pct: 1.0\n  progression: none\n",
        encoding="utf-8")
    db = tmp_path / "sbs.db"
    conn = sqlite3.connect(str(db)); conn.row_factory = sqlite3.Row
    init_schema(conn)
    # call migrate's seed with the test profile + conn (match how migrate.py exposes it;
    # if migrate.py only has a CLI main(), refactor a seed(conn, profile) helper — see step 3)
    from sbs_cli.data.io import load_profile
    p = load_profile(str(profile_yaml))
    migrate.seed(conn, p)   # helper introduced in step 3
    from webapp.repo import get_settings, list_lifts
    assert get_settings(conn)["bodyweight"] == 75.0
    chin = next(r for r in list_lifts(conn) if r["name"] == "Chin-ups")
    assert chin["bodyweight_pct"] == 1.0
    assert chin["progression"] == "none"
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_migrate.py::test_migrate_seeds_bodyweight_and_lift_bodyweight_fields -v`
Expected: FAIL — `migrate.seed` missing (or bodyweight not synced)

- [ ] **Step 3: Wire new fields into migrate.py**

Open `migrate.py`. Find where it builds the settings dict for `repo.update_settings(...)` and add `bodyweight`:

```python
    repo.update_settings(conn,
        rounding=p.rounding, days_per_week=p.days_per_week, incr=p.incr,
        t2_reset_pct=p.t2_reset_pct, t2_fail=p.t2_fail, t3_target=p.t3_target,
        bodyweight=p.bodyweight,
    )
```

Find each `repo.create_lift(...)` call and add the two kwargs:

```python
        repo.create_lift(conn, name=l.name, tier=l.tier, day=l.day, sort_order=idx,
                         sets=l.sets, max=l.max, intensity=l.intensity, reps=l.reps,
                         repout=l.repout, start=l.start, lift_kind=l.lift_kind, incr=l.incr,
                         bodyweight_pct=l.bodyweight_pct, progression=l.progression)
```

If `migrate.py` does not already expose a `seed(conn, profile)` function (only a `main()` that opens its own DB + profile path), extract one so the test (and any future re-seed) can call it directly:

```python
def seed(conn, p):
    """Apply a Profile to an already-open DB: settings + lifts."""
    # ... the update_settings + create_lift calls above ...
```

Keep `main()` reading `profile.yaml` + opening the DB, then delegating to `seed(conn, p)`.

- [ ] **Step 4: Update profile.yaml**

In `D:/WorkSpace/sbs/profile.yaml`, add a top-level `bodyweight: 75.0` (near `incr:` at top). Tag the three bodyweight lifts:

```yaml
- name: Dips                 # bodyweight
  tier: t3
  ...
  start: 0.0
  bodyweight_pct: 1.0
```

```yaml
- name: Chin-ups             # bodyweight, t2 back
  tier: t2
  ...
  start: 0.0
  bodyweight_pct: 1.0
```

```yaml
- name: High Crunch          # bodyweight
  tier: t3
  ...
  start: 0.0
  bodyweight_pct: 1.0
  progression: none
```

- [ ] **Step 5: Run tests + smoke the migration**

Run: `conda run -n sbs pytest tests/test_migrate.py -v`
Expected: PASS

Then against the real profile (optional smoke, requires backing up `sbs.db` first):
`conda run -n sbs python migrate.py`
Expected: no errors; verify with `conda run -n sbs python -c "from webapp.db import connect; from webapp.repo import get_settings; print(get_settings(connect())['bodyweight'])"` → `75.0`.

- [ ] **Step 6: Commit**

```bash
git add migrate.py profile.yaml tests/test_migrate.py
git commit -m "feat(migrate): sync bodyweight/bodyweight_pct/progression from profile.yaml"
```

---

### Task 15: est1RM recompute migration for existing lifts

**Files:**
- Create: `migrate_bodyweight.py` (one-shot: recompute est1RM for bodyweight lifts whose stored est1rm was computed from added-only weight)
- Test: `tests/test_migrate_bodyweight.py`

**Interfaces:**
- Consumes: Tasks 3–4 (bodyweight-aware `_est1rm_from_history` / `recompute_state`); Task 7 columns
- Produces: idempotent script that fixes stale `lift_state.est1rm` on existing DBs

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_bodyweight.py  (new file)
import sqlite3
from webapp.db import init_schema
from webapp.repo import create_lift, append_history, save_lift_state, get_lift_state, update_settings


def test_migrate_bodyweight_recomputes_stale_est1rm():
    import migrate_bodyweight
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    # stale est1rm as it would have been under the OLD (added-only) math:
    save_lift_state(conn, lid, tier="t3", tm=None, weight=0.0, target=None, streak=0,
                    est1rm=0.0)   # added was 0 -> old est1rm 0
    append_history(conn, lid, week=1, weight=0.0, reps=5)
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    st = get_lift_state(conn, lid)
    from sbs_cli.engine.onerm import estimate_1rm
    assert st["est1rm"] == estimate_1rm(75.0, 5)   # now working-weight based
    assert st["est1rm"] > 0.0
    conn.close()


def test_migrate_bodyweight_idempotent():
    # running twice yields the same est1rm
    import migrate_bodyweight
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    save_lift_state(conn, lid, tier="t3", tm=None, weight=0.0, target=None, streak=0, est1rm=0.0)
    append_history(conn, lid, week=1, weight=0.0, reps=5)
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    once = get_lift_state(conn, lid)["est1rm"]
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    twice = get_lift_state(conn, lid)["est1rm"]
    assert once == twice
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_migrate_bodyweight.py -v`
Expected: FAIL — `migrate_bodyweight` module missing

- [ ] **Step 3: Implement the one-shot migration**

```python
# migrate_bodyweight.py
"""One-shot: recompute lift_state.est1rm for bodyweight lifts whose stored
value predates the working-weight seam (ADR 0004). Idempotent.

Run once after deploying the bodyweight schema + engine changes against an
existing user DB:
    conda run -n sbs python migrate_bodyweight.py
"""
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import _est1rm_from_history
from webapp.db import connect, init_schema
from webapp.repo import list_lifts, list_history, save_lift_state, get_lift_state


def recompute_bodyweight_est1rm(conn) -> int:
    """Recompute est1rm for every lift with bodyweight_pct > 0. Returns count."""
    n = 0
    for r in list_lifts(conn):
        pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
        if not pct > 0:
            continue
        hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
                for h in list_history(conn, r["id"])]
        if not hist:
            continue
        from webapp.repo import get_settings
        bw = get_settings(conn)["bodyweight"]
        est = _est1rm_from_history(hist, bw, pct)
        st = get_lift_state(conn, r["id"])
        save_lift_state(conn, r["id"], tier=st["tier"], tm=st["tm"], weight=st["weight"],
                        target=st["target"], streak=st["streak"], est1rm=est)
        n += 1
    return n


if __name__ == "__main__":
    conn = connect(); init_schema(conn)
    fixed = recompute_bodyweight_est1rm(conn)
    print(f"recomputed est1rm for {fixed} bodyweight lift(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs pytest tests/test_migrate_bodyweight.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add migrate_bodyweight.py tests/test_migrate_bodyweight.py
git commit -m "feat(migrate): one-shot est1RM recompute for bodyweight lifts"
```

---

### Task 16: Behavior-guard tests (regression net)

**Files:**
- Create: `tests/test_bodyweight_guard.py`
- No production code changes

**Interfaces:**
- Consumes: all prior tasks
- Produces: a guard suite that fails if any future change lets raw added weight reach engine math

- [ ] **Step 1: Write the guard suite**

```python
# tests/test_bodyweight_guard.py
"""Behavior guards (ADR 0004): bodyweight lifts must never compute est1RM/tonnage
from raw added weight. If a future change reintroduces a raw-weight path, the
fixture (bw 75, added 0) yields 0 and these fail."""
import sqlite3
from webapp.db import init_schema
from webapp.repo import (create_lift, update_settings, save_lift_state,
                         append_history, get_lift_state)
from sbs_cli.engine.onerm import estimate_1rm


def _seed_bodyweight_db():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    return conn


def test_guard_preview_est1rm_is_bodyweight_driven():
    from webapp.services.preview import live_preview
    conn = _seed_bodyweight_db()
    lid = create_lift(conn, name="Chin-ups", tier="t2", day=2, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    assert live_preview(conn, lid, 5)["est1rm"] == estimate_1rm(75.0, 5)
    conn.close()


def test_guard_volume_tonnage_is_bodyweight_driven():
    from webapp.services.volume import lift_week_volume
    conn = _seed_bodyweight_db()
    lid = create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    save_lift_state(conn, lid, tier="t3", tm=None, weight=0.0, target=None, streak=0, est1rm=None)
    append_history(conn, lid, week=1, weight=0.0, reps=12)
    assert lift_week_volume(conn, lid, 1, is_current=False) == 75.0 * (2 * 15 + 12)
    conn.close()


def test_guard_advance_progression_none_keeps_added_zero():
    from sbs_cli.program import advance_lift
    from sbs_cli.data.schema import Lift, LiftState, Profile
    lift = Lift(name="Crunch", tier="t3", day=4, start=0.0,
                bodyweight_pct=1.0, progression="none")
    state = LiftState(name="Crunch", tier="t3", weight=0.0)
    advance_lift(Profile(bodyweight=75.0, incr=2.5, t3_target=15, schedule=[]),
                 lift, state, 20, 1)
    assert state.weight == 0.0
    assert state.est1rm == estimate_1rm(75.0, 20)


def test_guard_advance_t2_reset_uses_working_weight():
    from sbs_cli.program import advance_lift
    from sbs_cli.data.schema import Lift, LiftState, Profile
    # Chin-ups t2: drive 3 misses so a reset fires; reset weight must be bodyweight-scale.
    lift = Lift(name="Chin-ups", tier="t2", day=2, start=0.0, bodyweight_pct=1.0, incr=2.5)
    state = LiftState(name="Chin-ups", tier="t2", weight=0.0, target=8, streak=0)
    p = Profile(bodyweight=75.0, incr=2.5, t2_fail=3, t2_reset_pct=0.75, schedule=[])
    for _ in range(3):
        advance_lift(p, lift, state, 3, 1)   # miss each time
    assert state.weight > 50.0   # reset to ~est1rm(75,3)*0.75, not near 0
```

- [ ] **Step 2: Run the full suite**

Run: `conda run -n sbs pytest -v`
Expected: ALL PASS (new guards + entire existing suite green — ordinary lifts unaffected since `bodyweight_pct=0`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_bodyweight_guard.py
git commit -m "test: bodyweight behavior guards (ADR 0004 regression net)"
```

---

## Self-Review (run before handoff)

**Spec coverage** — every spec section maps to a task:
- `working_weight()` seam → Task 1
- Data model (`Profile.bodyweight`, `Lift.bodyweight_pct`, `Lift.progression`) → Task 2
- Call sites A (`best_1rm`) + B (`_est1rm_from_history`) → Task 3
- Call sites C + D (`recompute_state` est1RM + T2 reset) → Task 4
- `advance_lift` progression="none" + est1RM + history-stores-added (I) → Task 5
- Call site G (`week_plan`) → Task 6
- DB schema + repo + migration → Task 7
- `_lift_from_row` / `_profile_from_rows` → Task 8
- Call site E (`_working_weight`) → Task 9
- Call site F (volume history) → Task 10
- Call site H (`_by_day`) + UI width → Task 11
- Lift CRUD new fields → Task 12
- Settings bodyweight → Task 13
- migrate.py + profile.yaml → Task 14
- est1RM recompute migration → Task 15
- Guard tests → Task 16

**Placeholder scan** — no TBD/TODO; each step has real code or exact diff instructions. `migrate.py` and `settings.html` steps give exact kwargs/markup deltas keyed to known signatures (verified via codegraph).

**Type consistency** — `working_weight(added, bodyweight, bodyweight_pct)` signature identical across Tasks 1, 3, 4, 6, 9, 10, 11. `best_1rm(history, bodyweight, bodyweight_pct)` consistent across Tasks 3, 4. `_est1rm_from_history(history, bodyweight, bodyweight_pct)` consistent. Column names `bodyweight` / `bodyweight_pct` / `progression` identical in schema, repo, db, services, templates, migrate.

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-20-bodyweight-working-weight.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints.

Which approach?
