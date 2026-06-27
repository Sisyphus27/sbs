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
