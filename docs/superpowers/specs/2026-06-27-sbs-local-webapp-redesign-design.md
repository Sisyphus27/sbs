# Design: SBS Local Web App (Redesign)

**Date:** 2026-06-27
**Status:** Approved (brainstorming lock) — pending implementation plan
**Relationship to prior work:** Supersedes the CLI+HTML approach (`2026-06-26-sbs-cli-program-design.md`). The CLI delivered a proven, fully unit-tested engine (74 tests, three-tier progression: SBS autoregulation, GZCLP T2 state machine, T3 threshold) but the **delivery layer** proved cumbersome in daily use:

- **Two-file data sync** — `profile.yaml` (user-edited) and `state.yaml` (program-written) can drift.
- **Manual initialization** — requires the `tamp` conda env, an xlsx import step, and hand-editing YAML.
- **No flexible editing** — every lift change (add/remove, day reassignment, intensity tweak, tier switch) means hand-editing YAML.
- **Weekly JSON shuttle** — the worst friction: generate `week-N.html`, open it on a device, fill last-set reps, **export a JSON**, transfer the JSON back to the PC, then run `sbs next log.json`.

This redesign **keeps the proven engine 100% unchanged** and replaces only the data layer (YAML → SQLite repository) and the delivery layer (CLI + static HTML + JSON shuttle → local browser app). The engine, the dataclass domain models, and the core orchestration are reused; only their I/O adapters change.

**Dev environment:** conda env **`sbs`** (Python 3.12.0), created 2026-06-27 to replace the old shared `tamp` env. All commands run as `conda run -n sbs ...`. As of creation the env is empty — `flask`, `jinja2`, `openpyxl`, `pytest` are installed on first implementation need; `sqlite3` is stdlib.

---

## 1. Goal

A **local browser app** (single-user, PC-only, run at home) that:

- Holds the whole program (SBS main/auxiliary + GZCLP back + accessories) in **one SQLite file**.
- Renders the weekly plan in the browser (no generated HTML files, no JSON shuttle).
- Accepts last-set reps through an in-page form; advances every lift automatically and renders the next week in the same view.
- Lets the user edit the program through a UI: add/remove/rename lifts, reassign days, change per-lift intensity parameters, switch progression tier — all without touching any text file.
- Backs up automatically before each advance and supports one-click rollback.
- Launches by a single command (or double-click of a packaged exe) that starts a local server bound to `127.0.0.1` and opens the default browser.

## 2. Why local browser app (not exe GUI, not web service, not enhanced CLI)

The user records training data **on a PC at home** — no phone, no multi-device sync, no other users. This eliminates web-service/cloud options and mobile packaging. Among local-only forms:

| Option | Verdict |
|---|---|
| Native window GUI (PyQt/Tkinter) | Rejected — large UI build effort, big package, no reuse of existing HTML/Jinja skills. |
| Enhanced CLI / TUI | Rejected — "flexible action editing" via typing commands is exactly the current YAML-editing pain. |
| **Local browser app** (Flask + Jinja + HTMX) | **Chosen.** Engine reused as-is, existing Jinja/HTML rendering reused, form submissions replace the JSON shuttle, single-file PyInstaller packaging. |
| SPA (FastAPI + React/Vue) | Rejected — overkill for a single-user local tool; doubles maintenance. |

**Stack:** Flask (backend + routing) · Jinja2 (server-rendered templates, reusing the existing HTML style) · HTMX (partial page updates for CRUD/day-reassignment without full reloads, minimal hand-written JS) · `sqlite3` (stdlib). No JS framework. No auth (localhost only). No external network.

## 3. Engine reuse (unchanged)

The pure-function engine stays **0-change**:

- `sbs_cli/engine/progression.py` — `sbs_next`, `t2_next`, `t3_next`, `round_weight`, `T2State`.
- `sbs_cli/engine/onerm.py` — `estimate_1rm` (Epley/Brzycki/Wathan average).
- `sbs_cli/program.py` — `advance_lift(profile, lift, state, actual_reps, week)` and `week_plan(...)` core logic.
- `sbs_cli/data/schema.py` — dataclass domain models (`Lift`, `Profile`, `LiftState`, `ProgramState`, `SetEntry`).

**Adapter pattern:** the engine consumes and mutates dataclasses. The SQLite repository reads rows → assembles dataclasses → the engine runs → the updated dataclasses are written back to SQLite. The engine never sees SQLite. This keeps the 74 existing tests valid and the engine independently testable.

## 4. Architecture / module layout

```
D:\WorkSpace\sbs\
├─ sbs_cli/                  # KEPT — engine untouched
│   ├─ engine/               # progression.py, onerm.py — 0 change
│   ├─ data/schema.py        # dataclass domain models — kept
│   └─ program.py            # advance_lift / week_plan — kept
├─ webapp/                   # NEW — local browser app
│   ├─ app.py                # Flask app factory, route registration, auto-open browser
│   ├─ db.py                 # sqlite3 connection + schema bootstrap (CREATE TABLE IF NOT EXISTS)
│   ├─ repo.py               # Repository layer: settings / lifts / lift_state / history CRUD
│   ├─ services/
│   │   └─ advance.py        # orchestrate engine over a logged week → write DB → week+1
│   ├─ routes/
│   │   ├─ plan.py           # GET /  weekly plan; POST /log submit last-set reps
│   │   ├─ lifts.py          # lift CRUD / day reassign / tier switch / param edit
│   │   └─ settings.py       # global params (rounding, incr, t2_reset_pct, t2_fail, t3_target, days_per_week)
│   └─ templates/            # Jinja: plan, lift_editor, settings (reuse existing HTML style)
├─ migrate.py                # one-shot YAML → SQLite (xlsx importer kept as fallback cold-start)
├─ backups/                  # auto snapshot of sbs.db before each advance (sbs-wN-<ts>.db.bak)
├─ sbs.db                    # the single data file (gitignored if a repo is later init'd)
└─ tests/                    # keep 74 engine tests + add repo / service / route tests
```

**Repository pattern** (per the project's `patterns.md` rule): business logic depends on the repository interface, not on SQLite directly, so the storage mechanism is swappable and testable with a temp DB.

## 5. Data model (SQLite)

Four tables in one `.db` file. `lifts` (config, user-edited) is split from `lift_state` (current mutable state, engine-written) for clear responsibility, but both live in one DB with one writer (the app) — no more two-file drift.

```sql
-- Global parameters (single row)
settings(
    week           INTEGER,
    days_per_week  INTEGER,
    rounding       REAL,    -- kg granularity (= MROUND step)
    incr           REAL,    -- T2/T3 weekly increment (kg)
    t2_reset_pct   REAL,    -- T2 reset weight = pct * est1RM
    t2_fail        INTEGER, -- T2 consecutive misses before downgrade
    t3_target      INTEGER  -- T3 last-set target reps
)

-- Lift configuration (user-edited)
lifts(
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE,
    tier        TEXT CHECK (tier IN ('sbs','t2','t3')),
    day         INTEGER,
    sort_order  INTEGER,           -- ordering within a day
    sets        INTEGER,
    max         REAL,              -- sbs only (training max basis)
    intensity   REAL,              -- sbs only (weekly work weight = tm * intensity)
    reps        INTEGER,           -- sbs only
    repout      INTEGER,           -- sbs only (AMRAP target)
    start       REAL               -- t2/t3 starting weight
)

-- Lift state (engine-written, 1:1 with lifts)
lift_state(
    lift_id   INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
    tm        REAL,        -- sbs: training max
    weight    REAL,        -- t2/t3: current working weight
    target    INTEGER,     -- t2: current rep target (10/8/6)
    streak    INTEGER,     -- t2: consecutive fail count
    est1rm    REAL         -- derived from history, tier-agnostic
)

-- History (append-only, 1:N with lifts)
history(
    id        INTEGER PRIMARY KEY,
    lift_id   INTEGER REFERENCES lifts(id) ON DELETE CASCADE,
    week      INTEGER,
    weight    REAL,
    reps      INTEGER,
    ts        TEXT          -- ISO timestamp
)
```

Foreign keys are enabled per-connection (`PRAGMA foreign_keys = ON`).

## 6. Data flow

### 6.1 Weekly loop (the core simplification)

```
GET  /        → repo reads settings + lifts + lift_state → render weekly plan (no week-N.html file)
[fill last-set reps in the page form]
POST /log     → advance service:
                  for each logged lift:
                      dataclass ← repo
                      advance_lift(profile, lift, state, reps, week)   # engine, reused
                      repo ← dataclass   (writes lift_state + appends history)
                  cp sbs.db → backups/sbs-wN-<ts>.db.bak   (before commit)
                  settings.week += 1
                  render next week's plan
```

Everything happens inside the browser. **The JSON shuttle, the terminal commands, and the device-to-PC transfer are eliminated.**

### 6.2 Lift CRUD (all the editing the user asked for)

- **Add / delete / rename** a lift → HTMX partial-refresh of the list.
- **Reassign day**: dropdown or drag → `hx-post` updates `day` and `sort_order`.
- **Edit per-lift params**: inline editing of `intensity` / `reps` / `repout` / `sets` / `max` / `start`.
- **Switch tier** with history preserved (see §6.3).

### 6.3 Tier switch — keep history, change rule only

Each tier uses different state fields (`sbs`: `tm`; `t2`: `weight`/`target`/`streak`; `t3`: `weight`). Switching tier keeps all past performance but must re-derive the new tier's starting state:

```
On tier switch:
    history      → fully preserved (no rows deleted)
    est1rm       → recomputed from history (unchanged; it is tier-agnostic)
    new-tier starting state, derived from est1rm:
        sbs : tm     = est1rm      (fallback: the lift's configured max)
        t2 :  weight = round(est1rm * t2_reset_pct); target = 10; streak = 0
              (fallback: configured start)
        t3 :  weight = round(est1rm * 0.6)   (fallback: configured start)
    → show a preview page; the user may edit these derived start values before confirming
      (nothing is overwritten blindly)
```

Rationale: history is the truth of past performance; est1rm is a tier-agnostic strength measure, so it is the most sensible basis for the new tier's starting state. Preview + edit protects against a bad derivation.

### 6.4 Rollback

`backups/` holds an auto-snapshot before every advance (`sbs-wN-<ts>.db.bak`). The settings page exposes "restore from snapshot" and "export .db".

## 7. Migration path (YAML → SQLite)

One-shot migrator `migrate.py`:

- Reads the existing `profile.yaml` + `state.yaml` → writes into a fresh `sbs.db`.
- Preserves all hand-tuned config (day assignments, intensities, 1RMs, tiers) and the current week's state.
- Current `state.yaml` is at week 1 with empty history, so the migration is light (mostly the profile config).
- The xlsx importer (`sbs_cli/importer.py`) is **kept** as a fallback cold-start path (`migrate.py --from-xlsx backup/00_cold_backup.xlsx`), not the default.
- Idempotent: refuses to overwrite an existing `sbs.db` unless `--force`.

## 8. Error handling

- **Input validation** at boundaries: last-set reps must be a non-negative integer; weight/start/max must be positive. Invalid input → Flask flash message, no DB write.
- **DB locked / corrupt**: friendly error page pointing to the most recent `backups/` snapshot.
- **Tier switch / destructive edits**: always go through the preview-confirm flow (§6.3).
- Migration safety: refuse overwrite without `--force`.

## 9. Testing

- **Keep** the 74 existing engine tests (engine unchanged, so they stay green).
- **Add** repository tests (CRUD on a temp in-memory SQLite).
- **Add** advance-service integration tests (temp DB, full week advance, est1rm + history assertions).
- **Add** Flask route tests via the test client (plan render, log submit, CRUD endpoints, tier switch with history preserved).
- Target ≥ 80% coverage on new code.

## 10. Packaging & launch

- **Dev**: `conda run -n sbs python -m webapp` (or `python webapp/app.py`) → Flask starts on `127.0.0.1:<port>` → auto-opens the default browser.
- **Packaged**: PyInstaller one-file exe bundling Flask + Jinja + templates + static assets; the `sbs.db` lives next to the exe. Double-click to run.
- Server binds `127.0.0.1` only (no LAN exposure, no auth needed).

## 11. Out of scope (YAGNI — explicitly cut)

- **Multi-user / auth / cloud sync** — single user, PC-only.
- **Mobile / responsive phone-first UX** — used on a home PC.
- **Substitute / "enabled toggle" concept** — redundant with CRUD (just add/edit/rename a lift). No `enabled` column.
- **SPA / JS framework** — server-rendered Jinja + HTMX is sufficient.
- **Tier switch that resets history** — rejected; history is preserved, only the rule changes (§6.3).

## 12. Open items deferred to the implementation plan

- Concrete port selection + browser-open helper library (e.g. `webbrowser` stdlib vs `waitress` for production-ish serving under PyInstaller).
- Whether `program.py` is refactored to accept a repository or stays fed dataclasses by a thin caller in `services/advance.py` (lean toward the latter — keep `program.py` unchanged).
- Template/HTMX interaction specifics (drag-drop library choice) — resolved during implementation.
