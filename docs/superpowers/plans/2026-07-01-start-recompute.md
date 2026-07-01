# Start-Weight Recompute + T2 8→6→4 Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `lifts.start` the progression basis for t2/t3: editing it recomputes the current working weight by replaying progression from the new start over the immutable history. Also extend the T2 failure cascade to 8→6→4 with a 75% reset.

**Architecture:** A pure engine function `recompute_state(lift, history, profile)` replays `t2_next`/`t3_next` from `start` over history (reps drive decisions; est1rm stays derived from real history weights). A thin webapp service wraps it, triggered from `lifts.py:edit` when `start` is submitted for a t2/t3 lift. The T2 rule change (8→6→4 + reset_pct 0.70→0.75) is a separate engine edit shipped first. A one-shot migration bumps `t2_reset_pct` and resyncs every t2/t3 `lift_state.weight`.

**Tech Stack:** Python 3.12 (conda env `sbs`), Flask + Jinja2 + HTMX, sqlite3 (stdlib), pytest. All test commands run as `conda run -n sbs python -m pytest ...`.

**Spec:** `docs/superpowers/specs/2026-07-01-start-recompute-design.md`

---

## File Map

- **Modify** `sbs_cli/engine/progression.py` — `t2_next`: add 6→4 level, `reset_pct` default 0.70→0.75.
- **Modify** `sbs_cli/data/schema.py` — `Profile.t2_reset_pct` default 0.70→0.75.
- **Modify** `webapp/db.py` — `_DEFAULT_SETTINGS["t2_reset_pct"]` 0.70→0.75.
- **Modify** `sbs_cli/program.py` — add pure `recompute_state(lift, history, profile)`.
- **Create** `webapp/services/recompute.py` — `recompute_on_start_change(conn, lift_id, new_start)`.
- **Modify** `webapp/routes/lifts.py` — `edit()`: trigger recompute when t2/t3 + `start` submitted.
- **Create** `migrate_recompute.py` — one-shot: backup, `t2_reset_pct`=0.75, resync t2/t3 weights.
- **Modify** `tests/test_progression.py` — rewrite T2 section for 8→6→4 + 75%.
- **Modify** `tests/test_program.py` — update 2 T2 reset tests (force target=4); add `recompute_state` tests.
- **Modify** `tests/test_db.py` — default `t2_reset_pct` 0.7→0.75.
- **Modify** `tests/test_schema.py` — `Profile.t2_reset_pct` 0.70→0.75.
- **Create** `tests/test_recompute_service.py` — service unit tests.
- **Create** `tests/test_migrate_recompute.py` — migration end-to-end test.
- **Modify** `tests/test_routes_lifts.py` — edit-start recompute route tests.

---

## Task 1: T2 cascade 8→6→4 + reset_pct 0.75 (engine + defaults)

**Files:**
- Modify: `sbs_cli/engine/progression.py:48-59` (`t2_next`)
- Modify: `sbs_cli/data/schema.py:27` (`Profile.t2_reset_pct`)
- Modify: `webapp/db.py:63-66` (`_DEFAULT_SETTINGS`)
- Modify: `tests/test_progression.py:42-71` (rewrite T2 section)
- Modify: `tests/test_db.py:13`
- Modify: `tests/test_schema.py:13`
- Modify: `tests/test_program.py:42-53` and `tests/test_program.py:76-86` (2 reset tests)

- [ ] **Step 1: Rewrite the T2 section of `tests/test_progression.py`**

Replace lines 42–71 (from the `# --- T3 ...` no — from the T2 comment through `test_t2_no_log_carries_state`) with:

```python
# --- T2 (state machine: 4x8 -> 4x6 -> 4x4 -> reset, est1rm reset @75%) ---
def test_t2_hit_adds_weight_keeps_tier():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=52.5)


def test_t2_miss_under_threshold_accumulates():
    s = t2_next(T2State(target=8, streak=1, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=8, streak=2, weight=50)


def test_t2_three_misses_8_drops_to_6():
    s = t2_next(T2State(target=8, streak=2, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=0, weight=50)


def test_t2_three_misses_6_drops_to_4():
    s = t2_next(T2State(target=6, streak=2, weight=50), actual=4, est1rm=100)
    assert s == T2State(target=4, streak=0, weight=50)


def test_t2_three_misses_4_resets_to_75pct_of_est1rm():
    # 0.75 * 100 = 75 -> MROUND(75, 2.5) = 75
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=75)


def test_t2_reset_uses_est1rm_not_old_weight():
    # est1rm 110 -> 0.75*110 = 82.5 -> MROUND(82.5, 2.5) = 82.5
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=110)
    assert s == T2State(target=8, streak=0, weight=82.5)


def test_t2_no_log_carries_state():
    s = t2_next(T2State(target=8, streak=1, weight=50), actual=None, est1rm=100)
    assert s == T2State(target=8, streak=1, weight=50)
```

- [ ] **Step 2: Run test_progression — verify the new T2 tests fail**

Run: `conda run -n sbs python -m pytest tests/test_progression.py -v`
Expected: FAIL — `test_t2_three_misses_6_drops_to_4`, `test_t2_three_misses_4_resets_to_75pct_of_est1rm`, `test_t2_reset_uses_est1rm_not_old_weight` fail (impl still 8→6 with 0.70 reset).

- [ ] **Step 3: Implement the new `t2_next`**

Replace `sbs_cli/engine/progression.py:48-59` (the whole `t2_next` function) with:

```python
def t2_next(state: T2State, actual, est1rm: float, fail: int = 3,
            incr: float = 2.5, reset_pct: float = 0.75, quantum: float = 2.5) -> T2State:
    """GZCLP-modified T2 back: 4x8 -> 4x6 -> 4x4 cascade; reset = reset_pct * est1rm, back to 8."""
    if actual is None:
        return state
    if actual >= state.target:                                   # hit
        return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
    if state.streak + 1 >= fail:                                 # Nth consecutive miss
        if state.target == 8:
            return T2State(6, 0, state.weight)                   # 4x8 -> 4x6
        if state.target == 6:
            return T2State(4, 0, state.weight)                   # 4x6 -> 4x4
        return T2State(8, 0, round_weight(est1rm * reset_pct, quantum))  # at 4 -> reset to 8
    return T2State(state.target, state.streak + 1, state.weight) # miss, under threshold
```

- [ ] **Step 4: Run test_progression — verify pass**

Run: `conda run -n sbs python -m pytest tests/test_progression.py -v`
Expected: PASS (all T2 cases green).

- [ ] **Step 5: Bump the reset_pct defaults to 0.75**

In `sbs_cli/data/schema.py:27`, change:
```python
    t2_reset_pct: float = 0.70
```
to:
```python
    t2_reset_pct: float = 0.75
```

In `webapp/db.py:63-66`, change the `t2_reset_pct=0.7` line inside `_DEFAULT_SETTINGS` to `0.75`:
```python
_DEFAULT_SETTINGS = dict(
    week=1, days_per_week=4, rounding=2.5, incr=2.5,
    t2_reset_pct=0.75, t2_fail=3, t3_target=15,
)
```

- [ ] **Step 6: Update the two default-asserting tests**

In `tests/test_db.py:13`, change `s["t2_reset_pct"] == 0.7` to `s["t2_reset_pct"] == 0.75`:
```python
    assert s["incr"] == 2.5 and s["t2_reset_pct"] == 0.75 and s["t2_fail"] == 3 and s["t3_target"] == 15
```

In `tests/test_schema.py:13`, change `p.t2_reset_pct == 0.70` to `0.75`:
```python
    assert p.rounding == 2.5 and p.days_per_week == 4 and p.t2_reset_pct == 0.75
```

- [ ] **Step 7: Update the two T2 reset tests in `tests/test_program.py`**

Replace `tests/test_program.py:42-53` (`test_advance_t2_reset_uses_best_set_est1rm`) with:

```python
def test_advance_t2_reset_uses_best_set_est1rm():
    from sbs_cli.engine.progression import round_weight
    p = _profile(); s = initial_state(p)
    ls = s.lifts["Barbell rows"]
    # seed a best set: 50x10 -> est1rm ~ 67
    advance_lift(p, p.lift("Barbell rows"), ls, actual_reps=10, week=1)
    est = ls.est1rm
    # now force 3 consecutive misses at the bottom (target 4) -> reset @ 75%
    ls.target, ls.streak = 4, 2
    advance_lift(p, p.lift("Barbell rows"), ls, actual_reps=3, week=4)   # 3rd miss at 4 -> reset
    assert ls.target == 8 and ls.streak == 0
    assert ls.weight == round_weight(est * 0.75)                      # 0.75*est, MROUND 2.5
```

Replace `tests/test_program.py:76-86` (`test_advance_t2_reset_uses_profile_reset_pct`) with:

```python
def test_advance_t2_reset_uses_profile_reset_pct():
    from sbs_cli.engine.progression import round_weight
    # non-default reset_pct=0.60
    p = Profile(t2_reset_pct=0.60, lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    s = initial_state(p)
    ls = s.lifts["Row"]
    advance_lift(p, p.lift("Row"), ls, actual_reps=10, week=1)   # seed best set 50x10
    est = ls.est1rm
    ls.target, ls.streak = 4, 2
    advance_lift(p, p.lift("Row"), ls, actual_reps=3, week=4)    # 3rd miss @4 -> reset
    assert ls.weight == round_weight(est * 0.60)                 # uses 0.60, not default 0.75
```

- [ ] **Step 8: Run the full suite — verify all green**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS (all tests, including the updated default + reset tests). If any other test references the old 0.70 default or a 6→reset path, update it the same way (the grep in planning found only the files above).

- [ ] **Step 9: Commit**

```bash
git add sbs_cli/engine/progression.py sbs_cli/data/schema.py webapp/db.py \
        tests/test_progression.py tests/test_program.py tests/test_db.py tests/test_schema.py
git commit -m "feat: T2 cascade 8->6->4 + reset 75%

t2_next gains the 4x6->4x4 level; reset from target 4 = est1rm*0.75
(default reset_pct 0.70->0.75 in progression, Profile, _DEFAULT_SETTINGS).
Updates all T2 reset/default tests to the new rule."
```

---

## Task 2: Engine `recompute_state` (pure replay from start)

**Files:**
- Modify: `sbs_cli/program.py` (add `recompute_state`)
- Modify: `tests/test_program.py` (add recompute tests + import)

- [ ] **Step 1: Write the failing tests**

In `tests/test_program.py`, add to the top import line (line 2) so it reads:
```python
from sbs_cli.program import best_1rm, initial_state, advance_lift, week_plan, recompute_state
```

Append these tests at the end of `tests/test_program.py`:

```python
def test_recompute_state_t3_replays_hits_and_misses():
    from sbs_cli.program import _est1rm_from_history
    p = Profile(lifts=[Lift(name="Curls", tier="t3", day=1, start=40)])
    lift = p.lift("Curls")
    hist = [SetEntry(1, 42.5, 16), SetEntry(2, 45.0, 14), SetEntry(3, 45.0, 16)]
    ls = recompute_state(lift, hist, p)
    # replay from 40: w1 16>=15 hit -> 42.5; w2 14<15 miss -> 42.5; w3 16>=15 hit -> 45.0
    assert ls.tier == "t3" and ls.weight == 45.0 and ls.target is None and ls.streak == 0
    # est1rm drawn from the real history weights (Option A) -- unchanged by start
    assert ls.est1rm == _est1rm_from_history(hist)


def test_recompute_state_t2_all_hits_increments_from_start():
    from sbs_cli.program import _est1rm_from_history
    p = Profile(lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    lift = p.lift("Row")
    hist = [SetEntry(1, 50.0, 8), SetEntry(2, 52.5, 8), SetEntry(3, 55.0, 8)]
    ls = recompute_state(lift, hist, p)
    # 3 hits @ target 8 -> 50 -> 52.5 -> 55.0 -> 57.5
    assert ls.weight == 57.5 and ls.target == 8 and ls.streak == 0
    assert ls.est1rm == _est1rm_from_history(hist)


def test_recompute_state_t2_cascade_drops_to_6():
    p = Profile(lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    lift = p.lift("Row")
    # 3 consecutive misses at target 8 (reps 5 < 8) -> drop to target 6, weight unchanged
    hist = [SetEntry(1, 50.0, 5), SetEntry(2, 50.0, 5), SetEntry(3, 50.0, 5)]
    ls = recompute_state(lift, hist, p)
    assert ls.target == 6 and ls.streak == 0 and ls.weight == 50.0


def test_recompute_state_empty_history_seeds_start():
    p = Profile(lifts=[
        Lift(name="Row", tier="t2", day=1, start=65),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])
    assert recompute_state(p.lift("Row"), [], p) == LiftState(
        name="Row", tier="t2", weight=65, target=8, streak=0, est1rm=None, history=[])
    assert recompute_state(p.lift("Curls"), [], p) == LiftState(
        name="Curls", tier="t3", weight=40, target=None, streak=0, est1rm=None, history=[])


def test_recompute_state_sbs_raises():
    import pytest
    p = Profile(lifts=[Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8)])
    with pytest.raises(ValueError):
        recompute_state(p.lift("Squat"), [], p)
```

- [ ] **Step 2: Run the new tests — verify they fail**

Run: `conda run -n sbs python -m pytest tests/test_program.py -k recompute -v`
Expected: FAIL — `ImportError: cannot import name 'recompute_state'`.

- [ ] **Step 3: Implement `recompute_state` in `sbs_cli/program.py`**

Append at the end of `sbs_cli/program.py`:

```python
def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``
    over ``history``. History rows are immutable facts; only their reps drive the
    replay. ``est1rm`` is computed from the real history weights (unchanged by the
    new start). Not applicable to sbs (sbs has no start-based progression)."""
    est = _est1rm_from_history(history)
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target,
                             incr=profile.incr, quantum=profile.rounding)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1]) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=profile.incr,
                         reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")
```

- [ ] **Step 4: Run the recompute tests — verify pass**

Run: `conda run -n sbs python -m pytest tests/test_program.py -k recompute -v`
Expected: PASS (all 5 recompute tests green).

- [ ] **Step 5: Run full suite — verify no regressions**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "feat: engine recompute_state replays t2/t3 from start

Pure function: seeds (target=8,streak=0,weight=start) and applies
t2_next/t3_next over history reps; est1rm stays from real history
weights (immutable history). sbs raises ValueError."
```

---

## Task 3: Webapp recompute service

**Files:**
- Create: `webapp/services/recompute.py`
- Create: `tests/test_recompute_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_recompute_service.py`:

```python
from webapp import db, repo
from webapp.services import recompute as recompute_service


def _t2(conn, start=85.0):
    return repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                            sets=4, max=None, intensity=None, reps=None, repout=None, start=start)


def test_recompute_t2_no_history_sets_weight_to_start(tmp_path):
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = _t2(conn, start=85.0)
    recompute_service.recompute_on_start_change(conn, lid, 65.0)  # lower the start
    st = repo.get_lift_state(conn, lid)
    assert st["weight"] == 65.0 and st["target"] == 8 and st["streak"] == 0
    conn.close()


def test_recompute_sbs_is_noop(tmp_path):
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    tm_before = repo.get_lift_state(conn, lid)["tm"]
    assert recompute_service.recompute_on_start_change(conn, lid, 100.0) is None
    assert repo.get_lift_state(conn, lid)["tm"] == tm_before  # sbs untouched
    conn.close()


def test_recompute_preserves_est1rm_from_history(tmp_path):
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = _t2(conn, start=50.0)
    for wk, w, r in [(1, 50.0, 10), (2, 52.5, 8)]:
        repo.append_history(conn, lid, week=wk, weight=w, reps=r)
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lid)]
    expected_est = _est1rm_from_history(hist)
    recompute_service.recompute_on_start_change(conn, lid, 55.0)  # change start; est1rm must not move
    assert repo.get_lift_state(conn, lid)["est1rm"] == expected_est
    conn.close()
```

- [ ] **Step 2: Run the service tests — verify they fail**

Run: `conda run -n sbs python -m pytest tests/test_recompute_service.py -v`
Expected: FAIL — `ModuleNotFoundError: webapp.services.recompute`.

- [ ] **Step 3: Implement the service**

Create `webapp/services/recompute.py`:

```python
"""Recompute a t2/t3 lift's working weight by replaying progression from its
configured start over the immutable history. Triggered when ``start`` is edited
in the lift CRUD (see webapp/routes/lifts.py::edit)."""
import sqlite3

from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state
from .. import repo
from . import advance as advance_service


def recompute_on_start_change(conn: sqlite3.Connection, lift_id: int, new_start: float):
    """Replay t2/t3 progression from ``new_start`` over history and write the
    recomputed ``lift_state``. Returns the recomputed LiftState, or ``None`` for
    sbs lifts (no start-based progression -> no-op)."""
    lift_row = repo.get_lift(conn, lift_id)
    if lift_row["tier"] not in ("t2", "t3"):
        return None
    settings = repo.get_settings(conn)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    lift = advance_service._lift_from_row(lift_row)
    lift.start = new_start  # authoritative; the lifts row already holds it post-update
    profile = advance_service._profile_from_rows(settings, [])  # globals only
    ls = recompute_state(lift, history, profile)
    repo.save_lift_state(conn, lift_id, tier=ls.tier, tm=None, weight=ls.weight,
                         target=ls.target, streak=ls.streak, est1rm=ls.est1rm)
    return ls
```

- [ ] **Step 4: Run the service tests — verify pass**

Run: `conda run -n sbs python -m pytest tests/test_recompute_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/services/recompute.py tests/test_recompute_service.py
git commit -m "feat: recompute service replays t2/t3 weight on start edit

webapp/services/recompute.recompute_on_start_change wraps the engine
recompute_state; no-op for sbs; preserves est1rm from real history."
```

---

## Task 4: Wire the edit-route trigger

**Files:**
- Modify: `webapp/routes/lifts.py:48-59` (`edit`)
- Modify: `tests/test_routes_lifts.py` (append 2 tests)

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_routes_lifts.py`:

```python
def _t2_lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=85.0)
    conn.close()
    return lid


def test_edit_start_t2_recomputes_weight(client, app):
    lid = _t2_lift(app)  # created with start=85 -> lift_state.weight seeded 85
    rv = client.post(f"/lifts/{lid}/edit", data={"start": "65"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_state(conn, lid)["weight"] == 65.0  # recomputed to new start
        conn.close()


def test_edit_start_sbs_does_not_recompute(client, app):
    lid = _lift(app)  # sbs Squat
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        tm_before = repo.get_lift_state(conn, lid)["tm"]
        conn.close()
    client.post(f"/lifts/{lid}/edit", data={"start": "100"})
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_state(conn, lid)["tm"] == tm_before  # sbs tm unchanged
        conn.close()
```

- [ ] **Step 2: Run the route tests — verify the t2 one fails**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -v`
Expected: FAIL — `test_edit_start_t2_recomputes_weight` (weight stays 85; recompute not wired).

- [ ] **Step 3: Wire the trigger in `edit`**

Replace `webapp/routes/lifts.py:48-59` (the whole `edit` function) with:

```python
@bp.route("/lifts/<int:lid>/edit", methods=["POST"])
def edit(lid):
    conn = get_db()
    fields = {}
    for col, cast in (("name", str), ("tier", str), ("day", int), ("sets", int),
                      ("max", float), ("intensity", float), ("reps", int),
                      ("repout", int), ("start", float)):
        if col in request.form and request.form[col].strip() != "":
            fields[col] = cast(request.form[col])
    repo.update_lift(conn, lid, **fields)
    lift = repo.get_lift(conn, lid)
    # start is the progression basis for t2/t3: replay from the new start over
    # history to resync the working weight. Idempotent (no-op effect if start
    # unchanged). sbs has no start-based progression -> skipped.
    if lift["tier"] in ("t2", "t3") and "start" in fields:
        from ..services import recompute as recompute_service
        recompute_service.recompute_on_start_change(conn, lid, lift["start"])
    return render_template("_lift_row.html", lift=lift)
```

- [ ] **Step 4: Run the route tests — verify pass**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -v`
Expected: PASS (all route tests, including the 2 new ones).

- [ ] **Step 5: Run full suite**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/lifts.py tests/test_routes_lifts.py
git commit -m "feat: editing start recomputes t2/t3 working weight

lifts.edit triggers recompute_on_start_change for t2/t3 when start is
submitted; idempotent. Fixes plan showing stale weight after start edit."
```

---

## Task 5: One-shot migration (reset_pct 0.75 + resync weights)

**Files:**
- Create: `migrate_recompute.py`
- Create: `tests/test_migrate_recompute.py`

- [ ] **Step 1: Write the failing migration test**

Create `tests/test_migrate_recompute.py`:

```python
from webapp import db, repo
import migrate_recompute


def _seed(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    # a divergent t2 lift: configured start 65, but state.weight stuck at 85 (the bug)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=65.0)
    repo.save_lift_state(conn, lid, tier="t2", tm=None, weight=85.0,
                         target=8, streak=0, est1rm=None)
    conn.close()
    return lid


def test_migrate_bumps_reset_pct_and_syncs_weight(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_recompute.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_settings(conn)["t2_reset_pct"] == 0.75
    assert repo.get_lift_state(conn, lid)["weight"] == 65.0  # replayed to start (no history)
    conn.close()


def test_migrate_creates_backup(tmp_path):
    dbp = str(tmp_path / "t.db")
    _seed(dbp)
    bdir = tmp_path / "bak"
    migrate_recompute.main(db_path=dbp, backup_dir=str(bdir))
    backups = list(bdir.glob("*.db.bak"))
    assert len(backups) == 1
```

- [ ] **Step 2: Run the migration test — verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_migrate_recompute.py -v`
Expected: FAIL — `ModuleNotFoundError: migrate_recompute`.

- [ ] **Step 3: Implement the migration script**

Create `migrate_recompute.py`:

```python
"""One-shot migration: bump t2_reset_pct 0.70 -> 0.75 and resync every t2/t3
lift_state.weight to a replay from its configured start over history. Backs up
the db first. Idempotent (re-running re-derives the same state).

Run:  conda run -n sbs python migrate_recompute.py
      conda run -n sbs python migrate_recompute.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sys
from datetime import datetime, timezone

from webapp import db, repo
from webapp.services import recompute as recompute_service


def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-start-recompute-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    db.init_schema(conn)
    repo.update_settings(conn, t2_reset_pct=0.75)
    print("settings.t2_reset_pct -> 0.75")

    n = 0
    for row in repo.list_lifts(conn):
        if row["tier"] in ("t2", "t3"):
            recompute_service.recompute_on_start_change(conn, row["id"], row["start"])
            n += 1
    conn.close()
    print(f"recomputed {n} t2/t3 lifts from start -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_recompute")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
```

- [ ] **Step 4: Run the migration test — verify pass**

Run: `conda run -n sbs python -m pytest tests/test_migrate_recompute.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the migration against the live `sbs.db` and verify**

Run: `conda run -n sbs python migrate_recompute.py`
Expected output: a backup line, `settings.t2_reset_pct -> 0.75`, and `recomputed 4 t2/t3 lifts from start -> sbs.db` (4 T2 lifts; history empty so each weight becomes its start — Barbell rows 85→65).

Verify:
```bash
sqlite3 sbs.db "SELECT t2_reset_pct FROM settings WHERE id=1;"   # -> 0.75
sqlite3 sbs.db "SELECT l.name, l.start, ls.weight FROM lifts l JOIN lift_state ls ON l.id=ls.lift_id WHERE l.tier IN ('t2','t3');"
```
Expected: every row has `start == weight` (Barbell rows both 65.0).

- [ ] **Step 6: Run the full suite once more**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add migrate_recompute.py tests/test_migrate_recompute.py
git commit -m "feat: one-shot migrate_recompute (reset_pct 0.75 + weight resync)

Bumps settings.t2_reset_pct to 0.75 and replays every t2/t3 lift from
its configured start over history (clears the Barbell rows 85/65 split
and any latent start/weight divergence). Backs up sbs.db first."
```

---

## Final verification

- [ ] **Full suite green:** `conda run -n sbs python -m pytest -v`
- [ ] **Manual smoke test:** run the app (`conda run -n sbs python -m webapp`), open 动作管理, edit a t2 lift's `start`, save, then view the plan (`/`) — the working weight matches the new start. Edit a t2 lift's `start` to a value, log a few weeks via `/log`, then edit `start` again and confirm the plan weight recomputes through the history.
- [ ] **sbs regression:** edit an sbs lift's `start` (or any field) and confirm the plan weight (`tm × intensity`) is unaffected.

## Notes for the implementer

- All `pytest` commands must run under the conda env `sbs` (memory: env created empty; install Flask/pytest there if missing — `conda run -n sbs pip install flask openpyxl pytest`).
- Do NOT `git add -A` (user global rule). Add only the explicit paths listed in each commit step.
- The engine change (Task 1) intentionally alters proven behavior the user requested; the updated tests encode the new contract.
- `recompute_state` is the single source of truth for "given (start, history, settings), what is the current t2/t3 state?" — the service and migration both call it, so they cannot drift.
