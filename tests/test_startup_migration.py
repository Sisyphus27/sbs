import logging
import sqlite3

import pytest

from webapp.app import create_app
from webapp import db


TRAINING_TABLES = {
    "exercise",
    "program_slot",
    "strength_state",
    "training_session",
    "set_log",
    "progression_event",
}


def test_fresh_database_starts_at_v1_with_six_training_tables(tmp_path):
    db_path = tmp_path / "fresh.db"

    create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        settings_count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        schedule_count = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
        exercise_id = conn.execute(
            "INSERT INTO exercise (name, load_model) VALUES ('Squat', 'barbell')"
        ).lastrowid
        slot_id = conn.execute(
            "INSERT INTO program_slot "
            "(exercise_id, day, sort_order, mode, sets, bodyweight_pct) "
            "VALUES (?, 1, 0, 'sbs', 5, 0)",
            (exercise_id,),
        ).lastrowid
        conn.execute(
            "INSERT INTO strength_state (slot_id, mode) VALUES (?, 'sbs')",
            (slot_id,),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO strength_state (slot_id, mode) VALUES (?, 'sbs')",
                (slot_id,),
            )
        conn.rollback()

        conn.execute(
            "INSERT INTO program_slot "
            "(exercise_id, day, sort_order, mode, sets, bodyweight_pct) "
            "VALUES (?, 2, 0, 'sbs', 5, 0)",
            (exercise_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.commit()
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO strength_state (slot_id, mode) VALUES (999, 'sbs')"
            )
            conn.commit()
        conn.rollback()

    assert user_version == 1
    assert TRAINING_TABLES <= tables
    assert {"settings", "sbs_schedule"} <= tables
    assert {"lifts", "lift_state", "history", "week_log"}.isdisjoint(tables)
    assert settings_count == 1
    assert schedule_count == 42


def test_production_v0_is_snapshotted_and_migrated_without_inventing_facts(
    tmp_path, caplog
):
    db_path = tmp_path / "production-v0.db"
    backup_dir = tmp_path / "backups"
    conn = db.connect(str(db_path))
    db.init_schema(conn)
    conn.execute("UPDATE settings SET week = 3, bodyweight = 82 WHERE id = 1")
    squat_id = conn.execute(
        "INSERT INTO lifts "
        "(name, load_model, mode, day, sort_order, sets, max, intensity, reps, "
        "repout, lift_kind, incr, bodyweight_pct) "
        "VALUES ('Squat', 'barbell', 'sbs', 1, 0, 5, 140, .7, 5, 10, "
        "'main', 2.5, 0)"
    ).lastrowid
    pullup_id = conn.execute(
        "INSERT INTO lifts "
        "(name, load_model, mode, day, sort_order, sets, start, incr, bodyweight_pct) "
        "VALUES ('Pull-up', 'bodyweight', 'linear_t2', 1, 1, 3, 10, 1, 1)"
    ).lastrowid
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, tm, streak, reseeded_cycle) "
        "VALUES (?, 'sbs', 145, 0, 1)",
        (squat_id,),
    )
    conn.execute(
        "INSERT INTO lift_state "
        "(lift_id, mode, weight, target, streak, est1rm, reseeded_cycle) "
        "VALUES (?, 'linear_t2', 10, 8, 1, 110, 0)",
        (pullup_id,),
    )
    conn.execute(
        "INSERT INTO history (lift_id, week, weight, reps, ts) "
        "VALUES (?, 2, 10, 7, '2026-07-08T09:30:00+00:00')",
        (pullup_id,),
    )
    conn.execute(
        "INSERT INTO week_log (lift_id, week, reps) VALUES (?, 3, 12)",
        (squat_id,),
    )
    conn.commit()
    conn.close()

    with caplog.at_level(logging.INFO, logger="webapp.migration"):
        create_app(
            db_path=str(db_path),
            backup_dir=str(backup_dir),
            test_config={"TESTING": True},
        )

    assert "migrated v0 to v1: lifts=2 history=1 week_logs=1 incomplete=2" in caplog.messages

    snapshots = list(backup_dir.glob("sbs-w3-*.db.bak"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as snapshot_conn:
        assert snapshot_conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert snapshot_conn.execute("SELECT COUNT(*) FROM lifts").fetchone()[0] == 2

    with sqlite3.connect(db_path) as migrated:
        migrated.row_factory = sqlite3.Row
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {
            row[0]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"legacy_lifts", "legacy_lift_state", "legacy_history", "legacy_week_log"} <= tables
        assert {"lifts", "lift_state", "history", "week_log"}.isdisjoint(tables)
        assert migrated.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 3
        assert migrated.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 42
        assert migrated.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 2
        assert migrated.execute("SELECT COUNT(*) FROM program_slot").fetchone()[0] == 2
        assert migrated.execute("SELECT COUNT(*) FROM strength_state").fetchone()[0] == 2

        completed = migrated.execute(
            "SELECT ts.program_week, ts.day, ts.training_date, ts.bodyweight_kg, "
            "ts.finalized_at, sl.actual_added_weight, sl.reps, "
            "sl.drives_progression, pe.mode, pe.bodyweight_pct, "
            "pe.planned_working_weight "
            "FROM training_session AS ts "
            "JOIN set_log AS sl ON sl.session_id = ts.id "
            "JOIN progression_event AS pe "
            "ON pe.session_id = ts.id AND pe.slot_id = sl.slot_id "
            "WHERE ts.program_week = 2"
        ).fetchone()
        assert dict(completed) == {
            "program_week": 2,
            "day": 1,
            "training_date": "2026-07-08",
            "bodyweight_kg": None,
            "finalized_at": "2026-07-08T09:30:00+00:00",
            "actual_added_weight": 10.0,
            "reps": 7,
            "drives_progression": 1,
            "mode": None,
            "bodyweight_pct": None,
            "planned_working_weight": None,
        }

        draft = migrated.execute(
            "SELECT ts.program_week, ts.day, ts.training_date, ts.finalized_at, "
            "sl.actual_added_weight, sl.reps, sl.drives_progression "
            "FROM training_session AS ts "
            "JOIN set_log AS sl ON sl.session_id = ts.id "
            "WHERE ts.program_week = 3"
        ).fetchone()
        assert dict(draft) == {
            "program_week": 3,
            "day": 1,
            "training_date": None,
            "finalized_at": None,
            "actual_added_weight": None,
            "reps": 12,
            "drives_progression": 1,
        }


def test_v1_startup_is_a_no_op(tmp_path):
    db_path = tmp_path / "already-v1.db"
    backup_dir = tmp_path / "backups"
    config = {"TESTING": True}
    create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config=config,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO exercise (name, load_model) VALUES ('User row', 'barbell')"
        )
        conn.commit()
        schema_before = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index') ORDER BY type, name"
        ).fetchall()

    create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config=config,
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM exercise").fetchall() == [("User row",)]
        assert conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index') ORDER BY type, name"
        ).fetchall() == schema_before
    assert not backup_dir.exists()


def test_structural_migration_failure_rolls_back_and_keeps_snapshot(tmp_path):
    db_path = tmp_path / "invalid-v0.db"
    backup_dir = tmp_path / "backups"
    conn = db.connect(str(db_path))
    db.init_schema(conn)
    conn.execute("UPDATE settings SET week = 4 WHERE id = 1")
    conn.execute(
        "INSERT INTO lifts "
        "(name, load_model, mode, day, sort_order, sets, max, bodyweight_pct) "
        "VALUES ('Invalid day', 'barbell', 'sbs', 0, 0, 5, 100, 0)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="day > 0"):
        create_app(
            db_path=str(db_path),
            backup_dir=str(backup_dir),
            test_config={"TESTING": True},
        )

    snapshots = list(backup_dir.glob("sbs-w4-*.db.bak"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as snapshot_conn:
        assert snapshot_conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert snapshot_conn.execute("SELECT name FROM lifts").fetchall() == [
            ("Invalid day",)
        ]

    with sqlite3.connect(db_path) as original:
        assert original.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            row[0]
            for row in original.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"lifts", "lift_state", "history", "week_log"} <= tables
        assert TRAINING_TABLES.isdisjoint(tables)
        assert original.execute("SELECT name FROM lifts").fetchall() == [
            ("Invalid day",)
        ]


def test_missing_v0_table_failure_keeps_snapshot(tmp_path):
    db_path = tmp_path / "missing-table-v0.db"
    backup_dir = tmp_path / "backups"
    conn = db.connect(str(db_path))
    db.init_schema(conn)
    conn.execute("UPDATE settings SET week = 4 WHERE id = 1")
    conn.execute("DROP TABLE week_log")
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.DatabaseError, match="missing tables"):
        create_app(
            db_path=str(db_path),
            backup_dir=str(backup_dir),
            test_config={"TESTING": True},
        )

    snapshots = list(backup_dir.glob("sbs-w4-*.db.bak"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as snapshot_conn:
        assert snapshot_conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert snapshot_conn.execute("PRAGMA user_version").fetchone()[0] == 0
    with sqlite3.connect(db_path) as original:
        assert original.execute("PRAGMA user_version").fetchone()[0] == 0
        assert original.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'exercise'"
        ).fetchone()[0] == 0


def test_foreign_key_migration_failure_rolls_back_and_keeps_snapshot(tmp_path):
    db_path = tmp_path / "orphan-v0.db"
    backup_dir = tmp_path / "backups"
    conn = db.connect(str(db_path))
    db.init_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, streak, reseeded_cycle) "
        "VALUES (999, 'sbs', 0, 0)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="foreign key check failed"):
        create_app(
            db_path=str(db_path),
            backup_dir=str(backup_dir),
            test_config={"TESTING": True},
        )

    snapshots = list(backup_dir.glob("sbs-w1-*.db.bak"))
    assert len(snapshots) == 1
    with sqlite3.connect(db_path) as original:
        assert original.execute("PRAGMA user_version").fetchone()[0] == 0
        assert original.execute(
            "SELECT lift_id FROM lift_state WHERE lift_id = 999"
        ).fetchone() == (999,)
        assert original.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'exercise'"
        ).fetchone()[0] == 0


def test_transaction_migration_failure_rolls_back_and_keeps_snapshot(tmp_path):
    db_path = tmp_path / "locked-v0.db"
    backup_dir = tmp_path / "backups"
    conn = db.connect(str(db_path))
    db.init_schema(conn)
    conn.close()

    locker = sqlite3.connect(db_path)
    locker.execute("PRAGMA journal_mode = WAL")
    locker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            create_app(
                db_path=str(db_path),
                backup_dir=str(backup_dir),
                test_config={"TESTING": True},
            )
    finally:
        locker.rollback()
        locker.close()

    snapshots = list(backup_dir.glob("sbs-w1-*.db.bak"))
    assert len(snapshots) == 1
    with sqlite3.connect(db_path) as original:
        assert original.execute("PRAGMA user_version").fetchone()[0] == 0
        assert original.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'exercise'"
        ).fetchone()[0] == 0
