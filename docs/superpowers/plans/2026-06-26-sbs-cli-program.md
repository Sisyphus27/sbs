# SBS/GZCLP Training CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI tool (`python -m sbs_cli`) that holds the whole training program (SBS main/aux + GZCLP T2 back + T3 accessories), reads a `profile.yaml`, generates a weekly plan as a standalone HTML page with input fields, ingests the user's logged last-set reps via an exported JSON, and auto-progresses every lift — replacing the spreadsheet.

**Architecture:** MVC. Pure-Python engine (`engine/onerm.py` 1RM estimation, `engine/progression.py` per-tier rules) is the spec source of truth; data lives in `profile.yaml` (static) + `state.yaml` (dynamic); views are a Jinja2 HTML form and a terminal pretty-printer; the CLI wires it. The old xlsx approach under `tools/sbs_gzclp/` is frozen (not imported); its verified T2/T3 algorithm is ported into the new engine with the new est1RM-based T2 reset.

**Tech Stack:** Python 3 (conda env `tamp`), PyYAML, Jinja2, openpyxl (importer only), pytest. Run via `conda run --no-capture-output -n tamp python -m sbs_cli ...`.

**Spec:** `docs/superpowers/specs/2026-06-26-sbs-cli-program-design.md`

**No git / checkpoints:** Project is NOT a git repo and the user forbids `git add -A`. Do NOT `git init` or commit. The per-task gate is the full pytest suite passing. Python files are saved with Write/Edit as you go.

**Conda env note:** All commands run through `conda run --no-capture-output -n tamp python ...`. If `pyyaml`/`jinja2`/`pytest` are missing, install: `conda run -n tamp python -m pip install pyyaml jinja2 pytest` (openpyxl is already present).

---

## File Structure

```
D:\WorkSpace\sbs\
├─ sbs_cli/
│   ├─ __init__.py
│   ├─ __main__.py            # `python -m sbs_cli` entry → cli.main()
│   ├─ engine/
│   │   ├─ __init__.py
│   │   ├─ onerm.py           # estimate_1rm(weight, reps) = mean(Epley, Brzycki, Wathan)
│   │   └─ progression.py     # round_weight, SBS deltas, sbs_next, t3_next, t2_next(est1rm reset)
│   ├─ data/
│   │   ├─ __init__.py
│   │   ├─ schema.py          # dataclasses: Lift, Profile, SetEntry, LiftState, ProgramState
│   │   └─ io.py              # profile/state yaml load+save (dataclass ↔ dict)
│   ├─ program.py             # orchestrator: best_1rm, advance(lift,state,reps), build_week_plan
│   ├─ importer.py            # sbs init: read cold-backup xlsx → profile.yaml
│   ├─ view/
│   │   ├─ __init__.py
│   │   ├─ html.py            # render week HTML + parse exported log JSON
│   │   ├─ terminal.py        # pretty-print plan to terminal
│   │   └─ templates/
│   │       └─ week.html.j2   # Jinja2 template (inputs + JS export button)
│   └─ cli.py                 # argparse: init / week / next / show
├─ tests/
│   ├─ test_onerm.py
│   ├─ test_progression.py
│   ├─ test_schema.py
│   ├─ test_io.py
│   ├─ test_program.py
│   ├─ test_importer.py
│   ├─ test_html.py
│   ├─ test_terminal.py
│   └─ test_cli.py            # end-to-end
└─ docs/superpowers/{specs,plans}/…
```

Responsibilities: `onerm.py` (1RM math), `progression.py` (per-tier next-state rules), `schema.py` (in-memory types), `io.py` (yaml persistence), `program.py` (tie engine+state, history/best-set bookkeeping, week plan), `importer.py` (one-time xlsx→profile), `view/html.py` + template (form), `view/terminal.py` (text output), `cli.py` (commands). Each independently testable.

---

## Task 1: Scaffold + 1RM estimation

**Files:**
- Create: `sbs_cli/__init__.py` (empty), `sbs_cli/engine/__init__.py` (empty)
- Create: `sbs_cli/engine/onerm.py`
- Create: `tests/test_onerm.py`

- [ ] **Step 1: Verify deps**

Run: `conda run --no-capture-output -n tamp python -c "import yaml, jinja2, openpyxl, pytest; print('ok')"`
If ImportError: `conda run -n tamp python -m pip install pyyaml jinja2 pytest`.

- [ ] **Step 2: Write failing test `tests/test_onerm.py`:**

```python
import math
from sbs_cli.engine.onerm import estimate_1rm, epley, brzycki, wathan

def test_epley_formula():
    # 100 x 5 -> 100*(1+5/30) = 116.667
    assert abs(epley(100, 5) - 116.6667) < 0.01

def test_brzycki_formula():
    # 100 x 5 -> 100*36/(37-5) = 112.5
    assert abs(brzycki(100, 5) - 112.5) < 0.01

def test_wathan_formula():
    # 100 x 5 -> 100*100/(48.8+53.8*exp(-0.075*5))
    expected = 100 * 100 / (48.8 + 53.8 * math.exp(-0.075 * 5))
    assert abs(wathan(100, 5) - expected) < 1e-9

def test_estimate_is_mean_of_three():
    w, r = 100, 5
    expected = (epley(w, r) + brzycki(w, r) + wathan(w, r)) / 3
    assert abs(estimate_1rm(w, r) - expected) < 1e-9

def test_estimate_single_rep_returns_about_weight():
    # 1 rep -> 1RM ≈ weight (all three formulas give ~weight at reps=1)
    assert abs(estimate_1rm(100, 1) - 100) < 3.0

def test_estimate_higher_reps_exceeds_low_rep_at_same_weight():
    assert estimate_1rm(80, 8) > estimate_1rm(80, 3)
```

- [ ] **Step 3: Run, verify FAIL**

Run: `conda run --no-capture-output -n tamp python -m pytest tests/test_onerm.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 4: Implement `sbs_cli/engine/onerm.py`:**

```python
"""Estimated 1RM = mean of Epley, Brzycki, Wathan (top-3 authoritative formulas)."""
import math
from statistics import mean


def epley(weight: float, reps: float) -> float:
    return weight * (1 + reps / 30)


def brzycki(weight: float, reps: float) -> float:
    return weight * 36 / (37 - reps)


def wathan(weight: float, reps: float) -> float:
    return weight * 100 / (48.8 + 53.8 * math.exp(-0.075 * reps))


def estimate_1rm(weight: float, reps: float) -> float:
    """Mean of the three formulas. Most accurate at reps <= 10."""
    return mean((epley(weight, reps), brzycki(weight, reps), wathan(weight, reps)))
```

- [ ] **Step 5: Create empty package markers** `sbs_cli/__init__.py`, `sbs_cli/engine/__init__.py` so imports resolve from repo root `D:\WorkSpace\sbs`.

- [ ] **Step 6: Run, verify PASS (6 tests).**

- [ ] **Step 7: Full suite gate** — `conda run --no-capture-output -n tamp python -m pytest tests/ -v` (only test_onerm exists yet; 6 passed).

---

## Task 2: Progression engine (SBS tier + T3 + T2-with-est1rm-reset)

**Files:**
- Create: `sbs_cli/engine/progression.py`
- Create: `tests/test_progression.py`

`onerm.py` already exists. T2 reset uses `0.70 * est1rm` (passed in) instead of the old `weight * 0.8`.

- [ ] **Step 1: Write failing tests `tests/test_progression.py`:**

```python
from sbs_cli.engine.progression import round_weight, sbs_next, t3_next, t2_next, T2State

# --- round_weight (MROUND parity) ---
def test_round_weight_mround():
    assert round_weight(52.5, 2.5) == 52.5
    assert round_weight(44.0, 2.5) == 45.0      # MROUND(44,2.5)=45
    assert round_weight(55.0 * 0.8, 2.5) == 45.0

# --- SBS tier (TM autoregulation by rep-out delta) ---
def test_sbs_hit_keeps_tm():
    assert sbs_next(tm=100, repout=8, actual=8) == 100

def test_sbs_beat_adds_pct():
    # beat target 8 by 3 -> +1.5% -> 100*1.015 = 101.5 -> MROUND 101.5? 101.5/2.5=40.6->41*2.5=102.5
    assert sbs_next(tm=100, repout=8, actual=11) == 102.5

def test_sbs_miss_drops_pct():
    # miss by 2 -> -5% -> 95 -> MROUND 95
    assert sbs_next(tm=100, repout=8, actual=6) == 95

def test_sbs_beat_5_plus_caps_at_3pct():
    # beat by 6 -> +3% -> 103 -> MROUND(103,2.5)=102.5
    assert sbs_next(tm=100, repout=8, actual=14) == 102.5

def test_sbs_no_log_keeps_tm():
    assert sbs_next(tm=100, repout=8, actual=None) == 100

# --- T3 (threshold) ---
def test_t3_hit_adds():
    assert t3_next(weight=40, actual=16) == 42.5

def test_t3_miss_repeats():
    assert t3_next(weight=40, actual=12) == 40

def test_t3_no_log_repeats():
    assert t3_next(weight=40, actual=None) == 40

# --- T2 (state machine, est1rm reset) ---
def test_t2_hit_adds_weight_keeps_tier():
    s = t2_next(T2State(target=10, streak=0, weight=50), actual=10, est1rm=100)
    assert s == T2State(target=10, streak=0, weight=52.5)

def test_t2_miss_under_threshold_accumulates():
    s = t2_next(T2State(target=10, streak=1, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=10, streak=2, weight=50)

def test_t2_three_misses_10_drops_to_8():
    s = t2_next(T2State(target=10, streak=2, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=50)

def test_t2_three_misses_8_drops_to_6():
    s = t2_next(T2State(target=8, streak=2, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=0, weight=50)

def test_t2_three_misses_6_resets_to_70pct_of_est1rm():
    # est1rm 100 -> 0.70*100 = 70 -> MROUND 70
    s = t2_next(T2State(target=6, streak=2, weight=50), actual=4, est1rm=100)
    assert s == T2State(target=10, streak=0, weight=70)

def test_t2_reset_uses_est1rm_not_old_weight():
    # est1rm 110 -> 0.70*110 = 77 -> MROUND(77,2.5)=77.5
    s = t2_next(T2State(target=6, streak=2, weight=50), actual=4, est1rm=110)
    assert s == T2State(target=10, streak=0, weight=77.5)

def test_t2_no_log_carries_state():
    s = t2_next(T2State(target=8, streak=1, weight=50), actual=None, est1rm=100)
    assert s == T2State(target=8, streak=1, weight=50)
```

(Note: `T2State` is a frozen dataclass with structural equality.)

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/engine/progression.py`:**

```python
"""Per-tier progression rules. Pure functions; the spec source of truth."""
import math
from dataclasses import dataclass


def round_weight(w: float, quantum: float = 2.5) -> float:
    """Mirror Excel MROUND(w, quantum): round(w/quantum) half-away-from-zero, then * quantum."""
    n = math.floor((w / quantum) + 0.5)
    return round(n * quantum, 10)


# SBS delta by (actual - repout) difference
def _sbs_delta(diff: int) -> float:
    if diff <= -2: return -0.05
    if diff == -1: return -0.02
    if diff == 0:  return 0.0
    if diff == 1:  return 0.005
    if diff == 2:  return 0.01
    if diff == 3:  return 0.015
    if diff == 4:  return 0.02
    return 0.03   # beat by 5+


def sbs_next(tm: float, repout: int, actual, quantum: float = 2.5) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged."""
    if actual is None:
        return tm
    return round_weight(tm * (1 + _sbs_delta(actual - repout)), quantum)


def t3_next(weight: float, actual, target: int = 15, incr: float = 2.5,
            quantum: float = 2.5) -> float:
    """T3 accessories: +incr when last set >= target, else repeat."""
    if actual is None:
        return weight
    if actual >= target:
        return round_weight(weight + incr, quantum)
    return weight


@dataclass(frozen=True)
class T2State:
    target: int     # 10 / 8 / 6
    streak: int     # consecutive misses at current target
    weight: float


def t2_next(state: T2State, actual, est1rm: float, fail: int = 3,
            incr: float = 2.5, reset_pct: float = 0.70, quantum: float = 2.5) -> T2State:
    """GZCLP T2 back: 10->8->6 tier cascade; full reset = reset_pct * est1rm, back to 10."""
    if actual is None:
        return state
    if actual >= state.target:                                   # hit
        return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
    if state.streak + 1 >= fail:                                 # Nth consecutive miss -> tier change
        if state.target == 10:
            return T2State(8, 0, state.weight)
        if state.target == 8:
            return T2State(6, 0, state.weight)
        return T2State(10, 0, round_weight(est1rm * reset_pct, quantum))   # reset at 6
    return T2State(state.target, state.streak + 1, state.weight) # miss, under threshold
```

- [ ] **Step 4: Run, verify PASS (17 tests).**
- [ ] **Step 5: Full suite gate** — `tests/` all pass.

---

## Task 3: Data schema (dataclasses)

**Files:**
- Create: `sbs_cli/data/__init__.py` (empty)
- Create: `sbs_cli/data/schema.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write failing test `tests/test_schema.py`:**

```python
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState

def test_lift_sbs_construction():
    l = Lift(name="Squat", tier="sbs", day=1, max=135, intensity=0.75, reps=4, repout=8, sets=3)
    assert l.tier == "sbs" and l.max == 135 and l.start is None

def test_lift_t2_construction():
    l = Lift(name="Barbell rows", tier="t2", day=1, start=85)
    assert l.max is None and l.start == 85

def test_profile_defaults():
    p = Profile()
    assert p.rounding == 2.5 and p.days_per_week == 4 and p.t2_reset_pct == 0.70
    assert p.lifts == []

def test_setentry_and_liftstate():
    s = SetEntry(week=1, weight=100, reps=9)
    ls = LiftState(name="Squat", tier="sbs", tm=135, est1rm=158.0, history=[s])
    assert ls.history[0].reps == 9

def test_programstate_holds_lifts_by_name():
    ps = ProgramState(week=1, lifts={"Squat": LiftState(name="Squat", tier="sbs", tm=135)})
    assert "Squat" in ps.lifts and ps.lifts["Squat"].tm == 135
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/data/schema.py`:**

```python
"""In-memory data model."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Lift:
    """A lift definition in profile.yaml (static)."""
    name: str
    tier: str           # "sbs" | "t2" | "t3"
    day: int
    # sbs tier
    max: Optional[float] = None
    intensity: float = 0.0
    reps: int = 0
    repout: int = 0
    sets: int = 3
    # t2 / t3
    start: Optional[float] = None


@dataclass
class Profile:
    rounding: float = 2.5
    days_per_week: int = 4
    incr: float = 2.5
    t2_reset_pct: float = 0.70
    t2_fail: int = 3
    t3_target: int = 15
    lifts: List[Lift] = field(default_factory=list)

    def lift(self, name: str) -> Lift:
        for l in self.lifts:
            if l.name == name:
                return l
        raise KeyError(name)


@dataclass
class SetEntry:
    week: int
    weight: float
    reps: int


@dataclass
class LiftState:
    """Per-lift dynamic state in state.yaml."""
    name: str
    tier: str
    # sbs
    tm: Optional[float] = None
    # t2 / t3
    weight: Optional[float] = None
    target: Optional[int] = None     # t2 only (10/8/6)
    streak: int = 0                  # t2 only
    # computed
    est1rm: Optional[float] = None
    history: List[SetEntry] = field(default_factory=list)


@dataclass
class ProgramState:
    week: int = 1
    lifts: Dict[str, LiftState] = field(default_factory=dict)
```

- [ ] **Step 4: Run, verify PASS (5 tests).**
- [ ] **Step 5: Full suite gate.**

---

## Task 4: YAML persistence (profile + state)

**Files:**
- Create: `sbs_cli/data/io.py`
- Create: `tests/test_io.py`

- [ ] **Step 1: Write failing test `tests/test_io.py`:**

```python
import os, tempfile
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from sbs_cli.data import io as dio

def test_profile_roundtrip(tmp_path):
    p = Profile(rounding=2.5, days_per_week=4, lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=135, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", tier="t2", day=1, start=85),
        Lift(name="Curls", tier="t3", day=1, start=12.5),
    ])
    path = tmp_path / "profile.yaml"
    dio.save_profile(p, str(path))
    q = dio.load_profile(str(path))
    assert q.rounding == 2.5 and q.days_per_week == 4
    assert len(q.lifts) == 3
    assert q.lift("Squat").max == 135 and q.lift("Squat").intensity == 0.75
    assert q.lift("Barbell rows").start == 85 and q.lift("Barbell rows").tier == "t2"
    assert q.lift("Curls").start == 12.5

def test_state_roundtrip(tmp_path):
    s = ProgramState(week=3, lifts={
        "Squat": LiftState(name="Squat", tier="sbs", tm=137.5, est1rm=158.0,
                           history=[SetEntry(1, 102.5, 8), SetEntry(2, 105, 10)]),
        "Barbell rows": LiftState(name="Barbell rows", tier="t2", weight=87.5, target=10, streak=0,
                                  est1rm=110.0),
    })
    path = tmp_path / "state.yaml"
    dio.save_state(s, str(path))
    t = dio.load_state(str(path))
    assert t.week == 3
    assert t.lifts["Squat"].tm == 137.5
    assert len(t.lifts["Squat"].history) == 2
    assert t.lifts["Squat"].history[1].reps == 10
    assert t.lifts["Barbell rows"].target == 10 and t.lifts["Barbell rows"].streak == 0
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/data/io.py`:**

```python
"""YAML load/save for Profile and ProgramState."""
import yaml
from .schema import Lift, Profile, SetEntry, LiftState, ProgramState


# ---------- Profile ----------
def profile_to_dict(p: Profile) -> dict:
    return {
        "rounding": p.rounding, "days_per_week": p.days_per_week, "incr": p.incr,
        "t2_reset_pct": p.t2_reset_pct, "t2_fail": p.t2_fail, "t3_target": p.t3_target,
        "lifts": [
            {k: v for k, v in {
                "name": l.name, "tier": l.tier, "day": l.day, "max": l.max,
                "intensity": l.intensity, "reps": l.reps, "repout": l.repout,
                "sets": l.sets, "start": l.start,
            }.items() if v is not None and v != 0}
            for l in p.lifts
        ],
    }

def profile_from_dict(d: dict) -> Profile:
    lifts = [Lift(
        name=x["name"], tier=x["tier"], day=x["day"],
        max=x.get("max"), intensity=x.get("intensity", 0.0), reps=x.get("reps", 0),
        repout=x.get("repout", 0), sets=x.get("sets", 3), start=x.get("start"),
    ) for x in d.get("lifts", [])]
    return Profile(
        rounding=d.get("rounding", 2.5), days_per_week=d.get("days_per_week", 4),
        incr=d.get("incr", 2.5), t2_reset_pct=d.get("t2_reset_pct", 0.70),
        t2_fail=d.get("t2_fail", 3), t3_target=d.get("t3_target", 15), lifts=lifts,
    )

def save_profile(p: Profile, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile_to_dict(p), f, sort_keys=False, allow_unicode=True)

def load_profile(path: str) -> Profile:
    with open(path, "r", encoding="utf-8") as f:
        return profile_from_dict(yaml.safe_load(f))


# ---------- State ----------
def state_to_dict(s: ProgramState) -> dict:
    out_lifts = {}
    for name, ls in s.lifts.items():
        out_lifts[name] = {
            "tier": ls.tier,
            "tm": ls.tm, "weight": ls.weight, "target": ls.target, "streak": ls.streak,
            "est1rm": ls.est1rm,
            "history": [{"week": h.week, "weight": h.weight, "reps": h.reps} for h in ls.history],
        }
    return {"week": s.week, "lifts": out_lifts}

def state_from_dict(d: dict) -> ProgramState:
    lifts = {}
    for name, x in d.get("lifts", {}).items():
        lifts[name] = LiftState(
            name=name, tier=x["tier"], tm=x.get("tm"), weight=x.get("weight"),
            target=x.get("target"), streak=x.get("streak", 0), est1rm=x.get("est1rm"),
            history=[SetEntry(h["week"], h["weight"], h["reps"]) for h in x.get("history", [])],
        )
    return ProgramState(week=d.get("week", 1), lifts=lifts)

def save_state(s: ProgramState, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(state_to_dict(s), f, sort_keys=False, allow_unicode=True)

def load_state(path: str) -> ProgramState:
    with open(path, "r", encoding="utf-8") as f:
        return state_from_dict(yaml.safe_load(f))
```

- [ ] **Step 4: Run, verify PASS (2 tests).**
- [ ] **Step 5: Full suite gate.**

---

## Task 5: Program orchestrator (engine + state + history)

**Files:**
- Create: `sbs_cli/program.py`
- Create: `tests/test_program.py`

Wires the engine to state. Computes est1rm from best history set; advances a lift given its logged last-set reps; builds the per-lift week plan (display weight/reps/target/sets).

- [ ] **Step 1: Write failing test `tests/test_program.py`:**

```python
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from sbs_cli.program import best_1rm, initial_state, advance_lift, week_plan

def _profile():
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", tier="t2", day=1, start=50),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])

def test_best_1rm_picks_max_estimate():
    hist = [SetEntry(1, 80, 5), SetEntry(2, 85, 9), SetEntry(3, 90, 3)]
    b = best_1rm(hist)
    # 85x9 yields the highest est1rm of the three
    assert b is not None and b[0] == 85 and b[1] == 9

def test_best_1rm_empty_returns_none():
    assert best_1rm([]) is None

def test_initial_state_sbs_uses_max_as_tm():
    p = _profile()
    s = initial_state(p)
    assert s.lifts["Squat"].tm == 100
    assert s.lifts["Barbell rows"].weight == 50 and s.lifts["Barbell rows"].target == 10
    assert s.lifts["Curls"].weight == 40

def test_advance_sbs_appends_history_and_updates_est1rm():
    p = _profile(); s = initial_state(p)
    advance_lift(p.lift("Squat"), s.lifts["Squat"], actual_reps=11, week=1)
    # working weight was round(100*0.75)=75; logged; est1rm computed from (75,11)
    assert len(s.lifts["Squat"].history) == 1
    assert s.lifts["Squat"].history[0].weight == 75 and s.lifts["Squat"].history[0].reps == 11
    assert s.lifts["Squat"].est1rm is not None
    # TM progressed: beat repout 8 by 3 -> +1.5% -> 100*1.015=101.5 -> MROUND 102.5
    assert s.lifts["Squat"].tm == 102.5

def test_advance_t2_reset_uses_best_set_est1rm():
    from sbs_cli.engine.progression import round_weight
    p = _profile(); s = initial_state(p)
    ls = s.lifts["Barbell rows"]
    # seed a best set: 50x10 -> est1rm ~ 67
    advance_lift(p.lift("Barbell rows"), ls, actual_reps=10, week=1)
    est = ls.est1rm
    # now force 3 consecutive misses at 10, then 8, into 6, then reset
    ls.target, ls.streak = 6, 2
    advance_lift(p.lift("Barbell rows"), ls, actual_reps=4, week=4)   # 3rd miss at 6 -> reset
    assert ls.target == 10 and ls.streak == 0
    assert ls.weight == round_weight(est * 0.70)                      # 0.70*est, MROUND 2.5

def test_week_plan_sbs_shows_working_weight():
    p = _profile(); s = initial_state(p)
    plan = week_plan(p, s, day=1)
    squat = next(item for item in plan if item.name == "Squat")
    # working weight = round(100*0.75, 2.5) = 75; reps 4, sets 3
    assert squat.weight == 75 and squat.reps == 4 and squat.sets == 3 and squat.repout == 8
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/program.py`:**

```python
"""Tie engine rules to lift state; manage history + est1rm + week plan."""
from typing import Optional, List
from .data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from .engine.onerm import estimate_1rm
from .engine.progression import sbs_next, t3_next, t2_next, T2State, round_weight


def best_1rm(history: List[SetEntry]):
    """Return (weight, reps) of the history entry with the highest estimate_1rm, or None."""
    best = None
    best_e = -1.0
    for h in history:
        e = estimate_1rm(h.weight, h.reps)
        if e > best_e:
            best_e, best = e, (h.weight, h.reps)
    return best


def _est1rm_from_history(history: List[SetEntry]) -> Optional[float]:
    b = best_1rm(history)
    return estimate_1rm(b[0], b[1]) if b else None


def initial_state(profile: Profile) -> ProgramState:
    lifts = {}
    for l in profile.lifts:
        if l.tier == "sbs":
            lifts[l.name] = LiftState(name=l.name, tier="sbs", tm=l.max)
        elif l.tier == "t2":
            lifts[l.name] = LiftState(name=l.name, tier="t2", weight=l.start, target=10, streak=0)
        elif l.tier == "t3":
            lifts[l.name] = LiftState(name=l.name, tier="t3", weight=l.start)
    return ProgramState(week=1, lifts=lifts)


def advance_lift(lift: Lift, state: LiftState, actual_reps, week: int) -> None:
    """Apply this week's logged last-set reps; mutate state in place."""
    # working weight this week (before progression)
    if lift.tier == "sbs":
        w = round_weight((state.tm or 0) * lift.intensity, 2.5)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, lift.repout, actual_reps)
    elif lift.tier == "t3":
        state.weight = t3_next(state.weight, actual_reps, target=15)
    elif lift.tier == "t2":
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight


class PlanItem:
    __slots__ = ("name", "tier", "weight", "reps", "sets", "repout", "target", "streak", "est1rm")
    def __init__(self, name, tier, weight, reps, sets, repout, target, streak, est1rm):
        self.name, self.tier, self.weight, self.reps, self.sets = name, tier, weight, reps, sets
        self.repout, self.target, self.streak, self.est1rm = repout, target, streak, est1rm


def week_plan(profile: Profile, state: ProgramState, day: Optional[int] = None) -> List[PlanItem]:
    """Build the display plan for a given day (or all lifts if day=None)."""
    out = []
    for l in profile.lifts:
        if day is not None and l.day != day:
            continue
        ls = state.lifts.get(l.name)
        if ls is None:
            continue
        if l.tier == "sbs":
            w = round_weight((ls.tm or 0) * l.intensity, profile.rounding)
            out.append(PlanItem(l.name, "sbs", w, l.reps, l.sets, l.repout, None, 0, ls.est1rm))
        elif l.tier == "t2":
            out.append(PlanItem(l.name, "t2", ls.weight, ls.target, l.sets, None, ls.target, ls.streak, ls.est1rm))
        elif l.tier == "t3":
            out.append(PlanItem(l.name, "t3", ls.weight, profile.t3_target, l.sets, None, profile.t3_target, 0, ls.est1rm))
    return out
```

- [ ] **Step 4: Run, verify PASS (6 tests).**
- [ ] **Step 5: Full suite gate.**

---

## Task 6: Importer (cold-backup xlsx → profile.yaml)

**Files:**
- Create: `sbs_cli/importer.py`
- Create: `tests/test_importer.py`

Reads `backup/00_cold_backup.xlsx` and emits a `Profile`: SBS lifts (name + 1RM) from `Quick Setup` `C5:C16`/`D5:D16`; T2 back lifts + T3 accessories from the `4x` sheet (the user's hand-entered rows: back rows sit above each `Accessories` label as plain name+weight; accessories sit below each `Accessories` label).

- [ ] **Step 1: Confirm the source layout** (already known from debugging, re-verify):

```bash
conda run --no-capture-output -n tamp python - <<'EOF'
import openpyxl
wb = openpyxl.load_workbook("backup/00_cold_backup.xlsx")
qs = wb["Quick Setup"]
print("QS C5:D16 (main/aux names+1RM):")
for r in range(5,17):
    print(f"  C{r}={qs[f'C{r}'].value!r} D{r}={qs[f'D{r}'].value!r}")
ws = wb["4x"]
acc = [r for r in range(1, ws.max_row+1) if ws.cell(row=r,column=1).value=="Accessories"]
print("4x Accessories rows:", acc)
EOF
```
Expected: `C5`..`C8` = Squat/Bench Press/Deadlift/OHP; `C11`..`C16` = Front Squat/Paused Squat/Close Grip Bench/Long Pause Bench/Romanian Deadlift/Incline Press; `D5:D16` = 135/120/145/73/105/115/100/95/105/95; Accessories at [11,24,35,46]. Back rows are the non-formula name+number rows directly above each Accessories label (rows 10,23,34,45).

- [ ] **Step 2: Write failing test `tests/test_importer.py`:**

```python
import openpyxl
from sbs_cli.importer import import_profile
from sbs_cli.data.schema import Profile

SRC = r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx"

def test_import_pulls_sbs_maxes():
    p = import_profile(SRC, sheet="4x")
    assert isinstance(p, Profile)
    squat = p.lift("Squat"); assert squat.tier == "sbs" and squat.max == 135
    bench = p.lift("Bench Press"); assert bench.max == 120

def test_import_pulls_back_rows_as_t2():
    p = import_profile(SRC, sheet="4x")
    bb = p.lift("Barbell rows")
    assert bb.tier == "t2" and bb.start == 85

def test_import_pulls_accessories_as_t3():
    p = import_profile(SRC, sheet="4x")
    le = p.lift("Leg Extension")
    assert le.tier == "t3" and le.start == 40

def test_import_days_per_week_matches_sheet():
    p = import_profile(SRC, sheet="4x")
    assert p.days_per_week == 4
```

- [ ] **Step 3: Run, verify FAIL.**

- [ ] **Step 4: Implement `sbs_cli/importer.py`:**

```python
"""One-time import: cold-backup xlsx -> Profile. Specific to the user's 4x layout."""
import openpyxl
from .data.schema import Lift, Profile

QS_MAIN_ROWS = [5, 6, 7, 8]            # Squat/Bench/DL/OHP
QS_AUX_ROWS = [11, 12, 13, 14, 15, 16] # Front/Paused/Close Grip/Long Pause/RDL/Incline

# SBS-tier defaults the user can edit afterwards.
SBS_DEFAULTS = {  # intensity, reps, repout, sets by lift row
    5:  (0.75, 4, 8, 3), 6: (0.75, 4, 8, 3), 7: (0.80, 3, 6, 3), 8: (0.75, 4, 8, 3),
    11: (0.75, 4, 8, 3), 12: (0.75, 4, 8, 3), 13: (0.75, 4, 8, 3),
    14: (0.75, 4, 8, 3), 15: (0.75, 4, 8, 3), 16: (0.75, 4, 8, 3),
}


def _is_formula(v) -> bool:
    return isinstance(v, str) and v.startswith("=")


def import_profile(xlsx_path: str, sheet: str = "4x") -> Profile:
    wb = openpyxl.load_workbook(xlsx_path)
    qs = wb["Quick Setup"]
    lifts = []

    # SBS main + aux from Quick Setup
    qs_rows = list(QS_MAIN_ROWS) + list(QS_AUX_ROWS)
    for r in qs_rows:
        name = qs[f"C{r}"].value
        one_rm = qs[f"D{r}"].value
        if not name or one_rm is None:
            continue
        intensity, reps, repout, sets = SBS_DEFAULTS[r]
        lifts.append(Lift(name=str(name), tier="sbs", day=0, max=float(one_rm),
                          intensity=intensity, reps=reps, repout=repout, sets=sets))

    # day index for each Accessories block
    ws = wb[sheet]
    acc_rows = [r for r in range(1, ws.max_row + 1)
                if ws.cell(row=r, column=1).value == "Accessories"]
    days_per_week = len(acc_rows)

    # back rows = non-formula name + numeric weight, immediately above each Accessories label
    for day_idx, label_row in enumerate(acc_rows, start=1):
        r = label_row - 1
        while r > 0:
            a = ws.cell(row=r, column=1).value
            b = ws.cell(row=r, column=2).value
            if a is None and b is None:
                r -= 1
                continue
            if isinstance(a, str) and not _is_formula(a) and isinstance(b, (int, float)):
                lifts.append(Lift(name=a, tier="t2", day=day_idx, start=float(b)))
                r -= 1
                continue
            break  # hit SBS formula rows or a Day label -> stop scanning up

    # accessories = non-formula name + numeric weight, in the rows below each Accessories label
    for day_idx, label_row in enumerate(acc_rows, start=1):
        next_boundary = (acc_rows[day_idx] if day_idx < len(acc_rows) else ws.max_row + 1)
        for r in range(label_row + 1, next_boundary):
            a = ws.cell(row=r, column=1).value
            b = ws.cell(row=r, column=2).value
            if isinstance(a, str) and not _is_formula(a) and isinstance(b, (int, float)):
                lifts.append(Lift(name=a, tier="t3", day=day_idx, start=float(b)))

    # assign days to SBS lifts: distribute round-robin across days by order (user edits after)
    day_counter = [0] * (days_per_week + 1)
    sbs_by_day_order = {}
    # simple assignment: main lifts spread by index across days
    sbs_lifts = [l for l in lifts if l.tier == "sbs"]
    for i, l in enumerate(sbs_lifts):
        l.day = (i % days_per_week) + 1

    return Profile(rounding=2.5, days_per_week=days_per_week, incr=2.5,
                   t2_reset_pct=0.70, t2_fail=3, t3_target=15, lifts=lifts)
```

- [ ] **Step 5: Run, verify PASS (4 tests).**
- [ ] **Step 6: Full suite gate.**

---

## Task 7: HTML view (week form + log JSON export/parse)

**Files:**
- Create: `sbs_cli/view/__init__.py` (empty), `sbs_cli/view/templates/week.html.j2`
- Create: `sbs_cli/view/html.py`
- Create: `tests/test_html.py`

- [ ] **Step 1: Write failing test `tests/test_html.py`:**

```python
import json
from sbs_cli.data.schema import Lift, Profile
from sbs_cli.program import initial_state
from sbs_cli.view.html import render_week_html, parse_log_json

def _profile():
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", tier="t2", day=1, start=50),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])

def test_render_html_has_input_per_lift_and_export_button():
    p = _profile(); s = initial_state(p)
    html = render_week_html(p, s, week=1)
    assert 'data-lift="Squat"' in html
    assert 'data-lift="Barbell rows"' in html
    assert 'data-lift="Curls"' in html
    assert "Export results" in html and "week-1-log.json" in html
    assert "est1RM" in html or "est 1RM" in html  # shows estimate

def test_render_html_shows_weights():
    p = _profile(); s = initial_state(p)
    html = render_week_html(p, s, week=1)
    assert "75" in html        # Squat working weight round(100*0.75)
    assert "50" in html        # Barbell rows start
    assert "40" in html        # Curls start

def test_parse_log_json_reads_filled_values_ignores_blanks():
    log = {"week": 1, "logs": {"Squat": 11, "Curls": 15}}   # Barbell rows blank
    parsed = parse_log_json(json.dumps(log))
    assert parsed["week"] == 1
    assert parsed["logs"] == {"Squat": 11, "Curls": 15}
    assert "Barbell rows" not in parsed["logs"]
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Create template `sbs_cli/view/templates/week.html.j2`:**

```html
<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Week {{ week }} plan</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;max-width:900px}
h2{margin-top:1.5em;border-bottom:1px solid #ccc}
.row{display:flex;gap:1em;align-items:center;padding:4px 0;flex-wrap:wrap}
.row .name{font-weight:bold;min-width:170px}
.row .meta{color:#555;font-size:0.92em}
input{width:70px;padding:4px}
button{margin-top:1em;padding:8px 14px;font-size:1em;cursor:pointer}
</style></head>
<body>
<h1>Week {{ week }} plan</h1>
<p>Fill in <b>last-set reps</b> after each session, then tap <b>Export results</b>.</p>
{% for day, items in by_day %}
<h2>Day {{ day }}</h2>
{% for it in items %}
<div class="row">
  <span class="name">{{ it.name }}</span>
  <span class="meta">{{ it.tier }}
    {% if it.tier == 'sbs' %} | {{ it.weight }} kg × {{ it.reps }} × {{ it.sets }} | rep-out target {{ it.repout }}
    {% elif it.tier == 't2' %} | {{ it.weight }} kg × {{ it.target }} × {{ it.sets }} | streak {{ it.streak }}
    {% else %} | {{ it.weight }} kg × {{ it.target }}+ × {{ it.sets }}
    {% endif %}
    {% if it.est1rm %} | est 1RM {{ "%.1f"|format(it.est1rm) }}{% endif %}
  </span>
  <label>last set reps: <input type="number" data-lift="{{ it.name }}"></label>
</div>
{% endfor %}
{% endfor %}
<button onclick="exportLog()">Export results (week {{ week }})</button>
<script>
function exportLog(){
  const logs = {};
  document.querySelectorAll('input[data-lift]').forEach(i => {
    const v = i.value.trim();
    if (v !== '') logs[i.dataset.lift] = Number(v);
  });
  const data = {week: {{ week }}, logs: logs};
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'week-{{ week }}-log.json';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
</script>
</body></html>
```

- [ ] **Step 4: Implement `sbs_cli/view/html.py`:**

```python
"""Render week-N.html (form + JS export) and parse exported log JSON."""
import json
import os
from jinja2 import Environment, FileSystemLoader
from ..program import week_plan

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=False)


def render_week_html(profile, state, week: int) -> str:
    by_day = []
    for day in range(1, profile.days_per_week + 1):
        items = week_plan(profile, state, day=day)
        if items:
            by_day.append((day, items))
    tmpl = _env.get_template("week.html.j2")
    return tmpl.render(week=week, by_day=by_day)


def parse_log_json(text: str) -> dict:
    """Parse a week-N-log.json. Returns {week: int, logs: {lift_name: reps}}."""
    data = json.loads(text)
    return {"week": int(data["week"]), "logs": {k: int(v) for k, v in data.get("logs", {}).items()}}
```

- [ ] **Step 5: Run, verify PASS (3 tests).**
- [ ] **Step 6: Full suite gate.**

---

## Task 8: Terminal view

**Files:**
- Create: `sbs_cli/view/terminal.py`
- Create: `tests/test_terminal.py`

- [ ] **Step 1: Write failing test `tests/test_terminal.py`:**

```python
from sbs_cli.data.schema import Lift, Profile
from sbs_cli.program import initial_state
from sbs_cli.view.terminal import render_week_text, render_show_text

def _profile():
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])

def test_render_week_text_has_day_and_lifts():
    p = _profile(); s = initial_state(p)
    txt = render_week_text(p, s, week=2)
    assert "Week 2" in txt
    assert "Squat" in txt and "75" in txt      # working weight
    assert "Curls" in txt and "40" in txt

def test_render_show_text_has_est1rm_and_history_count():
    p = _profile(); s = initial_state(p)
    # log one session so history/est1rm exist
    from sbs_cli.program import advance_lift
    advance_lift(p.lift("Squat"), s.lifts["Squat"], actual_reps=10, week=1)
    txt = render_show_text(p, s)
    assert "Squat" in txt and "est" in txt.lower()
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/view/terminal.py`:**

```python
"""Plain-text plan + status for the terminal."""
from ..program import week_plan


def render_week_text(profile, state, week: int) -> str:
    lines = [f"=== Week {week} ==="]
    for day in range(1, profile.days_per_week + 1):
        items = week_plan(profile, state, day=day)
        if not items:
            continue
        lines.append(f"\n-- Day {day} --")
        for it in items:
            est = f"  est1RM {it.est1rm:.1f}" if it.est1rm else ""
            if it.tier == "sbs":
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.reps} x {it.sets}  (repout {it.repout}){est}")
            elif it.tier == "t2":
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.target} x {it.sets}  (streak {it.streak}){est}")
            else:
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.target}+ x {it.sets}{est}")
    return "\n".join(lines)


def render_show_text(profile, state) -> str:
    lines = [f"=== Week {state.week} status ==="]
    for l in profile.lifts:
        ls = state.lifts.get(l.name)
        if not ls:
            continue
        hist = len(ls.history)
        est = f"  est1RM {ls.est1rm:.1f}" if ls.est1rm else ""
        if l.tier == "sbs":
            lines.append(f"{l.name:18} TM {ls.tm}  hist {hist}{est}")
        elif l.tier == "t2":
            lines.append(f"{l.name:18} {ls.weight} kg  3x{ls.target}  streak {ls.streak}  hist {hist}{est}")
        else:
            lines.append(f"{l.name:18} {ls.weight} kg  hist {hist}{est}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, verify PASS (2 tests).**
- [ ] **Step 5: Full suite gate.**

---

## Task 9: CLI (init / week / next / show) + end-to-end

**Files:**
- Create: `sbs_cli/cli.py`, `sbs_cli/__main__.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing end-to-end test `tests/test_cli.py`:**

```python
import os, json
from sbs_cli import cli

def test_full_flow_init_week_next_show(tmp_path, monkeypatch):
    prof = tmp_path / "profile.yaml"; st = tmp_path / "state.yaml"
    monkeypatch.chdir(tmp_path)

    # init from cold backup
    cli.run(["init", "--from", r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx",
             "--profile", str(prof), "--state", str(st)])
    assert prof.exists()
    # week 1 html
    cli.run(["week", "--profile", str(prof), "--state", str(st), "--out", "week-1.html"])
    assert (tmp_path / "week-1.html").exists()
    # synthesize a log: Squat beats repout, Barbell rows hits, Curls hits
    log = {"week": 1, "logs": {"Squat": 11, "Barbell rows": 10, "Leg Extension": 15}}
    logp = tmp_path / "week-1-log.json"; logp.write_text(json.dumps(log))
    # next
    cli.run(["next", str(logp), "--profile", str(prof), "--state", str(st), "--out", "week-2.html"])
    assert (tmp_path / "week-2.html").exists()
    # state advanced
    from sbs_cli.data import io as dio
    s = dio.load_state(str(st))
    assert s.week == 2
    # Squat beat repout 8 by 3 -> +1.5% on TM 135 -> 137.025 -> MROUND 137.5
    assert s.lifts["Squat"].tm == 137.5
    # Barbell rows hit -> +2.5 on 85
    assert s.lifts["Barbell rows"].weight == 87.5
    # show runs
    cli.run(["show", "--profile", str(prof), "--state", str(st)])
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `sbs_cli/cli.py`:**

```python
"""CLI entry: init / week / next / show."""
import argparse, sys
from .data import io as dio
from .program import initial_state, advance_lift, week_plan
from .importer import import_profile
from .view.html import render_week_html, parse_log_json
from .view.terminal import render_week_text, render_show_text


def _load(args):
    p = dio.load_profile(args.profile)
    if not __import__("os").path.exists(args.state):
        s = initial_state(p); dio.save_state(s, args.state)
    else:
        s = dio.load_state(args.state)
    return p, s


def cmd_init(args):
    p = import_profile(args.from_path, sheet=args.sheet)
    dio.save_profile(p, args.profile)
    s = initial_state(p); dio.save_state(s, args.state)
    print(f"profile -> {args.profile}  ({len(p.lifts)} lifts, {p.days_per_week} days)")
    print(f"state  -> {args.state}")
    print("Edit profile.yaml to taste (day, intensity, reps, repout).")


def cmd_week(args):
    p, s = _load(args)
    html = render_week_html(p, s, week=s.week)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(render_week_text(p, s, week=s.week))
    print(f"\n-> open {args.out} on your phone, fill last-set reps, tap Export results.")


def cmd_next(args):
    p, s = _load(args)
    with open(args.log, "r", encoding="utf-8") as f:
        log = parse_log_json(f.read())
    logs = log["logs"]
    for l in p.lifts:
        advance_lift(l, s.lifts[l.name], logs.get(l.name), week=s.week)
    s.week += 1
    dio.save_state(s, args.state)
    html = render_week_html(p, s, week=s.week)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"advanced to week {s.week} -> {args.out}")


def cmd_show(args):
    p, s = _load(args)
    print(render_show_text(p, s))


def build_parser():
    ap = argparse.ArgumentParser(prog="sbs")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default="profile.yaml")
    common.add_argument("--state", default="state.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init", parents=[common])
    a.add_argument("--from", dest="from_path", required=True)
    a.add_argument("--sheet", default="4x")
    a.set_defaults(func=cmd_init)

    a = sub.add_parser("week", parents=[common])
    a.add_argument("--out", default="week-N.html")
    a.set_defaults(func=cmd_week)

    a = sub.add_parser("next", parents=[common])
    a.add_argument("log")
    a.add_argument("--out", default="week-N.html")
    a.set_defaults(func=cmd_next)

    a = sub.add_parser("show", parents=[common])
    a.set_defaults(func=cmd_show)
    return ap


def run(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    run()
```

`sbs_cli/__main__.py`:
```python
from .cli import run
run()
```

- [ ] **Step 4: Run, verify PASS (1 end-to-end test).**
- [ ] **Step 5: Full suite gate** — `conda run --no-capture-output -n tamp python -m pytest tests/ -v` all green.

---

## Task 10: Manual smoke run on real data + README

**Files:**
- Create: `README_sbs_cli.md`
- Run the tool end-to-end on the user's real cold-backup data.

- [ ] **Step 1: Run `init` against the real cold backup**

```bash
cd "D:\WorkSpace\sbs"
conda run --no-capture-output -n tamp python -m sbs_cli init --from backup/00_cold_backup.xlsx --profile profile.yaml --state state.yaml
```
Expected: prints "N lifts, 4 days"; `profile.yaml` + `state.yaml` created. Open `profile.yaml` and confirm: Squat max 135, Bench 120, DL 145, OHP 73; Barbell rows/DB rows/Pull-downs/Chin-ups as t2; Leg Extension/Leg Curl/Farmer's Walk/Dips/Face Pull/etc. as t3.

- [ ] **Step 2: Generate week 1 and eyeball the HTML**

```bash
conda run --no-capture-output -n tamp python -m sbs_cli week --profile profile.yaml --state state.yaml --out week-1.html
```
Open `week-1.html` in a browser. Confirm: every lift has a row + an input field; weights look right (Squat ~ round(135×0.75)=102.5 if intensity 0.75); est1RM blank on week 1 (no history yet); "Export results" button present.

- [ ] **Step 3: Simulate a filled log + advance**

Create `week-1-log.json` with at least one hit and one miss (e.g. `{"week":1,"logs":{"Squat":11,"Barbell rows":10,"Leg Extension":15}}`), then:
```bash
conda run --no-capture-output -n tamp python -m sbs_cli next week-1-log.json --profile profile.yaml --state state.yaml --out week-2.html
conda run --no-capture-output -n tamp python -m sbs_cli show --profile profile.yaml --state state.yaml
```
Confirm: state.yaml week=2; Squat TM up (beat repout by 3 → +1.5%); Barbell rows +2.5; Leg Extension +2.5; est1RM now populated for the logged lifts. Open `week-2.html` to see progressed weights.

- [ ] **Step 4: Write `README_sbs_cli.md`** — short usage doc:

```markdown
# SBS/GZCLP Training CLI

One-time setup (from your existing 4x spreadsheet):
    conda run -n tamp python -m sbs_cli init --from backup/00_cold_backup.xlsx --profile profile.yaml --state state.yaml
    # then edit profile.yaml to taste

Weekly loop:
    conda run -n tamp python -m sbs_cli week   # prints plan + writes week-N.html
    # open week-N.html on your phone, fill last-set reps, tap "Export results"
    conda run -n tamp python -m sbs_cli next week-N-log.json   # advances, writes week-(N+1).html

Check status:
    conda run -n tamp python -m sbs_cli show

Tiers:
- sbs (main/aux): TM autoregulates by rep-out delta (-5%..+3%)
- t2  (back): 3x10 -> 3x8 -> 3x6 on 3 misses; full reset = 70% x est1RM(best set)
- t3  (accessories): last set >= 15 -> +2.5kg, else repeat
est1RM = mean(Epley, Brzycki, Wathan)
```

- [ ] **Step 5: Clean up scratch outputs** (`week-1.html`, `week-2.html`, `week-1-log.json` if you want; or keep them as a demo). The deliverable is the `sbs_cli/` package + `profile.yaml`/`state.yaml` template flow.

- [ ] **Step 6: User acceptance** — hand off: user runs `init`, opens `week-1.html` on their phone, fills a real session, runs `next`, confirms next week's numbers match expectation.

---

## Done criteria

- Full pytest suite passes (onerm 6 + progression 17 + schema 5 + io 2 + program 6 + importer 4 + html 3 + terminal 2 + cli 1 = 46 tests).
- `python -m sbs_cli init --from backup/00_cold_backup.xlsx` produces a `profile.yaml` containing the user's real 1RMs + back lifts + accessories.
- `week` → `next` round-trip produces correct progressed weights (SBS delta, T2 state machine incl. est1RM reset, T3 threshold).
- HTML opens offline on a phone, every lift has an input, Export button downloads `week-N-log.json`, and `next` reads it.
- `README_sbs_cli.md` documents the setup + weekly loop.
- The old spreadsheet is no longer needed for day-to-day use.
