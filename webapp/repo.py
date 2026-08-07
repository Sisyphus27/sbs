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


# ---------- v1 training facts ----------
_TRAINING_SLOT_SELECT = (
    "SELECT ps.id, e.name, e.load_model, ps.mode, ps.day, ps.sort_order, "
    "ps.sets, ps.max_seed AS max, ps.intensity, ps.reps, ps.repout, "
    "ps.start_weight AS start, ps.lift_kind, ps.increment AS incr, "
    "ps.bodyweight_pct FROM program_slot AS ps "
    "JOIN exercise AS e ON e.id = ps.exercise_id "
)


def get_training_slot(conn: sqlite3.Connection, slot_id: int):
    """Return one v1 slot in the row shape consumed by the existing Mode handlers."""
    return conn.execute(
        _TRAINING_SLOT_SELECT + "WHERE ps.id = ?", (slot_id,)
    ).fetchone()


def list_training_slots(conn: sqlite3.Connection):
    return conn.execute(
        _TRAINING_SLOT_SELECT + "ORDER BY ps.day, ps.sort_order, ps.id"
    ).fetchall()


def get_training_state(conn: sqlite3.Connection, slot_id: int):
    return conn.execute(
        "SELECT slot_id AS lift_id, mode, tm, weight, target, streak, est1rm, "
        "reseeded_cycle FROM strength_state WHERE slot_id = ?",
        (slot_id,),
    ).fetchone()


_TRAINING_SLOT_EDIT_COLUMNS = {
    "day": "day",
    "sets": "sets",
    "max": "max_seed",
    "intensity": "intensity",
    "reps": "reps",
    "repout": "repout",
    "start": "start_weight",
    "lift_kind": "lift_kind",
    "incr": "increment",
    "bodyweight_pct": "bodyweight_pct",
}


def update_training_slot(conn: sqlite3.Connection, slot_id: int, **fields) -> None:
    """Update ordinary v1 plan fields; mode is deliberately not accepted."""
    name = fields.pop("name", None)
    bad = set(fields) - set(_TRAINING_SLOT_EDIT_COLUMNS)
    if bad:
        raise ValueError(f"unknown training slot columns: {bad}")
    if name is not None:
        conn.execute(
            "UPDATE exercise SET name = ? WHERE id = "
            "(SELECT exercise_id FROM program_slot WHERE id = ?)",
            (name, slot_id),
        )
    if fields:
        assignments = ", ".join(
            f"{_TRAINING_SLOT_EDIT_COLUMNS[field]} = ?" for field in fields
        )
        conn.execute(
            f"UPDATE program_slot SET {assignments} WHERE id = ?",
            (*fields.values(), slot_id),
        )


def switch_training_mode(conn: sqlite3.Connection, slot_id: int, *, mode: str,
                         tm, weight, target, streak: int, est1rm) -> None:
    """Update the two sides of a v1 slot/state mode switch without committing."""
    slot_update = conn.execute(
        "UPDATE program_slot SET mode = ? WHERE id = ?", (mode, slot_id)
    )
    state_update = conn.execute(
        "UPDATE strength_state SET mode = ?, tm = ?, weight = ?, target = ?, "
        "streak = ?, est1rm = ? WHERE slot_id = ?",
        (mode, tm, weight, target, streak, est1rm, slot_id),
    )
    if slot_update.rowcount != 1 or state_update.rowcount != 1:
        raise ValueError("unknown training slot")


def set_training_reseed(conn: sqlite3.Connection, slot_id: int, *, cycle: int,
                        new_max=None) -> None:
    """Apply the existing cycle reseed semantics to one v1 slot/state pair."""
    state_update = conn.execute(
        "UPDATE strength_state SET reseeded_cycle = ? "
        "WHERE slot_id = ? AND mode = 'sbs' AND EXISTS "
        "(SELECT 1 FROM program_slot WHERE id = ? AND mode = 'sbs')",
        (cycle, slot_id, slot_id),
    )
    if state_update.rowcount != 1:
        raise ValueError("unknown training slot")
    if new_max is not None:
        conn.execute(
            "UPDATE program_slot SET max_seed = ? WHERE id = ?",
            (new_max, slot_id),
        )
        conn.execute(
            "UPDATE strength_state SET tm = ? WHERE slot_id = ?",
            (new_max, slot_id),
        )


def get_training_session(conn: sqlite3.Connection, *, program_week: int, day: int):
    return conn.execute(
        "SELECT * FROM training_session WHERE program_week = ? AND day = ?",
        (program_week, day),
    ).fetchone()


def create_training_session(conn: sqlite3.Connection, *, program_week: int, day: int,
                            training_date, bodyweight_kg) -> int:
    return conn.execute(
        "INSERT INTO training_session "
        "(program_week, day, training_date, bodyweight_kg) VALUES (?, ?, ?, ?)",
        (program_week, day, training_date, bodyweight_kg),
    ).lastrowid


def update_training_session(conn: sqlite3.Connection, session_id: int,
                            **fields) -> None:
    allowed = {"training_date", "bodyweight_kg"}
    if not fields:
        return
    if set(fields) - allowed:
        raise ValueError("unknown training session field")
    assignments = ", ".join(f"{column} = ?" for column in fields)
    conn.execute(
        f"UPDATE training_session SET {assignments} WHERE id = ?",
        (*fields.values(), session_id),
    )


def create_prescription_snapshot(conn: sqlite3.Connection, values: dict) -> None:
    columns = tuple(values)
    placeholders = ", ".join("?" for _ in columns)
    snapshot_columns = tuple(
        column for column in columns if column not in {"session_id", "slot_id"}
    )
    assignments = ", ".join(
        f"{column}=excluded.{column}" for column in snapshot_columns
    )
    conn.execute(
        f"INSERT INTO progression_event ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON CONFLICT(session_id, slot_id) DO UPDATE SET "
        f"{assignments} WHERE progression_event.mode IS NULL",
        tuple(values[column] for column in columns),
    )


def clear_progression_driver(conn: sqlite3.Connection, *, session_id: int,
                             slot_id: int) -> None:
    conn.execute(
        "UPDATE set_log SET drives_progression = 0 "
        "WHERE session_id = ? AND slot_id = ? AND drives_progression = 1",
        (session_id, slot_id),
    )


def upsert_training_set(conn: sqlite3.Connection, *, session_id: int, slot_id: int,
                        set_number: int, actual_added_weight: float, reps: int,
                        warmup: bool, drives_progression: bool,
                        e1rm_qualified: bool) -> None:
    conn.execute(
        "INSERT INTO set_log "
        "(session_id, slot_id, set_number, actual_added_weight, reps, warmup, "
        "drives_progression, e1rm_qualified) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(session_id, slot_id, set_number) DO UPDATE SET "
        "actual_added_weight=excluded.actual_added_weight, reps=excluded.reps, "
        "warmup=excluded.warmup, drives_progression=excluded.drives_progression, "
        "e1rm_qualified=excluded.e1rm_qualified",
        (session_id, slot_id, set_number, actual_added_weight, reps,
         int(warmup), int(drives_progression), int(e1rm_qualified)),
    )


def list_training_facts(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT ts.id AS session_id, ts.program_week, ts.day, ts.training_date, "
        "ts.bodyweight_kg, ts.finalized_at, sl.slot_id, e.name AS exercise_name, "
        "e.load_model, sl.set_number, sl.actual_added_weight, sl.reps, sl.warmup, "
        "sl.drives_progression, sl.e1rm_qualified, pe.mode, pe.planned_sets, "
        "pe.planned_reps, "
        "pe.planned_repout, pe.planned_target, pe.planned_intensity, "
        "pe.planned_added_weight, pe.planned_working_weight, pe.bodyweight_pct "
        "FROM set_log AS sl "
        "JOIN training_session AS ts ON ts.id = sl.session_id "
        "JOIN program_slot AS ps ON ps.id = sl.slot_id "
        "JOIN exercise AS e ON e.id = ps.exercise_id "
        "JOIN progression_event AS pe "
        "ON pe.session_id = sl.session_id AND pe.slot_id = sl.slot_id "
        "ORDER BY ts.program_week, ts.day, sl.slot_id, sl.set_number"
    ).fetchall()


def list_progression_drivers(conn: sqlite3.Connection, *, program_week: int):
    """Return the one explicit progression set for each current-week session-slot."""
    return conn.execute(
        "SELECT ts.id AS session_id, ts.program_week, ts.day, ts.bodyweight_kg, "
        "sl.slot_id, sl.set_number, sl.actual_added_weight, sl.reps, "
        "sl.e1rm_qualified, "
        "e.name, e.load_model, "
        "ps.lift_kind, ps.mode AS current_slot_mode, "
        "ss.mode AS current_state_mode, pe.mode, pe.planned_sets, pe.planned_reps, "
        "pe.planned_repout, pe.planned_target, pe.planned_intensity, "
        "pe.bodyweight_pct, pe.state_tm, pe.state_weight, pe.state_target, "
        "pe.state_streak, COALESCE(pe.state_est1rm, ss.est1rm) AS state_est1rm, "
        "pe.rounding, pe.increment, pe.t2_reset_pct, pe.t2_fail, pe.t3_target "
        "FROM set_log AS sl "
        "JOIN training_session AS ts ON ts.id = sl.session_id "
        "JOIN program_slot AS ps ON ps.id = sl.slot_id "
        "JOIN exercise AS e ON e.id = ps.exercise_id "
        "JOIN strength_state AS ss ON ss.slot_id = sl.slot_id "
        "JOIN progression_event AS pe "
        "ON pe.session_id = sl.session_id AND pe.slot_id = sl.slot_id "
        "WHERE ts.program_week = ? AND ts.finalized_at IS NULL "
        "AND sl.drives_progression = 1 AND sl.warmup = 0 "
        "ORDER BY ts.day, sl.slot_id",
        (program_week,),
    ).fetchall()


def save_training_state(conn: sqlite3.Connection, slot_id: int, *, mode: str,
                        tm, weight, target, streak: int, est1rm) -> None:
    cursor = conn.execute(
        "UPDATE strength_state SET mode = ?, tm = ?, weight = ?, target = ?, "
        "streak = ?, est1rm = ? WHERE slot_id = ?",
        (mode, tm, weight, target, streak, est1rm, slot_id),
    )
    if cursor.rowcount != 1:
        raise sqlite3.IntegrityError("missing strength state")


def save_sbs_historical_peak(conn: sqlite3.Connection, slot_id: int,
                             peak_e1rm: float) -> None:
    cursor = conn.execute(
        "UPDATE strength_state SET est1rm = "
        "CASE WHEN est1rm IS NULL OR est1rm < ? THEN ? ELSE est1rm END "
        "WHERE slot_id = ? AND mode = 'sbs'",
        (peak_e1rm, peak_e1rm, slot_id),
    )
    if cursor.rowcount != 1:
        raise sqlite3.IntegrityError("missing SBS strength state")


def finalize_training_sessions(conn: sqlite3.Connection, *, program_week: int,
                               finalized_at: str) -> None:
    conn.execute(
        "UPDATE training_session SET finalized_at = ? "
        "WHERE program_week = ? AND finalized_at IS NULL",
        (finalized_at, program_week),
    )


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
