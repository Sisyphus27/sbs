import sqlite3

import pytest

from webapp.app import create_app
from sbs_cli.engine.onerm import estimate_1rm
from webapp import training_cli


def _app_with_slot(tmp_path, *, load_model="barbell", mode="linear_t3",
                   bodyweight_pct=0.0, weight=30.0):
    db_path = tmp_path / "training.db"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        exercise_id = conn.execute(
            "INSERT INTO exercise (name, load_model) VALUES (?, ?)",
            ("Curl", load_model),
        ).lastrowid
        slot_id = conn.execute(
            "INSERT INTO program_slot "
            "(exercise_id, day, sort_order, mode, sets, start_weight, "
            "bodyweight_pct) VALUES (?, 1, 0, ?, 3, ?, ?)",
            (exercise_id, mode, weight, bodyweight_pct),
        ).lastrowid
        conn.execute(
            "INSERT INTO strength_state (slot_id, mode, weight) VALUES (?, ?, ?)",
            (slot_id, mode, weight),
        )
        conn.commit()
    return app, db_path, slot_id


def test_quick_and_full_logging_update_one_stable_set_truth(tmp_path):
    app, db_path, slot_id = _app_with_slot(tmp_path)

    with app.test_client() as client:
        plan = client.get("/training/plan")
    assert plan.status_code == 200
    assert plan.get_json() == {
        "expected_week": 1,
        "slots": [
            {
                "day": 1,
                "load_model": "barbell",
                "name": "Curl",
                "planned_added_weight": 30.0,
                "planned_reps": 15,
                "planned_sets": 3,
                "planned_working_weight": 30.0,
                "slot_id": slot_id,
            }
        ],
    }
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 0

    with app.test_client() as client:
        quick = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "15",
            },
        )
        full = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "32.5",
                "reps": "16",
                "warmup": "0",
                "drives_progression": "1",
            },
        )

    assert quick.status_code == 200
    assert full.status_code == 200
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 1
        row = conn.execute(
            "SELECT sl.set_number, sl.actual_added_weight, sl.reps, "
            "sl.warmup, sl.drives_progression, pe.planned_added_weight, "
            "pe.planned_working_weight, pe.state_tm, pe.state_weight, "
            "pe.state_target, pe.state_streak, pe.state_est1rm, pe.rounding, "
            "pe.increment, pe.t2_reset_pct, pe.t2_fail, pe.t3_target "
            "FROM set_log AS sl "
            "JOIN progression_event AS pe "
            "ON pe.session_id = sl.session_id AND pe.slot_id = sl.slot_id"
        ).fetchone()
        assert dict(row) == {
            "set_number": 3,
            "actual_added_weight": 32.5,
            "reps": 16,
            "warmup": 0,
            "drives_progression": 1,
            "planned_added_weight": 30.0,
            "planned_working_weight": 30.0,
            "state_tm": None,
            "state_weight": 30.0,
            "state_target": None,
            "state_streak": None,
            "state_est1rm": None,
            "rounding": None,
            "increment": 2.5,
            "t2_reset_pct": None,
            "t2_fail": None,
            "t3_target": 15,
        }


def test_bodyweight_history_uses_saved_session_and_snapshot_after_restart(tmp_path):
    app, db_path, slot_id = _app_with_slot(
        tmp_path,
        load_model="bodyweight",
        mode="linear_t3",
        bodyweight_pct=1.0,
        weight=10.0,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET bodyweight = 75 WHERE id = 1")
        conn.commit()

    with app.test_client() as client:
        assert client.get("/training/history").get_json() == []
        warmup = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "5",
                "reps": "5",
                "warmup": "1",
                "drives_progression": "0",
                "training_date": "2026-08-05",
                "bodyweight_kg": "80",
            },
        )
        work = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "8",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "1",
            },
        )
    assert warmup.status_code == 200
    assert work.status_code == 200

    restarted = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET bodyweight = 100 WHERE id = 1")
        conn.execute(
            "UPDATE program_slot SET bodyweight_pct = .5 WHERE id = ?", (slot_id,)
        )
        conn.commit()

    with restarted.test_client() as client:
        rows = client.get("/training/history").get_json()

    assert len(rows) == 2
    assert [row["actual_working_weight"] for row in rows] == [85.0, 90.0]
    assert rows[0]["canonical_e1rm"] is None
    assert rows[1]["canonical_e1rm"] == estimate_1rm(90.0, 8)
    assert rows[1]["planned_working_weight"] == 85.0
    assert rows[1]["recorded_volume"] == 720.0
    assert rows[1]["training_date"] == "2026-08-05"
    assert rows[1]["bodyweight_kg"] == 80.0

    with restarted.test_client() as client:
        edited = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "8",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "1",
                "training_date": "2026-08-06",
                "bodyweight_kg": "82",
            },
        )
        edited_rows = client.get("/training/history").get_json()
    assert edited.status_code == 200
    assert edited_rows[1]["actual_working_weight"] == 92.0
    assert edited_rows[1]["planned_working_weight"] == 85.0
    assert edited_rows[1]["training_date"] == "2026-08-06"


def test_invalid_and_stale_saves_leave_no_training_facts(tmp_path):
    app, db_path, slot_id = _app_with_slot(tmp_path, bodyweight_pct=0.5)

    with app.test_client() as client:
        illegal_combo = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "10",
            },
        )
        negative = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "-1",
                "reps": "10",
            },
        )
        non_finite = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "nan",
                "reps": "10",
            },
        )
    assert illegal_combo.status_code == 400
    assert negative.status_code == 400
    assert non_finite.status_code == 400

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE program_slot SET bodyweight_pct = 0 WHERE id = ?", (slot_id,))
        conn.execute("UPDATE settings SET week = 2 WHERE id = 1")
        conn.commit()

    with app.test_client() as client:
        stale = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "10",
            },
        )
    assert stale.status_code == 409
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 0


def test_cli_uses_same_command_and_moves_the_progression_driver(tmp_path):
    app, db_path, slot_id = _app_with_slot(tmp_path)
    with app.test_client() as client:
        response = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "15",
                "training_date": "2026-08-05",
                "bodyweight_kg": "80",
            },
        )
    assert response.status_code == 200

    training_cli.run(
        [
            "save-set",
            "--db",
            str(db_path),
            "--expected-week",
            "1",
            "--slot-id",
            str(slot_id),
            "--set-number",
            "2",
            "--actual-added-weight",
            "31",
            "--reps",
            "10",
            "--drives-progression",
            "--clear-training-date",
            "--clear-bodyweight",
        ]
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT set_number, actual_added_weight, drives_progression "
            "FROM set_log ORDER BY set_number"
        ).fetchall()
        session = conn.execute(
            "SELECT training_date, bodyweight_kg FROM training_session"
        ).fetchone()
    assert rows == [(2, 31.0, 1), (3, 30.0, 0)]
    assert session == (None, None)


def test_warmup_cannot_displace_the_progression_driver(tmp_path):
    app, db_path, slot_id = _app_with_slot(tmp_path)
    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "10",
            },
        ).status_code == 200
        warmup_driver = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "10",
                "reps": "5",
                "warmup": "1",
                "drives_progression": "1",
            },
        )

    assert warmup_driver.status_code == 400
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT set_number, warmup, drives_progression "
            "FROM set_log ORDER BY set_number"
        ).fetchall()
    assert rows == [(3, 0, 1)]


def test_confirming_a_migrated_draft_completes_its_snapshot_once(tmp_path):
    app, db_path, slot_id = _app_with_slot(
        tmp_path,
        load_model="bodyweight",
        mode="linear_t3",
        bodyweight_pct=1.0,
        weight=10.0,
    )
    with sqlite3.connect(db_path) as conn:
        session_id = conn.execute(
            "INSERT INTO training_session (program_week, day) VALUES (1, 1)"
        ).lastrowid
        conn.execute(
            "INSERT INTO progression_event (session_id, slot_id) VALUES (?, ?)",
            (session_id, slot_id),
        )
        conn.execute(
            "INSERT INTO set_log "
            "(session_id, slot_id, set_number, actual_added_weight, reps, "
            "drives_progression) VALUES (?, ?, 3, NULL, 12, 1)",
            (session_id, slot_id),
        )
        conn.commit()

    with app.test_client() as client:
        before = client.get("/training/history").get_json()
        confirmed = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "8",
                "warmup": "0",
                "drives_progression": "1",
                "bodyweight_kg": "80",
            },
        )
        after = client.get("/training/history").get_json()

    assert before[0]["actual_working_weight"] is None
    assert confirmed.status_code == 200
    assert after[0]["actual_working_weight"] == 90.0
    assert after[0]["planned_working_weight"] == 10.0

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET bodyweight = 100 WHERE id = 1")
        conn.execute(
            "UPDATE program_slot SET bodyweight_pct = .5 WHERE id = ?", (slot_id,)
        )
        conn.commit()
    with app.test_client() as client:
        stable = client.get("/training/history").get_json()
    assert stable[0]["actual_working_weight"] == 90.0
    assert stable[0]["planned_working_weight"] == 10.0


def test_missing_bodyweight_only_makes_dependent_projection_unavailable(tmp_path):
    app, db_path, bodyweight_slot_id = _app_with_slot(
        tmp_path,
        load_model="bodyweight",
        mode="linear_t3",
        bodyweight_pct=1.0,
        weight=10.0,
    )
    with sqlite3.connect(db_path) as conn:
        exercise_id = conn.execute(
            "INSERT INTO exercise (name, load_model) VALUES ('Press', 'barbell')"
        ).lastrowid
        barbell_slot_id = conn.execute(
            "INSERT INTO program_slot "
            "(exercise_id, day, sort_order, mode, sets, start_weight, "
            "bodyweight_pct) VALUES (?, 1, 1, 'linear_t3', 3, 20, 0)",
            (exercise_id,),
        ).lastrowid
        conn.execute(
            "INSERT INTO strength_state (slot_id, mode, weight) "
            "VALUES (?, 'linear_t3', 20)",
            (barbell_slot_id,),
        )
        conn.commit()

    with app.test_client() as client:
        bodyweight = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(bodyweight_slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "8",
            },
        )
        barbell = client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(barbell_slot_id),
                "set_number": "3",
                "actual_added_weight": "20",
                "reps": "10",
            },
        )
        rows = client.get("/training/history").get_json()

    assert bodyweight.status_code == 200
    assert barbell.status_code == 200
    by_slot = {row["slot_id"]: row for row in rows}
    assert by_slot[bodyweight_slot_id]["actual_working_weight"] is None
    assert by_slot[bodyweight_slot_id]["canonical_e1rm"] is None
    assert by_slot[bodyweight_slot_id]["recorded_volume"] is None
    assert by_slot[barbell_slot_id]["actual_working_weight"] == 20.0
    assert by_slot[barbell_slot_id]["recorded_volume"] == 200.0


def test_mid_save_failure_rolls_back_session_snapshot_and_set(tmp_path):
    app, db_path, slot_id = _app_with_slot(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TRIGGER fail_set_save BEFORE INSERT ON set_log BEGIN "
            "SELECT RAISE(ABORT, 'simulated set failure'); END"
        )
        conn.commit()

    with app.test_client() as client:
        with pytest.raises(sqlite3.IntegrityError, match="simulated set failure"):
            client.post(
                "/training/sets/quick",
                data={
                    "expected_week": "1",
                    "slot_id": str(slot_id),
                    "set_number": "3",
                    "actual_added_weight": "30",
                    "reps": "10",
                },
            )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 0
