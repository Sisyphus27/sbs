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


# ---------- lift_state (read; full CRUD in Task 4) ----------
def get_lift_state(conn: sqlite3.Connection, lift_id: int):
    return conn.execute("SELECT * FROM lift_state WHERE lift_id = ?", (lift_id,)).fetchone()
