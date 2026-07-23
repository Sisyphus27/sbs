"""SQLite connection + schema bootstrap."""
import os
import sys
import sqlite3

# When frozen (PyInstaller onefile), __file__ is inside a temp extraction dir
# that is deleted on exit — so persist the DB next to the exe instead.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(_BASE_DIR, "sbs.db")

_SCHEMA = """
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
    load_model     TEXT NOT NULL DEFAULT 'barbell' CHECK (load_model IN ('barbell','bodyweight','pure_bodyweight')),
    mode           TEXT NOT NULL DEFAULT 'none' CHECK (mode IN ('sbs','linear_t2','linear_t3','none')),
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
    bodyweight_pct REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS lift_state (
    lift_id        INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
    mode           TEXT NOT NULL,
    tm             REAL,
    weight         REAL,
    target         INTEGER,
    streak         INTEGER NOT NULL DEFAULT 0,
    est1rm         REAL,
    reseeded_cycle INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
    week    INTEGER NOT NULL,
    weight  REAL NOT NULL,
    reps    INTEGER NOT NULL,
    ts      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS week_log (
    lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
    week    INTEGER NOT NULL,
    reps    INTEGER NOT NULL,
    PRIMARY KEY (lift_id, week)
);
CREATE TABLE IF NOT EXISTS sbs_schedule (
    kind      TEXT NOT NULL,
    week      INTEGER NOT NULL,
    intensity REAL NOT NULL,
    reps      INTEGER NOT NULL,
    repout    INTEGER NOT NULL,
    PRIMARY KEY (kind, week)
);
"""

_DEFAULT_SETTINGS = dict(
    week=1, days_per_week=4, rounding=2.5, incr=2.5,
    t2_reset_pct=0.75, t2_fail=3, t3_target=15, bodyweight=0.0,
)


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str,
                           decl: str) -> None:
    """ALTER TABLE add-column — used to migrate pre-bodyweight DBs (ADR 0004).
    Idempotent: no-op once the column exists. CREATE TABLE IF NOT EXISTS does
    NOT add columns to an existing table, so this path upgrades live user DBs."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # Migrate pre-bodyweight DBs (ADR 0004). Idempotent — no-op once present.
    # NOTE: the legacy tier/progression -> load_model/mode migration is handled
    # by the one-shot migrate_modes.py (T8); init_schema only bootstraps new DBs
    # (CREATE TABLE IF NOT EXISTS) and upgrades the orthogonal bodyweight cols.
    _add_column_if_missing(conn, "settings", "bodyweight", "REAL NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "lifts", "bodyweight_pct", "REAL NOT NULL DEFAULT 0.0")
    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO settings (id, week, days_per_week, rounding, incr, t2_reset_pct, t2_fail, t3_target, bodyweight) "
            "VALUES (1, :week, :days_per_week, :rounding, :incr, :t2_reset_pct, :t2_fail, :t3_target, :bodyweight)",
            _DEFAULT_SETTINGS,
        )
    # Task 5: seed the 42-row schedule table when empty (21 main + 21 aux).
    # Idempotent — re-running init_schema does NOT re-seed. The one-shot
    # migrate_schedule.py (Task 7) handles live DBs that pre-date this column.
    if conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 0:
        from sbs_cli.defaults import DEFAULT_SCHEDULE
        conn.executemany(
            "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r.kind, r.week, r.intensity, r.reps, r.repout) for r in DEFAULT_SCHEDULE],
        )
    conn.commit()


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
