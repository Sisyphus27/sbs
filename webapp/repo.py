"""SQLite repository: settings / lifts / lift_state / history CRUD."""
from typing import Optional
import sqlite3


def row_get(row, col: str, default=None):
    """Null-tolerant column read on a sqlite3.Row (or dict).

    Migration-era columns (bodyweight, bodyweight_pct, incr) may be absent on
    older rows; subscript access raises. This is the single accessor for that
    tolerance — do not re-litigate `x if col in row.keys() else default` at
    call sites (ADR 0004 shim)."""
    return row[col] if col in row.keys() else default

_SETTINGS_COLS = ("week", "days_per_week", "rounding", "incr",
                  "t2_reset_pct", "t2_fail", "t3_target", "bodyweight")


# ---------- settings ----------
def get_settings(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def set_week(conn: sqlite3.Connection, week: int) -> None:
    conn.execute("UPDATE settings SET week = ?", (week,))


def increment_week_if_current(conn: sqlite3.Connection, expected_week: int) -> bool:
    cursor = conn.execute(
        "UPDATE settings SET week = week + 1 WHERE id = 1 AND week = ?",
        (expected_week,),
    )
    return cursor.rowcount == 1


def lock_week_if_current(conn: sqlite3.Connection, expected_week: int) -> bool:
    cursor = conn.execute(
        "UPDATE settings SET week = week WHERE id = 1 AND week = ?",
        (expected_week,),
    )
    return cursor.rowcount == 1


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
_LIFT_COLS = ("name", "load_model", "mode", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start", "lift_kind", "incr",
              "bodyweight_pct")


def create_lift(conn: sqlite3.Connection, *, name: str,
                load_model: str, mode: str, day: int,
                sort_order: int, sets: int, max, intensity, reps, repout,
                start, lift_kind=None, incr=None,
                bodyweight_pct: float = 0.0) -> int:
    from sbs_cli.data.schema import is_legal_combo
    if not is_legal_combo(load_model, mode):
        raise ValueError(f"illegal load_model/mode: {load_model}/{mode}")
    cur = conn.execute(
        "INSERT INTO lifts (name, load_model, mode, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr, bodyweight_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, load_model, mode, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr,
         bodyweight_pct),
    )
    lid = cur.lastrowid
    _init_lift_state(conn, lid, mode, max, start)
    conn.commit()
    return lid


def _init_lift_state(conn, lid, mode, max, start):
    """Dispatch to the registered mode handler to seed lift_state (ADR 0005).

    Builds a throwaway Lift so the mode's initial_state() can run unchanged;
    persists only the scalar fields the DB cares about (history lives in the
    history table, not in lift_state)."""
    from sbs_cli.data.schema import Lift
    from sbs_cli.engine.modes import get_mode
    tmp = Lift(name="", day=1, load_model="barbell", mode=mode, max=max, start=start)
    s = get_mode(mode).initial_state(tmp, None)
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, tm, weight, target, streak, est1rm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lid, s.mode, s.tm, s.weight, s.target, s.streak, s.est1rm))


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
_STATE_COLS = ("mode", "tm", "weight", "target", "streak", "est1rm")


def save_lift_state(conn: sqlite3.Connection, lift_id: int, *, mode: str, tm,
                    weight, target, streak: int, est1rm) -> None:
    """Upsert lift_state from engine-produced fields. Does NOT touch history table
    (history is appended separately via append_history).

    Transaction boundary lives at the caller (ADR 0009 batch 2): this only
    executes — the owning service/route commits the unit of work."""
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, tm, weight, target, streak, est1rm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(lift_id) DO UPDATE SET "
        "mode=excluded.mode, tm=excluded.tm, weight=excluded.weight, "
        "target=excluded.target, streak=excluded.streak, est1rm=excluded.est1rm",
        (lift_id, mode, tm, weight, target, streak, est1rm),
    )


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


def list_history(conn: sqlite3.Connection, lift_id: int):
    return conn.execute(
        "SELECT * FROM history WHERE lift_id = ? ORDER BY id", (lift_id,)
    ).fetchall()


# ---------- week_log (per-week last-set reps, saved immediately, not yet advanced) ----------
# ADR 0009 batch 2: these execute only — the caller owns the commit. The autosave
# route commits per request; submit commits once after the advance+clear unit.
def save_log(conn: sqlite3.Connection, lift_id: int, week: int, reps: int) -> None:
    """Upsert this lift's logged last-set reps for the given week."""
    conn.execute(
        "INSERT INTO week_log (lift_id, week, reps) VALUES (?, ?, ?) "
        "ON CONFLICT(lift_id, week) DO UPDATE SET reps=excluded.reps",
        (lift_id, week, reps),
    )


def clear_one_log(conn: sqlite3.Connection, lift_id: int, week: int) -> None:
    conn.execute("DELETE FROM week_log WHERE lift_id = ? AND week = ?", (lift_id, week))


def get_week_logs(conn: sqlite3.Connection, week: int) -> dict:
    rows = conn.execute("SELECT lift_id, reps FROM week_log WHERE week = ?", (week,)).fetchall()
    return {r["lift_id"]: r["reps"] for r in rows}


def clear_week_logs(conn: sqlite3.Connection, week: int) -> None:
    conn.execute("DELETE FROM week_log WHERE week = ?", (week,))


# ---------- schedule (Task 5) ----------
def load_schedule(conn: sqlite3.Connection):
    """Return the schedule as a list of ScheduleRow (the dataclass the engine wants).
    Single loader used by every read path — do not inline this comprehension."""
    from sbs_cli.data.schema import ScheduleRow
    return [ScheduleRow(kind=r["kind"], week=r["week"], intensity=r["intensity"],
                        reps=r["reps"], repout=r["repout"])
            for r in conn.execute("SELECT * FROM sbs_schedule ORDER BY kind, week")]


def get_schedule(conn: sqlite3.Connection):
    """Raw sqlite3.Row view of the schedule (for the /schedule editor template)."""
    return conn.execute(
        "SELECT * FROM sbs_schedule ORDER BY kind, week"
    ).fetchall()


def replace_schedule(conn: sqlite3.Connection, rows) -> None:
    """Wipe + insert. `rows` is an iterable of (kind, week, intensity, reps, repout)."""
    conn.execute("DELETE FROM sbs_schedule")
    conn.executemany(
        "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
        "VALUES (?, ?, ?, ?, ?)",
        list(rows),
    )
    conn.commit()


def reset_schedule(conn: sqlite3.Connection) -> None:
    """Restore the 42-row DEFAULT_SCHEDULE (used by the /schedule reset button)."""
    from sbs_cli.defaults import DEFAULT_SCHEDULE
    replace_schedule(conn, [(r.kind, r.week, r.intensity, r.reps, r.repout)
                            for r in DEFAULT_SCHEDULE])


# ---------- reseed (Task 5) ----------
def set_reseed(conn: sqlite3.Connection, lift_id: int, *, cycle: int, new_max=None) -> None:
    """Stamp ``reseeded_cycle`` on an sbs lift; if ``new_max`` is given, also set
    ``lifts.max`` and ``lift_state.tm`` to it.

    This is the ONLY writer of ``reseeded_cycle`` besides the one-shot migration
    (Task 7). In particular ``save_lift_state`` deliberately omits the column so
    that ``advance_week``'s weekly UPSERT cannot clobber the reseed stamp (ADR 0002).
    """
    conn.execute(
        "UPDATE lift_state SET reseeded_cycle = ? WHERE lift_id = ?", (cycle, lift_id))
    if new_max is not None:
        conn.execute("UPDATE lifts SET max = ? WHERE id = ?", (new_max, lift_id))
        conn.execute("UPDATE lift_state SET tm = ? WHERE lift_id = ?", (new_max, lift_id))
    conn.commit()
