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


# ---------- lift_state ----------
_STATE_COLS = ("tier", "tm", "weight", "target", "streak", "est1rm")


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


# ---------- week_log (per-week last-set reps, saved immediately, not yet advanced) ----------
def save_log(conn: sqlite3.Connection, lift_id: int, week: int, reps: int) -> None:
    """Upsert this lift's logged last-set reps for the given week."""
    conn.execute(
        "INSERT INTO week_log (lift_id, week, reps) VALUES (?, ?, ?) "
        "ON CONFLICT(lift_id, week) DO UPDATE SET reps=excluded.reps",
        (lift_id, week, reps),
    )
    conn.commit()


def clear_one_log(conn: sqlite3.Connection, lift_id: int, week: int) -> None:
    conn.execute("DELETE FROM week_log WHERE lift_id = ? AND week = ?", (lift_id, week))
    conn.commit()


def get_week_logs(conn: sqlite3.Connection, week: int) -> dict:
    rows = conn.execute("SELECT lift_id, reps FROM week_log WHERE week = ?", (week,)).fetchall()
    return {r["lift_id"]: r["reps"] for r in rows}


def clear_week_logs(conn: sqlite3.Connection, week: int) -> None:
    conn.execute("DELETE FROM week_log WHERE week = ?", (week,))
    conn.commit()
