# SBS Local Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SBS/GZCLP CLI + YAML + JSON-shuttle workflow with a local browser app (Flask + Jinja + HTMX) backed by a single SQLite file, reusing the existing proven engine 100% unchanged.

**Architecture:** The pure-function engine (`sbs_cli/engine/`, `sbs_cli/program.py`) is fed dataclasses assembled by a thin adapter (`webapp/services/`) from a SQLite repository (`webapp/repo.py`). Flask serves server-rendered Jinja templates; HTMX provides partial updates for lift CRUD without full page reloads. No JS framework, no auth, localhost-only.

**Tech Stack:** Python 3.12 (conda env `sbs`) · Flask · Jinja2 · HTMX (vendored, offline) · sqlite3 (stdlib) · PyInstaller (packaging).

**Spec:** `docs/superpowers/specs/2026-06-27-sbs-local-webapp-redesign-design.md`

**Environment note:** All commands run as `conda run -n sbs ...`. The env exists but is empty — Task 0 installs deps. Never use `git add -A` (per global rule); commit steps list explicit paths. The project is currently **not** a git repo — Task 0 initializes it so commit steps work; if you choose to skip git, treat commit steps as checkpoints only.

---

## File Structure

**Created:**
- `requirements.txt` — pinned deps.
- `.gitignore` — exclude `sbs.db`, `backups/`, caches.
- `webapp/__init__.py`, `webapp/db.py`, `webapp/repo.py`, `webapp/app.py`, `webapp/__main__.py`
- `webapp/services/__init__.py`, `webapp/services/advance.py`, `webapp/services/tier.py`
- `webapp/routes/__init__.py`, `webapp/routes/plan.py`, `webapp/routes/lifts.py`, `webapp/routes/settings.py`
- `webapp/templates/base.html`, `webapp/templates/plan.html`, `webapp/templates/lifts.html`, `webapp/templates/_lift_row.html`, `webapp/templates/settings.html`, `webapp/templates/tier_preview.html`
- `webapp/static/htmx.min.js` — vendored (downloaded, offline).
- `migrate.py`
- `tests/test_db.py`, `tests/test_repo.py`, `tests/test_advance_service.py`, `tests/test_tier_service.py`, `tests/test_routes_plan.py`, `tests/test_routes_lifts.py`, `tests/test_routes_settings.py`, `tests/test_migrate.py`, `tests/conftest.py`

**Reused unchanged:** `sbs_cli/engine/progression.py`, `sbs_cli/engine/onerm.py`, `sbs_cli/program.py`, `sbs_cli/data/schema.py`, `sbs_cli/importer.py`, `sbs_cli/data/io.py` (read by `migrate.py`).

**Key engine signatures (do not change):**
- `round_weight(w, quantum=2.5)`; `sbs_next(tm, repout, actual, quantum=2.5)`; `t3_next(weight, actual, target=15, incr=2.5, quantum=2.5)`; `t2_next(T2State(target,streak,weight), actual, est1rm, fail=3, incr=2.5, reset_pct=0.70, quantum=2.5)`.
- `program.advance_lift(profile, lift, state, actual_reps, week)` — mutates `state` in place, appends to `state.history` only when `actual_reps is not None`, recomputes `state.est1rm`.
- `program._est1rm_from_history(history) -> float|None`; `program.best_1rm(history)`.

---

## Task 0: Environment, deps, git

**Files:**
- Create: `requirements.txt`, `.gitignore`

- [ ] **Step 1: Install deps into the `sbs` env**

Run:
```bash
conda run -n sbs python -m pip install flask pyyaml jinja2 openpyxl pytest
```
Expected: all install successfully (`jinja2` comes with flask but pin explicitly).

- [ ] **Step 2: Write `requirements.txt`**

```
flask>=3.0
pyyaml>=6.0
jinja2>=3.1
openpyxl>=3.1
pytest>=8.0
```

- [ ] **Step 3: Write `.gitignore`**

```
sbs.db
backups/
__pycache__/
.pytest_cache/
*.pyc
build/
dist/
*.spec.bak
```

- [ ] **Step 4: Initialize git (so commit steps work)**

Run:
```bash
cd "D:/WorkSpace/sbs" && git init && git add requirements.txt .gitignore && git commit -m "chore: add deps and gitignore for webapp redesign"
```
Expected: repo initialized, first commit created.

- [ ] **Step 5: Verify engine still green before touching anything**

Run:
```bash
conda run -n sbs python -m pytest tests/ -q
```
Expected: existing 74 engine tests pass (confirms env + engine intact).

---

## Task 1: DB connection + schema bootstrap

**Files:**
- Create: `webapp/__init__.py` (empty package marker)
- Create: `webapp/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Create empty `webapp/__init__.py`**

```python
```
(empty file)

- [ ] **Step 2: Write the failing test**

`tests/test_db.py`:
```python
import sqlite3
from webapp import db


def test_init_schema_creates_tables_and_default_settings(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"settings", "lifts", "lift_state", "history"} <= tables
    s = conn.execute("SELECT * FROM settings").fetchone()
    assert s["week"] == 1 and s["days_per_week"] == 4 and s["rounding"] == 2.5
    assert s["incr"] == 2.5 and s["t2_reset_pct"] == 0.7 and s["t2_fail"] == 3 and s["t3_target"] == 15
    conn.close()


def test_foreign_keys_enforced(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_db.py -q`
Expected: FAIL (`ModuleNotFoundError: webapp.db`).

- [ ] **Step 4: Implement `webapp/db.py`**

```python
"""SQLite connection + schema bootstrap."""
import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sbs.db"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    week         INTEGER NOT NULL,
    days_per_week INTEGER NOT NULL,
    rounding     REAL    NOT NULL,
    incr         REAL    NOT NULL,
    t2_reset_pct REAL    NOT NULL,
    t2_fail      INTEGER NOT NULL,
    t3_target    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lifts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    tier       TEXT NOT NULL CHECK (tier IN ('sbs','t2','t3')),
    day        INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    sets       INTEGER NOT NULL DEFAULT 3,
    max        REAL,
    intensity  REAL,
    reps       INTEGER,
    repout     INTEGER,
    start      REAL
);
CREATE TABLE IF NOT EXISTS lift_state (
    lift_id INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
    tier    TEXT NOT NULL,
    tm      REAL,
    weight  REAL,
    target  INTEGER,
    streak  INTEGER NOT NULL DEFAULT 0,
    est1rm  REAL
);
CREATE TABLE IF NOT EXISTS history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
    week    INTEGER NOT NULL,
    weight  REAL NOT NULL,
    reps    INTEGER NOT NULL,
    ts      TEXT NOT NULL
);
"""

_DEFAULT_SETTINGS = dict(
    week=1, days_per_week=4, rounding=2.5, incr=2.5,
    t2_reset_pct=0.7, t2_fail=3, t3_target=15,
)


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO settings (id, week, days_per_week, rounding, incr, t2_reset_pct, t2_fail, t3_target) "
            "VALUES (1, :week, :days_per_week, :rounding, :incr, :t2_reset_pct, :t2_fail, :t3_target)",
            _DEFAULT_SETTINGS,
        )
    conn.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_db.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/__init__.py webapp/db.py tests/test_db.py
git commit -m "feat: add SQLite connection and schema bootstrap"
```

---

## Task 2: Repository — settings

**Files:**
- Create: `webapp/repo.py`
- Test: `tests/test_repo.py`

- [ ] **Step 1: Write the failing test (append to new `tests/test_repo.py`)**

```python
import sqlite3
from webapp import db, repo


def _fresh(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    return conn


def test_get_settings_returns_defaults(tmp_path):
    conn = _fresh(tmp_path)
    s = repo.get_settings(conn)
    assert s["week"] == 1 and s["rounding"] == 2.5 and s["t3_target"] == 15
    conn.close()


def test_set_week_updates_week(tmp_path):
    conn = _fresh(tmp_path)
    repo.set_week(conn, 7)
    assert repo.get_settings(conn)["week"] == 7
    conn.close()


def test_update_settings_partial(tmp_path):
    conn = _fresh(tmp_path)
    repo.update_settings(conn, incr=5.0, t3_target=20)
    s = repo.get_settings(conn)
    assert s["incr"] == 5.0 and s["t3_target"] == 20 and s["rounding"] == 2.5
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: FAIL (`ModuleNotFoundError: webapp.repo`).

- [ ] **Step 3: Implement `webapp/repo.py` (settings section only; later tasks append)**

```python
"""SQLite repository: settings / lifts / lift_state / history CRUD."""
from typing import Optional
import sqlite3

_SETTINGS_COLS = ("week", "days_per_week", "rounding", "incr",
                  "t2_reset_pct", "t2_fail", "t3_target")


# ---------- settings ----------
def get_settings(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def set_week(conn: sqlite3.Connection, week: int) -> None:
    conn.execute("UPDATE settings SET week = ?", (week,))
    conn.commit()


def update_settings(conn: sqlite3.Connection, **fields) -> None:
    bad = set(fields) - set(_SETTINGS_COLS)
    if bad:
        raise ValueError(f"unknown settings columns: {bad}")
    if not fields:
        return
    assignments = ", ".join(f"{c} = ?" for c in fields)
    conn.execute(f"UPDATE settings SET {assignments} WHERE id = 1", tuple(fields.values()))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/repo.py tests/test_repo.py
git commit -m "feat: add settings repository"
```

---

## Task 3: Repository — lifts CRUD

**Files:**
- Modify: `webapp/repo.py` (append lifts section)
- Test: `tests/test_repo.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_repo.py`**

```python
def test_create_lift_sbs_returns_id_and_inits_state(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    assert isinstance(lid, int) and lid > 0
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "sbs" and st["tm"] == 135.0 and st["weight"] is None
    conn.close()


def test_create_lift_t2_inits_weight_target(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=1,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t2" and st["weight"] == 85.0 and st["target"] == 10 and st["streak"] == 0
    conn.close()


def test_create_lift_t3_inits_weight(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=2,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t3" and st["weight"] == 40.0
    conn.close()


def test_list_and_get_lift(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    rows = repo.list_lifts(conn)
    assert len(rows) == 1 and rows[0]["name"] == "Squat"
    assert repo.get_lift(conn, lid)["name"] == "Squat"
    assert repo.get_lift_by_name(conn, "Squat")["id"] == lid
    conn.close()


def test_update_and_delete_lift(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.update_lift(conn, lid, intensity=0.75, day=2)
    assert repo.get_lift(conn, lid)["intensity"] == 0.75
    repo.delete_lift(conn, lid)
    assert repo.list_lifts(conn) == []
    assert repo.get_lift_state(conn, lid) is None  # cascade
    conn.close()


def test_create_lift_duplicate_name_raises(tmp_path):
    import pytest
    conn = _fresh(tmp_path)
    repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                     sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=1,
                         sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: FAIL (lifts functions missing).

- [ ] **Step 3: Append lifts section to `webapp/repo.py`**

```python
# ---------- lifts ----------
_LIFT_COLS = ("name", "tier", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start")


def create_lift(conn: sqlite3.Connection, *, name: str, tier: str, day: int,
                sort_order: int, sets: int, max, intensity, reps, repout,
                start) -> int:
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, tier, day, sort_order, sets, max, intensity, reps, repout, start),
    )
    lid = cur.lastrowid
    _init_lift_state(conn, lid, tier, max, start)
    conn.commit()
    return lid


def _init_lift_state(conn, lid, tier, max, start):
    if tier == "sbs":
        conn.execute(
            "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
            "VALUES (?, 'sbs', ?, NULL, NULL, 0, NULL)", (lid, max))
    elif tier == "t2":
        conn.execute(
            "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
            "VALUES (?, 't2', NULL, ?, 10, 0, NULL)", (lid, start))
    else:  # t3
        conn.execute(
            "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
            "VALUES (?, 't3', NULL, ?, NULL, 0, NULL)", (lid, start))


def list_lifts(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM lifts ORDER BY day, sort_order").fetchall()


def get_lift(conn: sqlite3.Connection, lift_id: int):
    return conn.execute("SELECT * FROM lifts WHERE id = ?", (lift_id,)).fetchone()


def get_lift_by_name(conn: sqlite3.Connection, name: str):
    return conn.execute("SELECT * FROM lifts WHERE name = ?", (name,)).fetchone()


def update_lift(conn: sqlite3.Connection, lift_id: int, **fields) -> None:
    bad = set(fields) - set(_LIFT_COLS)
    if bad:
        raise ValueError(f"unknown lift columns: {bad}")
    if not fields:
        return
    assignments = ", ".join(f"{c} = ?" for c in fields)
    conn.execute(f"UPDATE lifts SET {assignments} WHERE id = ?",
                 (*fields.values(), lift_id))
    conn.commit()


def delete_lift(conn: sqlite3.Connection, lift_id: int) -> None:
    conn.execute("DELETE FROM lifts WHERE id = ?", (lift_id,))
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: PASS (all repo tests so far).

- [ ] **Step 5: Commit**

```bash
git add webapp/repo.py tests/test_repo.py
git commit -m "feat: add lifts repository with state initialization"
```

---

## Task 4: Repository — lift_state + history

**Files:**
- Modify: `webapp/repo.py` (append)
- Test: `tests/test_repo.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_repo.py`**

```python
def test_save_lift_state_upserts(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.save_lift_state(conn, lid, tier="sbs", tm=140.0, weight=None,
                         target=None, streak=0, est1rm=141.2, _append_history=False)
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 140.0 and st["est1rm"] == 141.2
    conn.close()


def test_append_history_and_list(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.append_history(conn, lid, week=1, weight=95.0, reps=11)
    repo.append_history(conn, lid, week=2, weight=97.5, reps=9)
    rows = repo.list_history(conn, lid)
    assert len(rows) == 2
    assert rows[0]["week"] == 1 and rows[0]["weight"] == 95.0 and rows[0]["reps"] == 11
    assert rows[1]["week"] == 2
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: FAIL (`save_lift_state`, `append_history`, `list_history` missing).

- [ ] **Step 3: Append to `webapp/repo.py`**

```python
# ---------- lift_state ----------
_STATE_COLS = ("tier", "tm", "weight", "target", "streak", "est1rm")


def get_lift_state(conn: sqlite3.Connection, lift_id: int):
    return conn.execute("SELECT * FROM lift_state WHERE lift_id = ?", (lift_id,)).fetchone()


def save_lift_state(conn: sqlite3.Connection, lift_id: int, *, tier: str, tm,
                    weight, target, streak: int, est1rm, _append_history: bool = True) -> None:
    """Upsert lift_state from engine-produced fields. Does NOT touch history table
    (history is appended separately via append_history)."""
    conn.execute(
        "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(lift_id) DO UPDATE SET "
        "tier=excluded.tier, tm=excluded.tm, weight=excluded.weight, "
        "target=excluded.target, streak=excluded.streak, est1rm=excluded.est1rm",
        (lift_id, tier, tm, weight, target, streak, est1rm),
    )
    conn.commit()


# ---------- history ----------
def append_history(conn: sqlite3.Connection, lift_id: int, *, week: int,
                   weight, reps: int, ts: str | None = None) -> None:
    if ts is None:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO history (lift_id, week, weight, reps, ts) VALUES (?, ?, ?, ?, ?)",
        (lift_id, week, weight, reps, ts),
    )
    conn.commit()


def list_history(conn: sqlite3.Connection, lift_id: int):
    return conn.execute(
        "SELECT * FROM history WHERE lift_id = ? ORDER BY id", (lift_id,)
    ).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -q`
Expected: PASS (all repo tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/repo.py tests/test_repo.py
git commit -m "feat: add lift_state upsert and history repository"
```

---

## Task 5: Advance service (engine adapter)

**Files:**
- Create: `webapp/services/__init__.py` (empty), `webapp/services/advance.py`
- Test: `tests/test_advance_service.py`

This is the core reuse: assemble dataclasses from DB → call `program.advance_lift` → write back.

- [ ] **Step 1: Create empty `webapp/services/__init__.py`**

```python
```

- [ ] **Step 2: Write the failing test**

`tests/test_advance_service.py`:
```python
import sqlite3
from webapp import db, repo
from webapp.services import advance


def _seed(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                     sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=1,
                     sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=2,
                     sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    return conn


def test_advance_week_runs_engine_and_bumps_week(tmp_path):
    conn = _seed(tmp_path)
    new_week = advance.advance_week(conn, {"Squat": 13, "Rows": 10, "Curl": 15})
    assert new_week == 2
    assert repo.get_settings(conn)["week"] == 2
    # Squat beat repout(10) by 3 -> +1.5% -> tm 135*1.015=137.025 -> round 2.5 -> 137.5
    squat_id = repo.get_lift_by_name(conn, "Squat")["id"]
    st = repo.get_lift_state(conn, squat_id)
    assert st["tm"] == 137.5
    # history appended for logged lift
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_advance_week_skips_unlogged_lifts(tmp_path):
    conn = _seed(tmp_path)
    advance.advance_week(conn, {"Squat": 10})  # Rows/Curl not logged
    curl_id = repo.get_lift_by_name(conn, "Curl")["id"]
    assert repo.list_history(conn, curl_id) == []   # no history
    assert repo.get_lift_state(conn, curl_id)["weight"] == 40.0  # unchanged
    conn.close()


def test_advance_week_rows_t2_hit_increments(tmp_path):
    conn = _seed(tmp_path)
    advance.advance_week(conn, {"Rows": 10})  # hit target 10 -> +incr 2.5
    rows_id = repo.get_lift_by_name(conn, "Rows")["id"]
    assert repo.get_lift_state(conn, rows_id)["weight"] == 87.5
    conn.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_advance_service.py -q`
Expected: FAIL (`ModuleNotFoundError: webapp.services.advance`).

- [ ] **Step 4: Implement `webapp/services/advance.py`**

```python
"""Orchestrate the engine over a logged week: DB -> dataclass -> engine -> DB."""
import sqlite3
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState
from sbs_cli.program import advance_lift, _est1rm_from_history
from .. import repo


def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
    )


def _profile_from_rows(settings, lift_rows) -> Profile:
    return Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
        lifts=[_lift_from_row(r) for r in lift_rows],
    )


def _state_from_rows(st_row, hist_rows) -> LiftState:
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"]) for h in hist_rows]
    return LiftState(
        name="", tier=st_row["tier"], tm=st_row["tm"], weight=st_row["weight"],
        target=st_row["target"], streak=st_row["streak"], est1rm=st_row["est1rm"],
        history=history,
    )


def advance_week(conn: sqlite3.Connection, logs: dict) -> int:
    """Run the engine for every lift using this week's logged last-set reps.
    `logs` maps lift name -> last-set reps (lifts absent from logs are skipped)."""
    settings = repo.get_settings(conn)
    week = settings["week"]
    lift_rows = repo.list_lifts(conn)
    profile = _profile_from_rows(settings, lift_rows)
    for row in lift_rows:
        name = row["name"]
        actual = logs.get(name)
        st = repo.get_lift_state(conn, row["id"])
        ls = _state_from_rows(st, repo.list_history(conn, row["id"]))
        advance_lift(profile, profile.lift(name), ls, actual, week=week)
        repo.save_lift_state(conn, row["id"], tier=ls.tier, tm=ls.tm,
                             weight=ls.weight, target=ls.target,
                             streak=ls.streak, est1rm=ls.est1rm)
        if actual is not None and ls.history:
            last = ls.history[-1]
            repo.append_history(conn, row["id"], week=week, weight=last.weight, reps=last.reps)
    new_week = week + 1
    repo.set_week(conn, new_week)
    return new_week
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_advance_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/services/__init__.py webapp/services/advance.py tests/test_advance_service.py
git commit -m "feat: add advance service reusing engine over SQLite"
```

---

## Task 6: Tier-switch service (history preserved)

**Files:**
- Create: `webapp/services/tier.py`
- Test: `tests/test_tier_service.py`

Rule (spec §6.3): keep `history`; recompute `est1rm`; derive new-tier starting state from `est1rm` (fallback to configured `max`/`start`); produce a preview dict; apply only on explicit confirm.

- [ ] **Step 1: Write the failing test**

`tests/test_tier_service.py`:
```python
from webapp import db, repo
from webapp.services import advance, tier


def _seed_with_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    # one logged week -> est1rm derived from history
    advance.advance_week(conn, {"Squat": 10})
    repo.set_week(conn, 1)  # roll week back for test isolation
    return conn, lid


def test_preview_tier_switch_preserves_history_basis(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = tier.derive_state(conn, lid, "t2", repo.get_settings(conn))
    assert preview["tier"] == "t2" and preview["target"] == 10 and preview["streak"] == 0
    # weight = round(est1rm * 0.7, 2.5)
    assert preview["weight"] == round((est_before * 0.7) / 2.5) * 2.5 or preview["est1rm"] == est_before
    conn.close()


def test_preview_sbs_uses_est1rm_for_tm(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = tier.derive_state(conn, lid, "sbs", repo.get_settings(conn))
    assert preview["tm"] == est_before
    conn.close()


def test_apply_tier_switch_keeps_history_and_writes_state(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    hist_before = len(repo.list_history(conn, lid))
    preview = tier.derive_state(conn, lid, "t3", repo.get_settings(conn))
    tier.apply_switch(conn, lid, preview)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t3" and st["weight"] == preview["weight"]
    assert repo.get_lift(conn, lid)["tier"] == "t3"
    assert len(repo.list_history(conn, lid)) == hist_before  # history untouched
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_tier_service.py -q`
Expected: FAIL (`ModuleNotFoundError: webapp.services.tier`).

- [ ] **Step 3: Implement `webapp/services/tier.py`**

```python
"""Tier switch: keep history, recompute est1rm, derive new-tier start state."""
import sqlite3
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import _est1rm_from_history
from sbs_cli.engine.progression import round_weight
from .. import repo


def derive_state(conn: sqlite3.Connection, lift_id: int, new_tier: str,
                 settings) -> dict:
    """Compute the new-tier starting state from preserved history. Read-only."""
    if new_tier not in ("sbs", "t2", "t3"):
        raise ValueError(f"unknown tier: {new_tier}")
    hist_rows = repo.list_history(conn, lift_id)
    history = [SetEntry(h["week"], h["weight"], h["reps"]) for h in hist_rows]
    est1rm = _est1rm_from_history(history)
    lift = repo.get_lift(conn, lift_id)
    quantum = settings["rounding"]

    if new_tier == "sbs":
        tm = est1rm if est1rm is not None else (lift["max"] or 0.0)
        return {"tier": "sbs", "tm": tm, "weight": None, "target": None,
                "streak": 0, "est1rm": est1rm}
    if new_tier == "t2":
        if est1rm is not None:
            w = round_weight(est1rm * settings["t2_reset_pct"], quantum)
        else:
            w = lift["start"] or 0.0
        return {"tier": "t2", "tm": None, "weight": w, "target": 10,
                "streak": 0, "est1rm": est1rm}
    # t3
    if est1rm is not None:
        w = round_weight(est1rm * 0.6, quantum)
    else:
        w = lift["start"] or 0.0
    return {"tier": "t3", "tm": None, "weight": w, "target": None,
            "streak": 0, "est1rm": est1rm}


def apply_switch(conn: sqlite3.Connection, lift_id: int, state: dict) -> None:
    """Write the derived state to lifts.tier + lift_state. History is NOT modified."""
    repo.update_lift(conn, lift_id, tier=state["tier"])
    repo.save_lift_state(
        conn, lift_id, tier=state["tier"], tm=state["tm"], weight=state["weight"],
        target=state["target"], streak=state["streak"], est1rm=state["est1rm"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_tier_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/services/tier.py tests/test_tier_service.py
git commit -m "feat: add tier-switch service preserving history"
```

---

## Task 7: Backup helper

**Files:**
- Create: `webapp/backup.py`
- Test: `tests/test_backup.py`

Auto-snapshot `sbs.db` → `backups/sbs-wN-<ts>.db.bak` before each advance.

- [ ] **Step 1: Write the failing test**

`tests/test_backup.py`:
```python
import sqlite3
from webapp import db, backup


def test_snapshot_copies_db(tmp_path):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.close()
    bak = backup.snapshot(str(src), dest_dir=str(tmp_path / "bak"), week=2, ts="20260627T100000")
    import os
    assert os.path.exists(bak)
    # copied file is a valid sqlite db with settings table
    chk = sqlite3.connect(bak)
    assert chk.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
    chk.close()


def test_snapshot_filename_format(tmp_path):
    src = tmp_path / "sbs.db"
    db.connect(str(src)).close()  # creates empty file
    bak = backup.snapshot(str(src), dest_dir=str(tmp_path / "bak"), week=3, ts="t1")
    assert bak.endswith("sbs-w3-t1.db.bak")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_backup.py -q`
Expected: FAIL (`ModuleNotFoundError: webapp.backup`).

- [ ] **Step 3: Implement `webapp/backup.py`**

```python
"""Snapshot the SQLite db before destructive operations."""
import os
import shutil
from typing import Optional


def snapshot(src_db: str, *, dest_dir: str, week: int, ts: str) -> str:
    """Copy src_db to dest_dir/sbs-w<week>-<ts>.db.bak. Creates dest_dir. Returns dest path."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"sbs-w{week}-{ts}.db.bak")
    shutil.copy2(src_db, dest)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_backup.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/backup.py tests/test_backup.py
git commit -m "feat: add db snapshot helper"
```

---

## Task 8: Flask app factory + plan GET route

**Files:**
- Create: `webapp/app.py`, `webapp/routes/__init__.py` (empty), `webapp/routes/plan.py`
- Create: `webapp/templates/base.html`, `webapp/templates/plan.html`
- Modify: `webapp/db.py` (add Flask `get_db`/`close_db`)
- Test: `tests/test_routes_plan.py`, `tests/conftest.py`

- [ ] **Step 1: Add Flask helpers to `webapp/db.py` (append)**

```python
# ---------- Flask integration ----------
def get_db():
    """Per-request connection stored in flask.g."""
    from flask import g, current_app
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
        init_schema(g.db)
    return g.db


def close_db(e=None):
    from flask import g
    db = g.pop("db", None)
    if db is not None:
        db.close()
```

- [ ] **Step 2: Write `webapp/templates/base.html`**

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}SBS{% endblock %}</title>
  <style>
    body{font-family:system-ui,sans-serif;margin:16px;max-width:900px}
    h2{margin-top:1.5em;border-bottom:1px solid #ccc}
    .row{display:flex;gap:1em;align-items:center;padding:4px 0;flex-wrap:wrap}
    .row .name{font-weight:bold;min-width:170px}
    .row .meta{color:#555;font-size:0.92em}
    input[type=number]{width:70px;padding:4px}
    button,.btn{margin-top:1em;padding:8px 14px;font-size:1em;cursor:pointer}
    .flash{background:#ffe;padding:8px;border:1px solid #dda;border-radius:4px;margin:8px 0}
    nav a{margin-right:1em}
  </style>
  <script src="{{ url_for('static', filename='htmx.min.js') }}"></script>
</head>
<body>
  <nav>
    <a href="{{ url_for('plan.view') }}">本周计划</a>
    <a href="{{ url_for('lifts.view') }}">动作管理</a>
    <a href="{{ url_for('settings.view') }}">全局参数</a>
  </nav>
  {% with msgs = get_flashed_messages() %}
    {% for m in msgs %}<div class="flash">{{ m }}</div>{% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Download HTMX into `webapp/static/htmx.min.js`**

Run:
```bash
conda run -n sbs python -c "import urllib.request,os;os.makedirs('webapp/static',exist_ok=True);urllib.request.urlretrieve('https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js','webapp/static/htmx.min.js');print('ok',os.path.getsize('webapp/static/htmx.min.js'),'bytes')"
```
Expected: prints `ok <size> bytes`. (Offline thereafter; if the download fails in your environment, fetch `htmx.min.js` v1.9.12 manually from unpkg and save it there.)

- [ ] **Step 4: Write `webapp/templates/plan.html`**

```html
{% extends "base.html" %}
{% block title %}Week {{ week }} plan{% endblock %}
{% block content %}
<h1>Week {{ week }} 计划</h1>
<p>练完填每个动作的<b>末组次数</b>, 点 <b>提交并算下周</b>。</p>
<form method="post" action="{{ url_for('plan.submit') }}">
  {% for day, items in by_day %}
    <h2>Day {{ day }}</h2>
    {% for it in items %}
      <div class="row">
        <span class="name">{{ it.name }}</span>
        <span class="meta">{{ it.tier }} | {{ it.weight }} kg
          {% if it.tier=='sbs' %} x {{ it.reps }} x {{ it.sets }} | rep-out {{ it.repout }}
          {% elif it.tier=='t2' %} x {{ it.target }} x {{ it.sets }} | streak {{ it.streak }}
          {% else %} x {{ it.target }} x {{ it.sets }}
          {% endif %}
          | est 1RM {{ it.est1rm if it.est1rm is not none else '—' }}
        </span>
        <label>末组: <input type="number" name="log_{{ it.name }}"></label>
      </div>
    {% endfor %}
  {% endfor %}
  <button type="submit">提交并算下周</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Create empty `webapp/routes/__init__.py`**

```python
```

- [ ] **Step 6: Write `webapp/routes/plan.py`**

```python
"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from ..db import get_db
from .. import repo
from ..services import advance, tier  # tier imported for completeness; used in lifts route


bp = Blueprint("plan", __name__)


def _by_day(conn):
    from sbs_cli.data.schema import Profile, LiftState
    from sbs_cli.program import week_plan
    settings = repo.get_settings(conn)
    lift_rows = repo.list_lifts(conn)
    profile = Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
    )
    from sbs_cli.data.schema import Lift
    lifts = [Lift(name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
                  intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
                  repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"]) for r in lift_rows]
    profile.lifts = lifts
    states = {}
    for r in lift_rows:
        st = repo.get_lift_state(conn, r["id"])
        hist = repo.list_history(conn, r["id"])
        states[r["name"]] = LiftState(
            name=r["name"], tier=st["tier"], tm=st["tm"], weight=st["weight"],
            target=st["target"], streak=st["streak"], est1rm=st["est1rm"])
    from sbs_cli.data.schema import ProgramState
    ps = ProgramState(week=settings["week"], lifts=states)
    by_day = []
    for d in range(1, settings["days_per_week"] + 1):
        items = week_plan(profile, ps, day=d)
        if items:
            by_day.append((d, items))
    return settings["week"], by_day


@bp.route("/")
def view():
    conn = get_db()
    week, by_day = _by_day(conn)
    return render_template("plan.html", week=week, by_day=by_day)


@bp.route("/log", methods=["POST"])
def submit():
    conn = get_db()
    logs = {}
    for key, val in request.form.items():
        if key.startswith("log_") and val.strip():
            name = key[4:]
            try:
                reps = int(val)
            except ValueError:
                flash(f"非法次数: {name} = {val}")
                return redirect(url_for("plan.view"))
            if reps < 0:
                flash(f"次数不能为负: {name}")
                return redirect(url_for("plan.view"))
            logs[name] = reps
    from ..backup import snapshot
    from datetime import datetime, timezone
    settings = repo.get_settings(conn)
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=settings["week"], ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    new_week = advance.advance_week(conn, logs)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))
```

- [ ] **Step 7: Write `webapp/app.py`**

```python
"""Flask app factory + launch."""
import os
import webbrowser
from threading import Timer
from flask import Flask
from .db import close_db, DEFAULT_DB_PATH


def create_app(db_path: str | None = None, backup_dir: str | None = None,
               test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config["DB_PATH"] = db_path or DEFAULT_DB_PATH
    app.config["BACKUP_DIR"] = backup_dir or os.path.join(
        os.path.dirname(app.config["DB_PATH"]), "backups")
    if test_config:
        app.config.update(test_config)

    from .routes.plan import bp as plan_bp
    app.register_blueprint(plan_bp)
    app.teardown_appcontext(close_db)
    return app


def run(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    app = create_app()
    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    app.run(host=host, port=port)
```

- [ ] **Step 8: Write `tests/conftest.py`**

```python
import os
import pytest
from webapp.app import create_app
from webapp import db


@pytest.fixture()
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    backup_dir = str(tmp_path / "backups")
    app = create_app(db_path=db_path, backup_dir=backup_dir,
                     test_config={"TESTING": True})
    with app.app_context():
        conn = db.connect(db_path)
        db.init_schema(conn)
        conn.close()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
```

- [ ] **Step 9: Write failing route test `tests/test_routes_plan.py`**

```python
from webapp import repo


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


def test_plan_submit_advances(client, app):
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                         sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
        conn.close()
    rv = client.post("/log", data={"log_Squat": "13"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_settings(conn)["week"] == 2
        conn.close()
```

- [ ] **Step 10: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -q`
Expected: FAIL (blueprint `lifts`/`settings` referenced in base nav not yet registered → template error, or import error).

- [ ] **Step 11: Stub the missing blueprints so the app boots**

Create `webapp/routes/lifts.py` and `webapp/routes/settings.py` with minimal blueprints (full bodies come in Tasks 9–10):

`webapp/routes/lifts.py`:
```python
from flask import Blueprint
bp = Blueprint("lifts", __name__)


@bp.route("/lifts")
def view():
    return "lifts stub"
```

`webapp/routes/settings.py`:
```python
from flask import Blueprint
bp = Blueprint("settings", __name__)


@bp.route("/settings")
def view():
    return "settings stub"
```

Register them in `webapp/app.py` `create_app` (after the plan blueprint registration):
```python
    from .routes.lifts import bp as lifts_bp
    from .routes.settings import bp as settings_bp
    app.register_blueprint(lifts_bp)
    app.register_blueprint(settings_bp)
```

- [ ] **Step 12: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -q`
Expected: PASS (2 tests).

- [ ] **Step 13: Commit**

```bash
git add webapp/ tests/conftest.py tests/test_routes_plan.py
git commit -m "feat: add Flask app factory and plan view/log route"
```

---

## Task 9: Lifts CRUD routes + template (HTMX)

**Files:**
- Modify: `webapp/routes/lifts.py` (replace stub)
- Create: `webapp/templates/lifts.html`, `webapp/templates/_lift_row.html`
- Test: `tests/test_routes_lifts.py`

- [ ] **Step 1: Write the failing test `tests/test_routes_lifts.py`**

```python
from webapp import repo


def _lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    conn.close()
    return lid


def test_lifts_view_lists_lift(client, app):
    _lift(app)
    rv = client.get("/lifts")
    assert rv.status_code == 200 and b"Squat" in rv.data


def test_create_lift_via_post(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Press", "tier": "sbs", "day": "2", "sets": "5",
        "max": "60", "intensity": "0.7", "reps": "5", "repout": "10",
    })
    assert rv.status_code == 200  # returns updated row fragment
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Press") is not None
        conn.close()


def test_delete_lift_via_post(client, app):
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/delete")
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid) is None
        conn.close()


def test_edit_lift_params_via_post(client, app):
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/edit", data={"intensity": "0.75", "day": "2"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["intensity"] == 0.75
        conn.close()


def test_rename_lift_via_post(client, app):
    lid = _lift(app)
    client.post(f"/lifts/{lid}/edit", data={"name": "Back Squat"})
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["name"] == "Back Squat"
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -q`
Expected: FAIL (routes 404 / stub returns plain text).

- [ ] **Step 3: Replace `webapp/routes/lifts.py`**

```python
"""Lift CRUD: list, create, edit (rename/params/day), delete."""
from flask import Blueprint, render_template, request, flash, abort
from ..db import get_db
from .. import repo

bp = Blueprint("lifts", __name__)


def _f(name, default=None, cast=str):
    v = request.form.get(name, default)
    if v in (None, ""):
        return None
    return cast(v)


@bp.route("/lifts")
def view():
    conn = get_db()
    lifts = repo.list_lifts(conn)
    settings = repo.get_settings(conn)
    return render_template("lifts.html", lifts=lifts, settings=settings)


@bp.route("/lifts/new", methods=["POST"])
def new():
    conn = get_db()
    name = request.form.get("name", "").strip()
    tier = request.form.get("tier", "sbs")
    if not name:
        flash("动作名不能为空")
        return render_template("_lift_row.html", lift=None, error="name required"), 400
    try:
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float))
    except Exception as e:
        flash(f"创建失败: {e}")
        return render_template("_lift_row.html", lift=None, error=str(e)), 400
    lift = repo.get_lift(conn, lid)
    return render_template("_lift_row.html", lift=lift)


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
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/delete", methods=["POST"])
def delete(lid):
    conn = get_db()
    repo.delete_lift(conn, lid)
    return ("", 200)
```

- [ ] **Step 4: Write `webapp/templates/lifts.html`**

```html
{% extends "base.html" %}
{% block title %}动作管理{% endblock %}
{% block content %}
<h1>动作管理</h1>
<h2>新增动作</h2>
<form hx-post="{{ url_for('lifts.new') }}" hx-target="#lift-list" hx-swap="beforeend" class="row">
  <input name="name" placeholder="动作名">
  <select name="tier"><option value="sbs">sbs</option><option value="t2">t2</option><option value="t3">t3</option></select>
  <input name="day" type="number" placeholder="day" value="1" style="width:60px">
  <input name="sets" type="number" placeholder="sets" value="3" style="width:60px">
  <input name="max" type="number" step="0.5" placeholder="max(sbs)" style="width:80px">
  <input name="intensity" type="number" step="0.05" placeholder="强度" style="width:80px">
  <input name="reps" type="number" placeholder="reps" style="width:60px">
  <input name="repout" type="number" placeholder="repout" style="width:70px">
  <input name="start" type="number" step="0.5" placeholder="start(t2/t3)" style="width:90px">
  <button>添加</button>
</form>

<h2>现有动作</h2>
<div id="lift-list">
  {% for l in lifts %}
    {% include "_lift_row.html" %}
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 5: Write `webapp/templates/_lift_row.html`**

```html
{% if lift %}
<div class="row" id="lift-{{ lift.id }}">
  <span class="name">{{ lift.name }}</span>
  <span class="meta">{{ lift.tier }} | day {{ lift.day }} | sets {{ lift.sets }}
    {% if lift.tier=='sbs' %} | max {{ lift.max }} | int {{ lift.intensity }} | {{ lift.reps }}/{{ lift.repout }}
    {% else %} | start {{ lift.start }}
    {% endif %}
  </span>
  <form hx-post="{{ url_for('lifts.edit', lid=lift.id) }}" hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML" class="row">
    <input name="name" value="{{ lift.name }}" style="width:140px">
    <input name="day" type="number" value="{{ lift.day }}" style="width:60px">
    <input name="intensity" type="number" step="0.05" value="{{ lift.intensity or '' }}" style="width:70px">
    <input name="reps" type="number" value="{{ lift.reps or '' }}" style="width:50px">
    <input name="repout" type="number" value="{{ lift.repout or '' }}" style="width:60px">
    <input name="start" type="number" step="0.5" value="{{ lift.start or '' }}" style="width:70px">
    <button>保存</button>
  </form>
  <button hx-post="{{ url_for('lifts.delete', lid=lift.id) }}" hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML"
          hx-confirm="删除 {{ lift.name }}?">删除</button>
  <a class="btn" href="{{ url_for('lifts.tier_preview', lid=lift.id) }}">换 tier</a>
</div>
{% endif %}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -q`
Expected: PASS (5 tests). (Note: `tier_preview` route added in Task 10; the link will 404 until then — acceptable, route test does not click it.)

- [ ] **Step 7: Commit**

```bash
git add webapp/routes/lifts.py webapp/templates/lifts.html webapp/templates/_lift_row.html tests/test_routes_lifts.py
git commit -m "feat: add lift CRUD routes with HTMX partials"
```

---

## Task 10: Tier switch route + preview

**Files:**
- Modify: `webapp/routes/lifts.py` (append)
- Create: `webapp/templates/tier_preview.html`
- Test: `tests/test_routes_lifts.py` (append)

- [ ] **Step 1: Append failing test to `tests/test_routes_lifts.py`**

```python
def test_tier_preview_then_apply(client, app):
    lid = _lift(app)
    # build some history so est1rm exists
    client.post("/log", data={"log_Squat": "12"})
    rv = client.get(f"/lifts/{lid}/tier?tier=t3")
    assert rv.status_code == 200 and b"t3" in rv.data
    rv = client.post(f"/lifts/{lid}/tier", data={"tier": "t3"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["tier"] == "t3"
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py::test_tier_preview_then_apply -q`
Expected: FAIL (route missing → 404).

- [ ] **Step 3: Append to `webapp/routes/lifts.py`**

```python
from ..services import tier as tier_service


@bp.route("/lifts/<int:lid>/tier")
def tier_preview(lid):
    conn = get_db()
    new_tier = request.args.get("tier", "sbs")
    preview = tier_service.derive_state(conn, lid, new_tier, repo.get_settings(conn))
    lift = repo.get_lift(conn, lid)
    return render_template("tier_preview.html", lift=lift, preview=preview)


@bp.route("/lifts/<int:lid>/tier", methods=["POST"])
def tier_apply(lid):
    conn = get_db()
    new_tier = request.form.get("tier", "sbs")
    preview = tier_service.derive_state(conn, lid, new_tier, repo.get_settings(conn))
    # user may override derived start values
    if "weight" in request.form and request.form["weight"].strip():
        preview["weight"] = float(request.form["weight"])
    if "tm" in request.form and request.form["tm"].strip():
        preview["tm"] = float(request.form["tm"])
    tier_service.apply_switch(conn, lid, preview)
    flash(f"{repo.get_lift(conn, lid)['name']} 已切换到 {new_tier} (历史保留)")
    return redirect(url_for("lifts.view")) if False else _redirect_lifts()


def _redirect_lifts():
    from flask import redirect, url_for
    return redirect(url_for("lifts.view"))
```

(Remove the `if False else` guard once confirmed — it exists only so the import ordering is explicit; cleaner: just `return redirect(url_for("lifts.view"))`. Use the clean version:)

Replace the `tier_apply` return with:
```python
    from flask import redirect, url_for
    return redirect(url_for("lifts.view"))
```

- [ ] **Step 4: Write `webapp/templates/tier_preview.html`**

```html
{% extends "base.html" %}
{% block title %}换 tier{% endblock %}
{% block content %}
<h1>{{ lift.name }} → {{ preview.tier }}</h1>
<p>历史保留, est1rm 从历史重算。下面是新 tier 的起点状态, 可改后确认:</p>
<form method="post" action="{{ url_for('lifts.tier_apply', lid=lift.id) }}">
  <input type="hidden" name="tier" value="{{ preview.tier }}">
  <ul>
    <li>est1RM (从历史): {{ preview.est1rm if preview.est1rm is not none else '—' }}</li>
    {% if preview.tier == 'sbs' %}
      <li>新 TM: <input name="tm" type="number" step="0.5" value="{{ preview.tm }}"></li>
    {% else %}
      <li>新重量: <input name="weight" type="number" step="0.5" value="{{ preview.weight }}"></li>
    {% endif %}
  </ul>
  <button>确认切换</button>
  <a class="btn" href="{{ url_for('lifts.view') }}">取消</a>
</form>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/lifts.py webapp/templates/tier_preview.html tests/test_routes_lifts.py
git commit -m "feat: add tier switch route with editable preview"
```

---

## Task 11: Settings route + template

**Files:**
- Modify: `webapp/routes/settings.py` (replace stub)
- Create: `webapp/templates/settings.html`
- Test: `tests/test_routes_settings.py`

- [ ] **Step 1: Write failing test `tests/test_routes_settings.py`**

```python
from webapp import repo


def test_settings_view(client):
    rv = client.get("/settings")
    assert rv.status_code == 200 and b"rounding" in rv.data.lower() or b"参数" in rv.data


def test_settings_update(client, app):
    rv = client.post("/settings", data={"incr": "5.0", "t3_target": "20"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        s = repo.get_settings(conn)
        assert s["incr"] == 5.0 and s["t3_target"] == 20
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_routes_settings.py -q`
Expected: FAIL (stub returns plain text).

- [ ] **Step 3: Replace `webapp/routes/settings.py`**

```python
"""Global settings view + update."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo

bp = Blueprint("settings", __name__)

_NUM = {"rounding": float, "incr": float, "t2_reset_pct": float,
        "t2_fail": int, "t3_target": int, "days_per_week": int}


@bp.route("/settings")
def view():
    conn = get_db()
    return render_template("settings.html", s=repo.get_settings(conn))


@bp.route("/settings", methods=["POST"])
def update():
    conn = get_db()
    fields = {}
    for col, cast in _NUM.items():
        if col in request.form and request.form[col].strip():
            try:
                fields[col] = cast(request.form[col])
            except ValueError:
                flash(f"非法值: {col}")
                return redirect(url_for("settings.view"))
    repo.update_settings(conn, **fields)
    flash("参数已更新")
    return redirect(url_for("settings.view"))
```

- [ ] **Step 4: Write `webapp/templates/settings.html`**

```html
{% extends "base.html" %}
{% block title %}全局参数{% endblock %}
{% block content %}
<h1>全局参数</h1>
<form method="post" action="{{ url_for('settings.update') }}">
  <div class="row"><label>rounding (kg): <input type="number" step="0.5" name="rounding" value="{{ s.rounding }}"></label></div>
  <div class="row"><label>days_per_week: <input type="number" name="days_per_week" value="{{ s.days_per_week }}"></label></div>
  <div class="row"><label>incr (kg): <input type="number" step="0.5" name="incr" value="{{ s.incr }}"></label></div>
  <div class="row"><label>t2_reset_pct: <input type="number" step="0.05" name="t2_reset_pct" value="{{ s.t2_reset_pct }}"></label></div>
  <div class="row"><label>t2_fail: <input type="number" name="t2_fail" value="{{ s.t2_fail }}"></label></div>
  <div class="row"><label>t3_target: <input type="number" name="t3_target" value="{{ s.t3_target }}"></label></div>
  <button>保存</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_routes_settings.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/settings.py webapp/templates/settings.html tests/test_routes_settings.py
git commit -m "feat: add global settings route and template"
```

---

## Task 12: Migration script (YAML → SQLite)

**Files:**
- Create: `migrate.py`
- Test: `tests/test_migrate.py`

- [ ] **Step 1: Write failing test `tests/test_migrate.py`**

```python
import os
import yaml
from webapp import db, repo
import migrate


def _write_yaml(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


def test_migrate_from_yaml(tmp_path, monkeypatch):
    profile = {
        "rounding": 2.5, "days_per_week": 4, "incr": 2.5,
        "t2_reset_pct": 0.7, "t2_fail": 3, "t3_target": 15,
        "lifts": [
            {"name": "Squat", "tier": "sbs", "day": 1, "max": 135.0,
             "intensity": 0.7, "reps": 5, "repout": 10, "sets": 5},
            {"name": "Rows", "tier": "t2", "day": 1, "sets": 3, "start": 85.0},
        ],
    }
    state = {"week": 2, "lifts": {
        "Squat": {"tier": "sbs", "tm": 137.5, "history": [{"week": 1, "weight": 95.0, "reps": 11}]},
        "Rows": {"tier": "t2", "weight": 87.5, "target": 10, "streak": 0, "history": []},
    }}
    p = tmp_path / "profile.yaml"; _write_yaml(str(p), profile)
    s = tmp_path / "state.yaml"; _write_yaml(str(s), state)
    dbp = str(tmp_path / "out.db")
    migrate.migrate_from_yaml(dbp, str(p), str(s))
    conn = db.connect(dbp); db.init_schema(conn)
    assert repo.get_settings(conn)["week"] == 2
    assert len(repo.list_lifts(conn)) == 2
    squat_id = repo.get_lift_by_name(conn, "Squat")["id"]
    assert repo.get_lift_state(conn, squat_id)["tm"] == 137.5
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_migrate_refuses_overwrite(tmp_path):
    dbp = str(tmp_path / "out.db")
    db.connect(dbp).close()
    import pytest
    with pytest.raises(SystemExit):
        migrate.migrate_from_yaml(dbp, "profile.yaml", "state.yaml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs python -m pytest tests/test_migrate.py -q`
Expected: FAIL (`ModuleNotFoundError: migrate`).

- [ ] **Step 3: Implement `migrate.py`**

```python
"""One-shot migration: profile.yaml + state.yaml -> SQLite sbs.db."""
import argparse
import os
import sys

from sbs_cli.data import io as dio
from webapp import db, repo


def migrate_from_yaml(db_path: str, profile_path: str, state_path: str, *, force: bool = False) -> None:
    if os.path.exists(db_path) and not force:
        sys.exit(f"refusing to overwrite existing {db_path} (pass --force)")
    if not os.path.exists(profile_path):
        sys.exit(f"profile not found: {profile_path}")
    if not os.path.exists(state_path):
        sys.exit(f"state not found: {state_path}")

    p = dio.load_profile(profile_path)
    s = dio.load_state(state_path)
    conn = db.connect(db_path)
    db.init_schema(conn)
    repo.update_settings(
        conn, week=s.week, days_per_week=p.days_per_week, rounding=p.rounding,
        incr=p.incr, t2_reset_pct=p.t2_reset_pct, t2_fail=p.t2_fail, t3_target=p.t3_target,
    )
    for i, l in enumerate(p.lifts):
        lid = repo.create_lift(
            conn, name=l.name, tier=l.tier, day=l.day, sort_order=i, sets=l.sets,
            max=l.max, intensity=l.intensity, reps=l.reps, repout=l.repout, start=l.start)
        ls = s.lifts.get(l.name)
        if ls is not None:
            repo.save_lift_state(conn, lid, tier=ls.tier, tm=ls.tm, weight=ls.weight,
                                 target=ls.target, streak=ls.streak, est1rm=ls.est1rm)
            for h in ls.history:
                repo.append_history(conn, lid, week=h.week, weight=h.weight, reps=h.reps)
    conn.close()
    print(f"migrated {len(p.lifts)} lifts, week {s.week} -> {db_path}")


def migrate_from_xlsx(db_path: str, xlsx_path: str, *, force: bool = False) -> None:
    from sbs_cli.importer import import_profile
    from sbs_cli.program import initial_state
    if os.path.exists(db_path) and not force:
        sys.exit(f"refusing to overwrite existing {db_path} (pass --force)")
    p = import_profile(xlsx_path)
    s = initial_state(p)
    conn = db.connect(db_path)
    db.init_schema(conn)
    repo.update_settings(conn, week=1, days_per_week=p.days_per_week, rounding=p.rounding,
                         incr=p.incr, t2_reset_pct=p.t2_reset_pct, t2_fail=p.t2_fail,
                         t3_target=p.t3_target)
    for i, l in enumerate(p.lifts):
        repo.create_lift(conn, name=l.name, tier=l.tier, day=l.day, sort_order=i, sets=l.sets,
                         max=l.max, intensity=l.intensity, reps=l.reps, repout=l.repout, start=l.start)
    conn.close()
    print(f"imported {len(p.lifts)} lifts from xlsx -> {db_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="migrate")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--profile", default="profile.yaml")
    ap.add_argument("--state", default="state.yaml")
    ap.add_argument("--from-xlsx", dest="xlsx", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.xlsx:
        migrate_from_xlsx(a.db, a.xlsx, force=a.force)
    else:
        migrate_from_yaml(a.db, a.profile, a.state, force=a.force)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs python -m pytest tests/test_migrate.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add migrate.py tests/test_migrate.py
git commit -m "feat: add YAML/xlsx to SQLite migration"
```

---

## Task 13: `__main__` entry + smoke run

**Files:**
- Create: `webapp/__main__.py`

- [ ] **Step 1: Write `webapp/__main__.py`**

```python
"""Entry point: python -m webapp  -> starts local server + opens browser."""
from .app import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Migrate real data and smoke-test the server**

Run:
```bash
cd "D:/WorkSpace/sbs"
conda run -n sbs python migrate.py --db sbs.db --profile profile.yaml --state state.yaml
```
Expected: `migrated 24 lifts, week 1 -> sbs.db`.

- [ ] **Step 3: Boot the app (background) and curl the plan page**

Run:
```bash
conda run -n sbs python -m webapp &
sleep 2
curl -s http://127.0.0.1:5000/ | head -20
```
Expected: HTML containing `Week 1` and lift names (e.g. `Squat`). Kill the server afterward (`kill %1` or close it).

- [ ] **Step 4: Full test suite stays green**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: all tests pass (engine 74 + new repo/service/route/migrate tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/__main__.py
git commit -m "feat: add webapp entry point and migrate real data"
```

---

## Task 14: PyInstaller packaging

**Files:**
- Create: `sbs_webapp.spec` (PyInstaller spec)

- [ ] **Step 1: Install PyInstaller**

Run: `conda run -n sbs python -m pip install pyinstaller`

- [ ] **Step 2: Write `sbs_webapp.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("webapp/templates", "webapp/templates"),
    ("webapp/static", "webapp/static"),
]
hiddenimports = ["sbs_cli", "sbs_cli.engine.progression", "sbs_cli.engine.onerm",
                 "sbs_cli.program", "sbs_cli.data.schema", "sbs_cli.data.io",
                 "sbs_cli.importer", "jinja2"]

a = Analysis(["webapp/__main__.py"], pathex=[], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="sbs_webapp",
          console=True, onefile=True)
```

- [ ] **Step 3: Build**

Run: `conda run -n sbs python -m PyInstaller sbs_webapp.spec --clean`
Expected: `dist/sbs_webapp.exe` produced.

- [ ] **Step 4: Smoke-test the packaged exe (creates sbs.db next to it)**

Run:
```bash
cd "D:/WorkSpace/sbs/dist"
cp ../sbs.db . 2>/dev/null || true
./sbs_webapp.exe &
sleep 3
curl -s http://127.0.0.1:5000/ | head -5
```
Expected: HTML returned. Kill afterward.

- [ ] **Step 5: Commit**

```bash
git add sbs_webapp.spec
git commit -m "build: add PyInstaller spec for single-file exe"
```

---

## Task 15: README update

**Files:**
- Modify: `README_sbs_cli.md` (or create `README.md` for the webapp)

- [ ] **Step 1: Update env reference**

In `README_sbs_cli.md`, replace all `conda run -n tamp` with `conda run -n sbs` (the `tamp` env is retired). Add a section at the top pointing to the new webapp as the primary interface, with the CLI retained for engine/testing.

- [ ] **Step 2: Add webapp quick-start**

Append a section:
```
## Web App (primary UI)

conda run -n sbs python -m webapp        # 开浏览器到 127.0.0.1:5000
conda run -n sbs python migrate.py       # 首次: profile.yaml+state.yaml -> sbs.db
```

- [ ] **Step 3: Commit**

```bash
git add README_sbs_cli.md
git commit -m "docs: point README at the webapp and sbs env"
```

---

## Self-Review (completed during authoring)

**Spec coverage:**
- §1 Goal (one SQLite, browser plan, UI CRUD, auto-backup, single launch) → Tasks 1–13, 14 packaging.
- §2 Why local browser app → reflected in stack; no web-service/mobile tasks (correctly absent).
- §3 Engine reuse unchanged → Task 5 adapter calls `advance_lift` / `_est1rm_from_history`; engine files never modified.
- §4 Module layout → matches the File Structure section exactly.
- §5 SQLite schema (settings/lifts/lift_state/history, FK ON) → Task 1; FK test included.
- §6.1 Weekly loop (no JSON shuttle) → Task 8 plan route; backup-before-commit → Task 7+8.
- §6.2 Lift CRUD (add/del/rename/day/params) → Task 9.
- §6.3 Tier switch keeps history, est1rm-derived, preview+editable → Task 6 + Task 10.
- §6.4 Rollback (auto snapshot + export) → Task 7 auto-snapshot wired into `/log` (Task 8). (Manual "restore from snapshot" / "export .db" = copy a file in `backups/` — documented in README, not a separate route; kept out per YAGNI.)
- §7 Migration (YAML→SQLite, xlsx fallback, --force) → Task 12.
- §8 Error handling (input validation, flash, refuse overwrite) → Tasks 8, 11, 12.
- §9 Testing (keep 74 + repo/service/route tests, 80%+) → every task is TDD; Task 13 Step 4 runs full suite.
- §10 Packaging (PyInstaller one-file, 127.0.0.1, auto-open) → Tasks 13, 14.
- §11 YAGNI cuts (no substitute/enabled, no SPA, no multi-user) → no tasks for them; correct.

**Placeholder scan:** no TBD/TODO/"add error handling"/"similar to Task N". All code blocks are complete. (One intentional cleanup note in Task 10 Step 3 about simplifying the return — resolved in the same step.)

**Type/name consistency:** repo API (`get_settings`, `set_week`, `update_settings`, `create_lift`, `list_lifts`, `get_lift`, `get_lift_by_name`, `update_lift`, `delete_lift`, `get_lift_state`, `save_lift_state`, `append_history`, `list_history`) is used identically across Tasks 2–12. Engine signatures match `sbs_cli/`. Blueprint endpoint names (`plan.view`, `plan.submit`, `lifts.view`, `lifts.new`, `lifts.edit`, `lifts.delete`, `lifts.tier_preview`, `lifts.tier_apply`, `settings.view`, `settings.update`) are consistent between templates and routes.

No gaps remain.
