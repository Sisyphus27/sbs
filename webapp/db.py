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
    t3_target    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lifts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
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
CREATE TABLE IF NOT EXISTS week_log (
    lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
    week    INTEGER NOT NULL,
    reps    INTEGER NOT NULL,
    PRIMARY KEY (lift_id, week)
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
