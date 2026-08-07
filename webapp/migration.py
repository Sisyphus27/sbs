"""One-time startup migration from the production v0 schema to v1."""

from datetime import datetime, timezone
import logging
import math
import sqlite3

from sbs_cli.defaults import DEFAULT_SCHEDULE
from .backup import snapshot


logger = logging.getLogger(__name__)


_BASE_SCHEMA = """
CREATE TABLE settings (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    week          INTEGER NOT NULL,
    days_per_week INTEGER NOT NULL,
    rounding      REAL    NOT NULL,
    incr          REAL    NOT NULL,
    t2_reset_pct  REAL    NOT NULL,
    t2_fail       INTEGER NOT NULL,
    t3_target     INTEGER NOT NULL,
    bodyweight    REAL    NOT NULL DEFAULT 0
);
CREATE TABLE sbs_schedule (
    kind      TEXT NOT NULL,
    week      INTEGER NOT NULL,
    intensity REAL NOT NULL,
    reps      INTEGER NOT NULL,
    repout    INTEGER NOT NULL,
    PRIMARY KEY (kind, week)
);
"""


_V1_SCHEMA = """
CREATE TABLE exercise (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    load_model TEXT NOT NULL
        CHECK (load_model IN ('barbell', 'bodyweight', 'pure_bodyweight')),
    category   TEXT
);
CREATE TABLE program_slot (
    id             INTEGER PRIMARY KEY
        REFERENCES strength_state(slot_id) DEFERRABLE INITIALLY DEFERRED,
    exercise_id    INTEGER NOT NULL REFERENCES exercise(id) ON DELETE RESTRICT,
    day            INTEGER NOT NULL CHECK (day > 0),
    sort_order     INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    mode           TEXT NOT NULL
        CHECK (mode IN ('sbs', 'linear_t2', 'linear_t3', 'none')),
    lift_kind      TEXT CHECK (lift_kind IS NULL OR lift_kind IN ('main', 'aux')),
    sets           INTEGER NOT NULL CHECK (sets > 0),
    reps           INTEGER CHECK (reps IS NULL OR reps > 0),
    repout         INTEGER CHECK (repout IS NULL OR repout > 0),
    target         INTEGER CHECK (target IS NULL OR target > 0),
    intensity      REAL CHECK (intensity IS NULL OR intensity > 0),
    max_seed       REAL,
    start_weight   REAL,
    increment      REAL CHECK (increment IS NULL OR increment > 0),
    bodyweight_pct REAL NOT NULL DEFAULT 0 CHECK (bodyweight_pct >= 0)
);
CREATE TABLE strength_state (
    slot_id          INTEGER PRIMARY KEY REFERENCES program_slot(id) ON DELETE CASCADE,
    mode             TEXT NOT NULL
        CHECK (mode IN ('sbs', 'linear_t2', 'linear_t3', 'none')),
    tm               REAL,
    weight           REAL,
    target           INTEGER CHECK (target IS NULL OR target > 0),
    streak           INTEGER NOT NULL DEFAULT 0 CHECK (streak >= 0),
    est1rm           REAL,
    reseeded_cycle   INTEGER NOT NULL DEFAULT 0 CHECK (reseeded_cycle >= 0)
);
CREATE TABLE training_session (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    program_week  INTEGER NOT NULL CHECK (program_week > 0),
    day           INTEGER NOT NULL CHECK (day > 0),
    training_date TEXT,
    bodyweight_kg REAL CHECK (bodyweight_kg IS NULL OR bodyweight_kg >= 0),
    finalized_at  TEXT,
    UNIQUE (program_week, day)
);
CREATE TABLE set_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL REFERENCES training_session(id) ON DELETE CASCADE,
    slot_id             INTEGER NOT NULL REFERENCES program_slot(id) ON DELETE RESTRICT,
    set_number          INTEGER NOT NULL CHECK (set_number > 0),
    actual_added_weight REAL,
    reps                INTEGER NOT NULL CHECK (reps >= 0),
    warmup              INTEGER NOT NULL DEFAULT 0 CHECK (warmup IN (0, 1)),
    drives_progression  INTEGER NOT NULL DEFAULT 0
        CHECK (drives_progression IN (0, 1)),
    UNIQUE (session_id, slot_id, set_number)
);
CREATE UNIQUE INDEX uq_set_log_progression_driver
    ON set_log(session_id, slot_id) WHERE drives_progression = 1;
CREATE TABLE progression_event (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL REFERENCES training_session(id) ON DELETE CASCADE,
    slot_id                INTEGER NOT NULL REFERENCES program_slot(id) ON DELETE RESTRICT,
    mode                   TEXT
        CHECK (mode IS NULL OR mode IN ('sbs', 'linear_t2', 'linear_t3', 'none')),
    planned_sets           INTEGER CHECK (planned_sets IS NULL OR planned_sets > 0),
    planned_reps           INTEGER CHECK (planned_reps IS NULL OR planned_reps > 0),
    planned_repout         INTEGER CHECK (planned_repout IS NULL OR planned_repout > 0),
    planned_target         INTEGER CHECK (planned_target IS NULL OR planned_target > 0),
    planned_intensity      REAL CHECK (planned_intensity IS NULL OR planned_intensity > 0),
    planned_added_weight   REAL,
    planned_working_weight REAL,
    bodyweight_pct         REAL CHECK (bodyweight_pct IS NULL OR bodyweight_pct >= 0),
    state_tm               REAL,
    state_weight           REAL,
    state_target           INTEGER CHECK (state_target IS NULL OR state_target > 0),
    state_streak           INTEGER CHECK (state_streak IS NULL OR state_streak >= 0),
    state_est1rm           REAL,
    rounding               REAL CHECK (rounding IS NULL OR rounding > 0),
    increment              REAL CHECK (increment IS NULL OR increment > 0),
    t2_reset_pct           REAL CHECK (t2_reset_pct IS NULL OR t2_reset_pct > 0),
    t2_fail                INTEGER CHECK (t2_fail IS NULL OR t2_fail > 0),
    t3_target              INTEGER CHECK (t3_target IS NULL OR t3_target > 0),
    UNIQUE (session_id, slot_id)
);
"""


_DEFAULT_SETTINGS = {
    "week": 1,
    "days_per_week": 4,
    "rounding": 2.5,
    "incr": 2.5,
    "t2_reset_pct": 0.75,
    "t2_fail": 3,
    "t3_target": 15,
    "bodyweight": 0.0,
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _snapshot_week(conn: sqlite3.Connection) -> int:
    """Return only a trustworthy week for naming a pre-migration snapshot."""
    try:
        row = conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()
    except sqlite3.Error:
        return 0
    if row is None or not isinstance(row[0], int) or row[0] < 1:
        return 0
    return row[0]


def _add_e1rm_qualified_column(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE set_log ADD COLUMN e1rm_qualified "
        "INTEGER NOT NULL DEFAULT 0 CHECK (e1rm_qualified IN (0, 1))"
    )


def _create_fresh(conn: sqlite3.Connection, *, version: int) -> None:
    if version not in (1, 2):
        raise ValueError("fresh schema version must be 1 or 2")
    conn.executescript(f"BEGIN IMMEDIATE;\n{_BASE_SCHEMA}\n{_V1_SCHEMA}")
    try:
        if version == 2:
            _add_e1rm_qualified_column(conn)
        conn.execute(
            "INSERT INTO settings "
            "(id, week, days_per_week, rounding, incr, t2_reset_pct, t2_fail, "
            "t3_target, bodyweight) "
            "VALUES (1, :week, :days_per_week, :rounding, :incr, :t2_reset_pct, "
            ":t2_fail, :t3_target, :bodyweight)",
            _DEFAULT_SETTINGS,
        )
        conn.executemany(
            "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (row.kind, row.week, row.intensity, row.reps, row.repout)
                for row in DEFAULT_SCHEDULE
            ],
        )
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _create_fresh_v1(conn: sqlite3.Connection) -> None:
    _create_fresh(conn, version=1)


def _create_fresh_v2(conn: sqlite3.Connection) -> None:
    _create_fresh(conn, version=2)


def _insert_legacy_lifts(conn: sqlite3.Connection) -> tuple[dict[int, int], int]:
    slot_ids = {}
    incomplete = 0
    states = {
        row["lift_id"]: row
        for row in conn.execute("SELECT * FROM lift_state ORDER BY lift_id")
    }
    for lift in conn.execute("SELECT * FROM lifts ORDER BY id"):
        if lift["mode"] == "sbs":
            reps = lift["reps"]
            repout = lift["repout"]
            intensity = lift["intensity"]
        else:
            # v0 stored zeroes in SBS-only prescription columns for modes where
            # those fields do not apply. v1 represents "not applicable" as NULL.
            reps = None
            repout = None
            intensity = None
        exercise_id = conn.execute(
            "INSERT INTO exercise (name, load_model) VALUES (?, ?)",
            (lift["name"], lift["load_model"]),
        ).lastrowid
        slot_id = conn.execute(
            "INSERT INTO program_slot "
            "(exercise_id, day, sort_order, mode, lift_kind, sets, reps, repout, "
            "intensity, max_seed, start_weight, increment, bodyweight_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                exercise_id,
                lift["day"],
                lift["sort_order"],
                lift["mode"],
                lift["lift_kind"],
                lift["sets"],
                reps,
                repout,
                intensity,
                lift["max"],
                lift["start"],
                lift["incr"],
                lift["bodyweight_pct"],
            ),
        ).lastrowid
        state = states.get(lift["id"])
        if state is None:
            incomplete += 1
            conn.execute(
                "INSERT INTO strength_state (slot_id, mode) VALUES (?, ?)",
                (slot_id, lift["mode"]),
            )
        else:
            conn.execute(
                "INSERT INTO strength_state "
                "(slot_id, mode, tm, weight, target, streak, est1rm, reseeded_cycle) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slot_id,
                    state["mode"],
                    state["tm"],
                    state["weight"],
                    state["target"],
                    state["streak"],
                    state["est1rm"],
                    state["reseeded_cycle"],
                ),
            )
        slot_ids[lift["id"]] = slot_id
    return slot_ids, incomplete


def _parse_training_date(timestamp: str) -> str | None:
    if not timestamp:
        return None
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp[:10]


def _get_or_create_session(
    conn: sqlite3.Connection,
    *,
    program_week: int,
    day: int,
    training_date: str | None,
    finalized_at: str | None,
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM training_session WHERE program_week = ? AND day = ?",
        (program_week, day),
    ).fetchone()
    if row is None:
        session_id = conn.execute(
            "INSERT INTO training_session "
            "(program_week, day, training_date, bodyweight_kg, finalized_at) "
            "VALUES (?, ?, ?, NULL, ?)",
            (program_week, day, training_date, finalized_at),
        ).lastrowid
        return conn.execute(
            "SELECT * FROM training_session WHERE id = ?", (session_id,)
        ).fetchone()
    if finalized_at is not None:
        current_finalized = row["finalized_at"]
        current_date = row["training_date"]
        conn.execute(
            "UPDATE training_session SET training_date = ?, finalized_at = ? WHERE id = ?",
            (
                min(filter(None, (current_date, training_date))),
                max(filter(None, (current_finalized, finalized_at))),
                row["id"],
            ),
        )
        return conn.execute(
            "SELECT * FROM training_session WHERE id = ?", (row["id"],)
        ).fetchone()
    return row


def _insert_empty_prescription(
    conn: sqlite3.Connection, *, session_id: int, slot_id: int
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO progression_event (session_id, slot_id) VALUES (?, ?)",
        (session_id, slot_id),
    )


def _legacy_planned_reps(
    conn: sqlite3.Connection, *, lift_id: int, program_week: int
) -> int | None:
    lift = conn.execute("SELECT * FROM lifts WHERE id = ?", (lift_id,)).fetchone()
    mode = lift["mode"]
    if mode == "sbs":
        schedule_week = ((program_week - 1) % 21) + 1
        row = conn.execute(
            "SELECT reps FROM sbs_schedule WHERE kind = ? AND week = ?",
            (lift["lift_kind"], schedule_week),
        ).fetchone()
        if row is None:
            raise sqlite3.DatabaseError(
                f"missing legacy schedule row for lift={lift_id} week={program_week}"
            )
        planned_reps = row["reps"]
        if planned_reps <= 0:
            raise sqlite3.DatabaseError(
                "legacy planned reps must be positive "
                f"for lift={lift_id} week={program_week}"
            )
        return planned_reps
    if mode == "linear_t3":
        planned_reps = conn.execute(
            "SELECT t3_target FROM settings WHERE id = 1"
        ).fetchone()["t3_target"]
        if planned_reps <= 0:
            raise sqlite3.DatabaseError(
                "legacy planned reps must be positive "
                f"for lift={lift_id} week={program_week}"
            )
        return planned_reps
    if mode == "linear_t2":
        target = 8
        streak = 0
        fail = conn.execute(
            "SELECT t2_fail FROM settings WHERE id = 1"
        ).fetchone()["t2_fail"]
        for history in conn.execute(
            "SELECT reps FROM history "
            "WHERE lift_id = ? AND week < ? AND reps >= 0 ORDER BY week, id",
            (lift_id, program_week),
        ):
            actual = history["reps"]
            if lift["bodyweight_pct"] > 0:
                target = max(4, min(10, actual))
                streak = 0
            elif actual >= target:
                streak = 0
            else:
                streak += 1
                if streak >= fail:
                    target = 8
                    streak = 0
                else:
                    target = {8: 6, 6: 4, 4: 4}.get(target, 6)
        return target
    prior = conn.execute(
        "SELECT reps FROM history "
        "WHERE lift_id = ? AND week < ? AND reps >= 0 ORDER BY week DESC, id DESC "
        "LIMIT 1",
        (lift_id, program_week),
    ).fetchone()
    return prior["reps"] if prior is not None else None


def _insert_legacy_sets(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    slot_id: int,
    sets: int,
    planned_reps: int | None,
    last_set_reps: int,
    actual_added_weight,
) -> None:
    """Backfill prior sets from the applicable v0 prescription.

    The owner-confirmed rule treats the stored legacy result as the final set,
    fills earlier sets with the reps prescribed for that historical week, and
    keeps only the final set as the progression driver. If the record-only
    mode has no prior reps to act as its plan, only the stored final set is
    materialized.
    """
    conn.executemany(
        "INSERT INTO set_log "
        "(session_id, slot_id, set_number, actual_added_weight, reps, "
        "warmup, drives_progression) VALUES (?, ?, ?, ?, ?, 0, ?)",
        [
            (
                session_id,
                slot_id,
                set_number,
                actual_added_weight,
                last_set_reps if set_number == sets else planned_reps,
                int(set_number == sets),
            )
            for set_number in (
                range(1, sets + 1) if planned_reps is not None else (sets,)
            )
        ],
    )


def _insert_legacy_history(
    conn: sqlite3.Connection, slot_ids: dict[int, int]
) -> tuple[int, int]:
    migrated = 0
    incomplete = 0
    slot_days = {
        row["id"]: row["day"]
        for row in conn.execute("SELECT id, day FROM program_slot")
    }
    slot_sets = {
        row["id"]: row["sets"]
        for row in conn.execute("SELECT id, sets FROM program_slot")
    }
    for history in conn.execute("SELECT * FROM history ORDER BY id"):
        slot_id = slot_ids.get(history["lift_id"])
        training_date = _parse_training_date(history["ts"])
        actual_added_weight = history["weight"]
        valid = (
            slot_id is not None
            and history["week"] > 0
            and history["reps"] >= 0
            and actual_added_weight is not None
            and math.isfinite(actual_added_weight)
            and training_date is not None
        )
        if not valid:
            incomplete += 1
            continue
        session = _get_or_create_session(
            conn,
            program_week=history["week"],
            day=slot_days[slot_id],
            training_date=training_date,
            finalized_at=history["ts"],
        )
        _insert_empty_prescription(
            conn, session_id=session["id"], slot_id=slot_id
        )
        _insert_legacy_sets(
            conn,
            session_id=session["id"],
            slot_id=slot_id,
            sets=slot_sets[slot_id],
            planned_reps=_legacy_planned_reps(
                conn,
                lift_id=history["lift_id"],
                program_week=history["week"],
            ),
            last_set_reps=history["reps"],
            actual_added_weight=actual_added_weight,
        )
        migrated += 1
        # v0 has no session bodyweight or historical prescription percentage.
        incomplete += 1
    return migrated, incomplete


def _insert_legacy_week_logs(
    conn: sqlite3.Connection, slot_ids: dict[int, int]
) -> tuple[int, int]:
    migrated = 0
    incomplete = 0
    slot_days = {
        row["id"]: row["day"]
        for row in conn.execute("SELECT id, day FROM program_slot")
    }
    slot_sets = {
        row["id"]: row["sets"]
        for row in conn.execute("SELECT id, sets FROM program_slot")
    }
    for week_log in conn.execute("SELECT * FROM week_log ORDER BY week, lift_id"):
        slot_id = slot_ids.get(week_log["lift_id"])
        if slot_id is None or week_log["week"] <= 0 or week_log["reps"] < 0:
            incomplete += 1
            continue
        session = _get_or_create_session(
            conn,
            program_week=week_log["week"],
            day=slot_days[slot_id],
            training_date=None,
            finalized_at=None,
        )
        if session["finalized_at"] is not None:
            incomplete += 1
            continue
        _insert_empty_prescription(
            conn, session_id=session["id"], slot_id=slot_id
        )
        _insert_legacy_sets(
            conn,
            session_id=session["id"],
            slot_id=slot_id,
            sets=slot_sets[slot_id],
            planned_reps=_legacy_planned_reps(
                conn,
                lift_id=week_log["lift_id"],
                program_week=week_log["week"],
            ),
            last_set_reps=week_log["reps"],
            actual_added_weight=None,
        )
        migrated += 1
        # week_log proves reps only; actual weight and prescription are unknown.
        incomplete += 1
    return migrated, incomplete


def _rename_legacy_tables(conn: sqlite3.Connection) -> None:
    for old, new in (
        ("lifts", "legacy_lifts"),
        ("lift_state", "legacy_lift_state"),
        ("history", "legacy_history"),
        ("week_log", "legacy_week_log"),
    ):
        conn.execute(f"ALTER TABLE {old} RENAME TO {new}")


def _migrate_production_v0(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
    conn.executescript(f"BEGIN IMMEDIATE;\n{_V1_SCHEMA}")
    try:
        slot_ids, incomplete_states = _insert_legacy_lifts(conn)
        migrated_history, incomplete_history = _insert_legacy_history(conn, slot_ids)
        migrated_week_logs, incomplete_week_logs = _insert_legacy_week_logs(
            conn, slot_ids
        )
        _rename_legacy_tables(conn)
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise sqlite3.IntegrityError(
                f"foreign key check failed: {foreign_key_errors!r}"
            )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return (
        len(slot_ids),
        migrated_history,
        migrated_week_logs,
        incomplete_states + incomplete_history + incomplete_week_logs,
    )


def migrate_v0_to_v1(
    conn: sqlite3.Connection, *, db_path: str, backup_dir: str
) -> None:
    """Bring an empty database or the single production v0 schema to v1."""
    if conn.execute("PRAGMA user_version").fetchone()[0] == 1:
        return
    tables = _table_names(conn)
    if not tables:
        _create_fresh_v1(conn)
        logger.info("initialized fresh database at schema v1")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    snapshot(
        db_path,
        dest_dir=backup_dir,
        week=_snapshot_week(conn),
        ts=timestamp,
    )

    expected_v0 = {"settings", "lifts", "lift_state", "history", "week_log", "sbs_schedule"}
    if not expected_v0 <= tables:
        missing = sorted(expected_v0 - tables)
        raise sqlite3.DatabaseError(f"unrecognized v0 schema; missing tables: {missing}")
    if conn.execute("SELECT 1 FROM settings WHERE id = 1").fetchone() is None:
        raise sqlite3.DatabaseError("unrecognized v0 schema; missing settings row")
    lifts, history, week_logs, incomplete = _migrate_production_v0(conn)
    logger.info(
        "migrated v0 to v1: lifts=%d history=%d week_logs=%d incomplete=%d",
        lifts,
        history,
        week_logs,
        incomplete,
    )


def _upgrade_v1_to_v2(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        _add_e1rm_qualified_column(conn)
        conn.execute(
            "UPDATE strength_state SET est1rm = NULL WHERE mode = 'sbs'"
        )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def migrate_to_v2(
    conn: sqlite3.Connection, *, db_path: str, backup_dir: str
) -> None:
    """Bring an empty, v0, or v1 database to the concrete v2 schema."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 2:
        return
    if not _table_names(conn):
        _create_fresh_v2(conn)
        logger.info("initialized fresh database at schema v2")
        return
    if version == 0:
        migrate_v0_to_v1(conn, db_path=db_path, backup_dir=backup_dir)
    elif version == 1:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        snapshot(
            db_path,
            dest_dir=backup_dir,
            week=_snapshot_week(conn),
            ts=timestamp,
        )
    else:
        raise sqlite3.DatabaseError(f"unsupported schema version: {version}")

    _upgrade_v1_to_v2(conn)
    logger.info("migrated v1 to v2")
