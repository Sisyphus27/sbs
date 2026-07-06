# SBS TM-Rounding Fix + est1RM 2-Decimal Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SBS Training Max accumulate raw (xlsx-faithful), show est1RM to 2 decimals on every surface, correct stored rounded TMs via a one-shot migration, and relabel the gym-increment setting.

**Architecture:** Engine (`sbs_cli/`) stays pure; `sbs_next` drops its `quantum` param and returns raw `tm × (1+delta)`. A new pure `recompute_sbs_tm(lift, history)` lives in `sbs_cli/program.py` next to `recompute_state`; an I/O wrapper in `webapp/services/recompute.py` mirrors `recompute_on_start_change`, and a root-level `migrate_sbs_tm.py` (mirroring `migrate_recompute.py`) orchestrates the one-shot DB fix. Display rounding is applied only in view/templates. See [ADR 0001](../../adr/0001-tm-accumulates-raw.md) and [CONTEXT.md](../../../CONTEXT.md).

**Tech Stack:** Python 3, Flask + Jinja2 + HTMX (`webapp/`), SQLite, pytest, conda env `sbs`.

## Global Constraints

- **Python runs in conda env `sbs`:** every `python`/`pytest` invocation is `conda run -n sbs python ...`. Tests run from repo root: `conda run -n sbs python -m pytest tests/ -v`.
- **TDD red-green-refactor** for every behavior change.
- **Conventional commits** (`feat:`/`fix:`/`test:`/`docs:`/`refactor:`); attribution disabled globally. Commit per task.
- **Engine purity:** `sbs_cli/program.py` and `sbs_cli/engine/**` import NO sqlite / webapp code. Repo I/O lives in `webapp/services/**`.
- **Immutability:** prefer returning new objects; do not mutate inputs except the documented in-place `advance_lift` state mutation.
- **Chinese UI copy** in `webapp/templates/**` (existing convention).
- **`rounding` quantum applies ONLY to loaded weights**, never to TM. This is the core invariant — do not re-introduce `quantum=` into `sbs_next`.

**Branch:** `feat/sbs-tm-rounding-fix` (already checked out).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `sbs_cli/engine/progression.py` | pure progression fns; `sbs_next` drops `quantum`, returns raw TM | modify |
| `sbs_cli/program.py` | engine↔state glue; `advance_lift` caller; new `recompute_sbs_tm` pure fn | modify |
| `webapp/services/recompute.py` | repo I/O wrapper `recompute_sbs_tm(conn, lid)` | modify |
| `migrate_sbs_tm.py` | one-shot DB migration orchestrator (backup + loop) | create |
| `webapp/routes/plan.py` | est1RM live-preview f-string formatting | modify |
| `webapp/templates/plan.html` | est1RM cell formatting | modify |
| `webapp/templates/week_export.html` | est1RM + live cell formatting | modify |
| `webapp/templates/tier_preview.html` | est1RM cell formatting | modify |
| `webapp/templates/settings.html` | relabel `rounding` field; link `incr` spinner step | modify |
| `sbs_cli/view/terminal.py` | est1RM 2-dec + TM 1-dec text formatting | modify |
| `sbs_cli/view/templates/week.html.j2` | est1RM cell formatting | modify |
| `tests/test_progression.py` | flip 3 `sbs_next` expectations to raw | modify |
| `tests/test_program.py` | flip `:39` tm assertion; add regression test | modify |
| `tests/test_migrate_sbs_tm.py` | migration idempotency + est1rm-untouched + backup | create |
| `tests/test_terminal.py`, `tests/test_html.py`, `tests/test_routes_plan.py` | lock 2-decimal est1RM rendering | modify |
| `tests/test_routes_settings.py` | lock new `最小变动` label | modify |

Already complete (do not touch in this plan): `CONTEXT.md`, `docs/adr/0001-tm-accumulates-raw.md`, the spec `docs/superpowers/specs/2026-07-06-sbs-tm-rounding-and-est1rm-display-design.md`.

---

## Task 1: Core fix — `sbs_next` keeps TM full-precision

**Files:**
- Modify: `sbs_cli/engine/progression.py:24-28` (`sbs_next`)
- Modify: `sbs_cli/program.py:48` (caller — drop `quantum=`)
- Modify: `tests/test_progression.py:13-30` (3 expectations flip)
- Modify: `tests/test_program.py:38-39` (tm assertion flips) + append new regression test

**Interfaces:**
- Produces: `sbs_next(tm: float, repout: int, actual) -> float` (raw; `actual=None` ⇒ unchanged). No `quantum` param.

- [ ] **Step 1: Flip the 3 `sbs_next` expectations in `tests/test_progression.py`**

Replace the body of these three tests (the other three — `test_sbs_hit_keeps_tm`, `test_sbs_miss_drops_pct`, `test_sbs_no_log_keeps_tm` — stay unchanged):

```python
def test_sbs_beat_adds_pct():
    # beat target 8 by 3 -> +1.5% -> 100*1.015 = 101.5 (raw, TM never rounded)
    assert sbs_next(tm=100, repout=8, actual=11) == 101.5

def test_sbs_beat_5_plus_caps_at_3pct():
    # beat by 6 -> +3% -> 100*1.03 = 103.0 (raw)
    assert sbs_next(tm=100, repout=8, actual=14) == 103.0

def test_sbs_miss_by_1_drops_2pct():
    # diff -1 -> -2% -> 100*0.98 = 98.0 (raw)
    assert sbs_next(tm=100, repout=8, actual=7) == 98.0
```

- [ ] **Step 2: Flip the tm assertion in `tests/test_program.py:38-39`**

```python
    # TM progressed: beat repout 8 by 3 -> +1.5% -> 100*1.015 = 101.5 (raw, no MROUND)
    assert s.lifts["Squat"].tm == 101.5
```

- [ ] **Step 3: Run the affected tests — expect FAIL (old impl still rounds)**

Run: `conda run -n sbs python -m pytest tests/test_progression.py tests/test_program.py -v`
Expected: 3 failures in `test_progression.py` (`102.5 != 101.5`, etc.) and 1 failure in `test_program.py::test_advance_sbs_appends_history_and_updates_est1rm` (`102.5 != 101.5`).

- [ ] **Step 4: Implement — drop `quantum` from `sbs_next`**

In `sbs_cli/engine/progression.py`, replace the `sbs_next` definition:

```python
def sbs_next(tm: float, repout: int, actual) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged.

    TM is kept full-precision to match the SBS RTF xlsx (which rounds only the
    working weight, not the TM). Rounding the TM here stalls upward progression
    because sub-quantum weekly deltas are discarded before they accumulate.
    The working weight is rounded to the gym increment in week_plan / the webapp.
    See ADR 0001.
    """
    if actual is None:
        return tm
    return tm * (1 + _sbs_delta(actual - repout))
```

- [ ] **Step 5: Drop the `quantum=` argument at the caller**

In `sbs_cli/program.py:48`, change:

```python
        state.tm = sbs_next(state.tm, lift.repout, actual_reps, quantum=profile.rounding)
```

to:

```python
        state.tm = sbs_next(state.tm, lift.repout, actual_reps)
```

- [ ] **Step 6: Run the affected tests — expect PASS**

Run: `conda run -n sbs python -m pytest tests/test_progression.py tests/test_program.py -v`
Expected: all green.

- [ ] **Step 7: Add the regression test locking the stall fix**

Append to `tests/test_program.py`:

```python
def test_sbs_tm_raw_accumulation_unfreezes_weight():
    # Beat repout by 1 each week -> +0.5%/week. Under the old bug the TM was
    # rounded each week, freezing the weight at 95 forever. With raw TM the
    # weight must climb in legal 2.5 steps.
    p = Profile(lifts=[Lift(name="Squat", tier="sbs", day=1, max=135,
                            intensity=0.7, reps=4, repout=8, sets=3)])
    s = initial_state(p); lift = p.lift("Squat")
    weights = []
    for week in range(1, 9):
        advance_lift(p, lift, s.lifts["Squat"], actual_reps=9, week=week)
        weights.append(week_plan(p, s, day=1)[0].weight)
    assert s.lifts["Squat"].tm % 2.5 != 0          # (a) TM stays raw, not snapped
    assert weights[-1] > weights[0]                # (b) weight climbs -- stall fixed
    assert all(w % 2.5 == 0 for w in weights)      # (c) every loaded weight legal
```

- [ ] **Step 8: Run the regression test — expect PASS**

Run: `conda run -n sbs python -m pytest tests/test_program.py::test_sbs_tm_raw_accumulation_unfreezes_weight -v`
Expected: PASS. (Sanity: temporarily reverting Step 4 makes this test fail — that is the bug it locks.)

- [ ] **Step 9: Commit**

```bash
git add sbs_cli/engine/progression.py sbs_cli/program.py tests/test_progression.py tests/test_program.py
git commit -m "fix: keep sbs TM full-precision so weekly deltas accumulate

sbs_next rounded TM to the gym quantum each week, discarding sub-quantum
deltas and stalling upward progression for lifts with TM < ~250 kg.
Drop the quantum param; round only the loaded working weight. Add a
regression test asserting raw TM + climbing weight + legal 2.5 steps."
```

---

## Task 2: Display precision — est1RM to 2 decimals everywhere + TM to 1 decimal in CLI

**Files:**
- Modify: `webapp/routes/plan.py:78-79`
- Modify: `webapp/templates/plan.html:18`
- Modify: `webapp/templates/week_export.html:32,35`
- Modify: `webapp/templates/tier_preview.html:9`
- Modify: `sbs_cli/view/terminal.py:13,30,32`
- Modify: `sbs_cli/view/templates/week.html.j2:26`
- Modify: `tests/test_terminal.py`, `tests/test_html.py`, `tests/test_routes_plan.py` (lock 2-decimals)

**Interfaces:** none new — display-only.

- [ ] **Step 1: Write the failing display-precision tests first**

In `tests/test_terminal.py`, add `import re` at the top and augment the show-text test:

```python
def test_render_show_text_has_est1rm_and_history_count():
    p = _profile(); s = initial_state(p)
    from sbs_cli.program import advance_lift
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=10, week=1)
    txt = render_show_text(p, s)
    assert "Squat" in txt and "est" in txt.lower()
    assert re.search(r"\d+\.\d{2}", txt)          # est1RM renders to 2 decimals
```

In `tests/test_html.py`, add `import re` and append a new test:

```python
def test_render_html_est1rm_two_decimals():
    p = _profile(); s = initial_state(p)
    from sbs_cli.program import advance_lift
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=11, week=1)
    html = render_week_html(p, s, week=1)
    assert re.search(r"\d+\.\d{2}", html)          # est1RM renders to 2 decimals
```

In `tests/test_routes_plan.py`, add `import re` and augment `test_export_week_standalone_with_progress` — after the existing `assert "≈" in html` line add:

```python
    assert re.search(r"≈\s*\d+\.\d{2}", html)      # live est1RM renders to 2 decimals
```

- [ ] **Step 2: Run the new tests — expect FAIL**

Run: `conda run -n sbs python -m pytest tests/test_terminal.py tests/test_html.py tests/test_routes_plan.py -v`
Expected: the three new/changed assertions FAIL (current rendering uses 1 decimal / bare value).

- [ ] **Step 3: Update `webapp/routes/plan.py` — delta + est1rm f-strings**

At `webapp/routes/plan.py:78`:

```python
        delta_html = f'<span class="{cls}">{sign}{p["delta"]:.2f}</span>'
```

At `webapp/routes/plan.py:79`:

```python
    return f'≈{p["est1rm"]:.2f} {delta_html}'
```

- [ ] **Step 4: Update `webapp/templates/plan.html:18`**

```jinja
          | est 1RM {{ "%.2f"|format(it.est1rm) if it.est1rm is not none else '—' }}
```

- [ ] **Step 5: Update `webapp/templates/week_export.html:32` and `:35`**

Line 32:

```jinja
        | 最佳 1RM {{ "%.2f"|format(it.est1rm) if it.est1rm is not none else '—' }}
```

Line 35:

```jinja
        <span class="log">本周末组: {{ it.logged }} → est1RM ≈{{ "%.2f"|format(it.live) }}</span>
```

- [ ] **Step 6: Update `webapp/templates/tier_preview.html:9`**

```jinja
    <li>est1RM (从历史): {{ "%.2f"|format(preview.est1rm) if preview.est1rm is not none else '—' }}</li>
```

- [ ] **Step 7: Update `sbs_cli/view/terminal.py` — est1RM 2-dec (lines 13, 30) and TM 1-dec (line 32)**

Line 13:

```python
            est = f"  est1RM {it.est1rm:.2f}" if it.est1rm else ""
```

Line 30:

```python
        est = f"  est1RM {ls.est1rm:.2f}" if ls.est1rm else ""
```

Line 32 (TM display — round the now-raw TM to 1 decimal for text only):

```python
            lines.append(f"{l.name:18} TM {ls.tm:.1f}  hist {hist}{est}")
```

- [ ] **Step 8: Update `sbs_cli/view/templates/week.html.j2:26`**

```jinja
    {% if it.est1rm %} | est 1RM {{ "%.2f"|format(it.est1rm) }}{% else %} | est 1RM —{% endif %}
```

- [ ] **Step 9: Run display + full webapp/CLI test suites — expect PASS**

Run: `conda run -n sbs python -m pytest tests/test_terminal.py tests/test_html.py tests/test_routes_plan.py tests/test_routes_settings.py -v`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add webapp/routes/plan.py webapp/templates/plan.html webapp/templates/week_export.html \
        webapp/templates/tier_preview.html sbs_cli/view/terminal.py \
        sbs_cli/view/templates/week.html.j2 tests/test_terminal.py tests/test_html.py \
        tests/test_routes_plan.py
git commit -m "feat: show est1RM to 2 decimals; round TM display to 1 decimal

est1RM is display-rounded to 2 decimals on every surface (plan, export,
tier preview, live autosave, CLI, html export). TM is now raw internally;
CLI show rounds it to 1 decimal for presentation only."
```

---

## Task 3: One-shot migration — replay raw sbs TM from `lift.max`

**Files:**
- Modify: `sbs_cli/program.py` (append `recompute_sbs_tm` pure fn)
- Modify: `webapp/services/recompute.py` (append I/O wrapper)
- Create: `migrate_sbs_tm.py` (root-level orchestrator)
- Create: `tests/test_migrate_sbs_tm.py`

**Interfaces:**
- Produces (engine): `recompute_sbs_tm(lift: Lift, history: List[SetEntry]) -> float`
- Produces (service): `recompute_sbs_tm(conn: sqlite3.Connection, lift_id: int) -> Optional[float]` (returns `None` for non-sbs)
- Consumes: `sbs_next` (Task 1 raw signature), `repo.get_lift` / `repo.list_history` / `repo.get_lift_state` / `repo.save_lift_state`, `advance_service._lift_from_row`.

- [ ] **Step 1: Write the failing migration test**

Create `tests/test_migrate_sbs_tm.py`:

```python
from webapp import db, repo
import migrate_sbs_tm


def _seed(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    # sbs Squat: max=135, week-1 history 90x8 (repout 10 -> diff -2 -> -5%).
    # Faithful raw TM = 135*0.95 = 128.25. Stored (buggy, rounded) = 127.5.
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=3, max=135.0, intensity=0.7, reps=4, repout=10, start=None)
    repo.save_lift_state(conn, lid, tier="sbs", tm=127.5, weight=None,
                         target=None, streak=0, est1rm=120.0)
    repo.append_history(conn, lid, week=1, weight=90.0, reps=8)
    conn.close()
    return lid


def test_migrate_replays_sbs_tm_raw_from_max(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 128.25            # replayed raw from max, not 127.5
    assert st["est1rm"] == 120.0         # untouched
    conn.close()


def test_migrate_skips_non_sbs_lifts(tmp_path):
    dbp = str(tmp_path / "t.db")
    conn = db.connect(dbp)
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=65.0)
    repo.save_lift_state(conn, lid, tier="t2", tm=None, weight=85.0,
                         target=8, streak=0, est1rm=None)
    conn.close()
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_lift_state(conn, lid)["weight"] == 85.0   # unchanged
    conn.close()


def test_migrate_creates_backup(tmp_path):
    dbp = str(tmp_path / "t.db")
    _seed(dbp)
    bdir = tmp_path / "bak"
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(bdir))
    assert len(list(bdir.glob("*.db.bak"))) == 1


def test_migrate_is_idempotent(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_lift_state(conn, lid)["tm"] == 128.25
    conn.close()
```

- [ ] **Step 2: Run the migration test — expect FAIL (module missing)**

Run: `conda run -n sbs python -m pytest tests/test_migrate_sbs_tm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_sbs_tm'` (and `recompute_sbs_tm` not yet defined).

- [ ] **Step 3: Add the pure engine fn `recompute_sbs_tm`**

Append to `sbs_cli/program.py` (after `recompute_state`):

```python
def recompute_sbs_tm(lift: Lift, history: List[SetEntry]) -> float:
    """Replay an sbs lift's TM from ``lift.max`` over its history (raw, no rounding).
    History rows are immutable facts; only their reps drive the replay. No Profile
    is needed: ``sbs_next`` (post-fix) takes only ``(tm, repout, actual)``.
    xlsx-faithful: in the RTF template, editing Max recomputes every downstream
    TM from that Max. See ADR 0001."""
    tm = lift.max
    for h in sorted(history, key=lambda x: x.week):
        tm = sbs_next(tm, lift.repout, h.reps)
    return tm
```

- [ ] **Step 4: Add the I/O wrapper in `webapp/services/recompute.py`**

At the top of `webapp/services/recompute.py`, extend the existing import line:

```python
from sbs_cli.program import recompute_state, recompute_sbs_tm as _engine_recompute_sbs_tm
```

Add `Optional` to the typing import (the file currently has none — add `from typing import Optional` near the other imports).

Append:

```python
def recompute_sbs_tm(conn: sqlite3.Connection, lift_id: int) -> Optional[float]:
    """Replay an sbs lift's TM from its max over history and write the corrected tm.
    Returns the recomputed TM, or None for non-sbs lifts (no-op). est1rm is
    preserved (it is derived from the immutable history and was never corrupted
    by the TM-rounding bug)."""
    lift_row = repo.get_lift(conn, lift_id)
    if lift_row["tier"] != "sbs":
        return None
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    lift = advance_service._lift_from_row(lift_row)
    tm = _engine_recompute_sbs_tm(lift, history)
    st = repo.get_lift_state(conn, lift_id)
    repo.save_lift_state(conn, lift_id, tier="sbs", tm=tm, weight=None,
                         target=None, streak=0, est1rm=st["est1rm"])
    return tm
```

- [ ] **Step 5: Create the migration orchestrator `migrate_sbs_tm.py`**

Create `migrate_sbs_tm.py` at the repo root:

```python
"""One-shot migration: recompute every sbs lift's stored TM by replaying from its
``lifts.max`` over the immutable history, RAW (no rounding). Fixes TMs rounded
under the old bug. Backs up the db first. Idempotent (re-running replays the
same history to the same raw TM). Non-sbs lifts are skipped.

Run:  conda run -n sbs python migrate_sbs_tm.py
      conda run -n sbs python migrate_sbs_tm.py --db sbs.db --backup-dir backups
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
    bak = os.path.join(backup_dir, f"sbs-tm-recompute-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        n = 0
        for row in repo.list_lifts(conn):
            if row["tier"] == "sbs" and \
               recompute_service.recompute_sbs_tm(conn, row["id"]) is not None:
                n += 1
    finally:
        conn.close()
    print(f"recomputed {n} sbs lift TMs from max -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_sbs_tm")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
```

- [ ] **Step 6: Run the migration test — expect PASS**

Run: `conda run -n sbs python -m pytest tests/test_migrate_sbs_tm.py -v`
Expected: all four tests green.

- [ ] **Step 7: Run the full suite to confirm no regressions**

Run: `conda run -n sbs python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add sbs_cli/program.py webapp/services/recompute.py migrate_sbs_tm.py tests/test_migrate_sbs_tm.py
git commit -m "feat: one-shot migrate_sbs_tm replays raw TM from max

Add pure recompute_sbs_tm(lift, history) in the engine and an I/O wrapper
in webapp/services/recompute.py (mirrors recompute_on_start_change).
migrate_sbs_tm.py backs up sbs.db, then replays each sbs lift's TM from
its max over history. Idempotent; est1rm untouched. See ADR 0001."
```

---

## Task 4: Settings UX — relabel gym-increment field + link `incr` spinner

**Files:**
- Modify: `webapp/templates/settings.html:6,8`
- Modify: `tests/test_routes_settings.py` (lock new label)

**Interfaces:** none — template-only; internal `rounding` symbol unchanged.

- [ ] **Step 1: Write the failing label test**

In `tests/test_routes_settings.py`, change `test_settings_view`:

```python
def test_settings_view(client):
    rv = client.get("/settings")
    text = rv.data.decode("utf-8")
    assert rv.status_code == 200
    assert "最小变动" in text            # gym-increment field relabeled
    assert "全局参数" in text            # page title still present
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `conda run -n sbs python -m pytest tests/test_routes_settings.py::test_settings_view -v`
Expected: FAIL (`"最小变动" in text` is False — label is still `rounding (kg)`).

- [ ] **Step 3: Relabel `rounding` field and link `incr` spinner step**

In `webapp/templates/settings.html`:

Line 6 — relabel (keep `step="0.5"` so any quantum can be set; internal `name="rounding"` unchanged):

```html
  <div class="row"><label>最小变动 (kg): <input type="number" step="0.5" name="rounding" value="{{ s.rounding }}"></label></div>
```

Line 8 — link the `incr` spinner to the configured rounding:

```html
  <div class="row"><label>incr (kg): <input type="number" step="{{ s.rounding }}" name="incr" value="{{ s.incr }}"></label></div>
```

- [ ] **Step 4: Run the settings test — expect PASS**

Run: `conda run -n sbs python -m pytest tests/test_routes_settings.py -v`
Expected: green.

- [ ] **Step 5: Run full suite — final gate**

Run: `conda run -n sbs python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/settings.html tests/test_routes_settings.py
git commit -m "feat: relabel gym-increment setting to 最小变动; link incr spinner

Display label for the rounding field localized to 最小变动 (kg); the incr
input's step now follows the configured rounding so its spinner snaps to
legal gym multiples. Internal name unchanged."
```

---

## Spec Coverage Map

| Spec section / decision | Task |
|---|---|
| Change 1 — `sbs_next` raw, drop `quantum` | Task 1 (Steps 4-5) |
| Change 2 — `test_progression` flips | Task 1 (Step 1) |
| Change 2 — `test_program.py:39` flip | Task 1 (Step 2) |
| Q2 — regression test (raw TM + climbing weight + legal steps) | Task 1 (Step 7) |
| Change 3 — est1RM 2-dec on 9 surfaces | Task 2 (Steps 3-8) |
| F1 — `plan.py:78` delta `:.2f` | Task 2 (Step 3) |
| Change 4 — TM CLI 1-dec (`terminal.py:32`) | Task 2 (Step 7) |
| Q7 — 2-decimal display-test assertions | Task 2 (Step 1) |
| Change 5 — engine `recompute_sbs_tm` (Q3=P service layer) | Task 3 (Steps 3-5) |
| Q1=A′ — replay from `lift.max`, no guard, idempotent, est1rm untouched | Task 3 (Steps 3, 5) + migration test (Step 1) |
| Change 6 — relabel `最小变动` + `incr` step linkage (Q5=Now) | Task 4 |
| CONTEXT.md / ADR 0001 | already written (no task) |
| Follow-ups (tier-switch seed, max-edit recompute) | documented in ADR 0001 + spec Out-of-Scope; no task |

## Out of Scope (per ADR 0001 / spec)

- Unifying the tier-switch-into-sbs TM seed (`webapp/services/tier.py:21`, `tm = est1rm`) with the engine's `max`-replay.
- Live `max`-edit recompute for sbs (currently a no-op in `recompute_on_start_change`).
- Renaming the internal `rounding` symbol (DB column / schema / code) — display label only.
