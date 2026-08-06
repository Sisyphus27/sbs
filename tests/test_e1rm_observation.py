import sqlite3

import pytest

from tests.v1_helpers import insert_v1_slot
from webapp.app import create_app
from webapp.db import connect
from webapp.migration import migrate_v0_to_v1


def test_sbs_qualified_observations_survive_v2_upgrade_and_keep_historical_peak(
    tmp_path,
):
    db_path = tmp_path / "e1rm-observation.db"
    backup_dir = tmp_path / "backups"

    conn = connect(str(db_path))
    migrate_v0_to_v1(
        conn,
        db_path=str(db_path),
        backup_dir=str(backup_dir),
    )
    slot_id = insert_v1_slot(
        conn,
        name="Squat",
        mode="sbs",
        day=1,
        sort_order=0,
        sets=3,
        lift_kind="main",
        reps=5,
        repout=10,
        tm=100.0,
        est1rm=200.0,
    )
    observation_only_slot_id = insert_v1_slot(
        conn,
        name="Bench Press",
        mode="sbs",
        day=2,
        sort_order=0,
        sets=3,
        lift_kind="main",
        reps=5,
        repout=10,
        tm=80.0,
    )
    conn.execute(
        "UPDATE sbs_schedule SET intensity = .7, reps = 5, repout = 10 "
        "WHERE kind = 'main' AND week IN (1, 2)"
    )
    old_session_id = conn.execute(
        "INSERT INTO training_session "
        "(program_week, day, training_date, finalized_at) "
        "VALUES (21, 1, '2026-07-01', '2026-07-01T12:00:00+00:00')"
    ).lastrowid
    conn.execute(
        "INSERT INTO progression_event (session_id, slot_id) VALUES (?, ?)",
        (old_session_id, slot_id),
    )
    conn.execute(
        "INSERT INTO set_log "
        "(session_id, slot_id, set_number, actual_added_weight, reps, "
        "warmup, drives_progression) VALUES (?, ?, 1, 200, 1, 0, 1)",
        (old_session_id, slot_id),
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()

    app = create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config={"TESTING": True},
    )

    with sqlite3.connect(db_path) as upgraded:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 2
        old_set = upgraded.execute(
            "SELECT e1rm_qualified FROM set_log WHERE session_id = ?",
            (old_session_id,),
        ).fetchone()
        assert old_set == (0,)
        assert upgraded.execute(
            "SELECT est1rm FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == (None,)
    assert len(list(backup_dir.glob("sbs-w1-*.db.bak"))) == 1

    with app.test_client() as client:
        driver_only = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "70",
                "reps": "12",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "0",
            },
        )
        observation_only = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "150",
                "reps": "1",
                "warmup": "0",
                "drives_progression": "0",
                "e1rm_qualified": "1",
            },
        )
        ordinary = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "2",
                "actual_added_weight": "300",
                "reps": "1",
                "warmup": "0",
                "drives_progression": "0",
                "e1rm_qualified": "0",
            },
        )
        observation_without_driver = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(observation_only_slot_id),
                "set_number": "1",
                "actual_added_weight": "120",
                "reps": "1",
                "warmup": "0",
                "drives_progression": "0",
                "e1rm_qualified": "1",
            },
        )

    assert [
        driver_only.status_code,
        observation_only.status_code,
        ordinary.status_code,
        observation_without_driver.status_code,
    ] == [
        200,
        200,
        200,
        200,
    ]

    restarted = create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config={"TESTING": True},
    )
    with restarted.test_client() as client:
        current_rows = {
            row["set_number"]: row
            for row in client.get("/training/history").get_json()
            if row["program_week"] == 1 and row["slot_id"] == slot_id
        }
        finalized = client.post("/training/finalize", data={"expected_week": "1"})
        plan = client.get("/training/plan").get_json()

    assert current_rows[3]["drives_progression"] == 1
    assert current_rows[3]["e1rm_qualified"] == 0
    assert current_rows[3]["canonical_e1rm"] is None
    assert current_rows[1]["drives_progression"] == 0
    assert current_rows[1]["e1rm_qualified"] == 1
    assert current_rows[1]["canonical_e1rm"] == pytest.approx(150.0)
    assert current_rows[2]["canonical_e1rm"] is None
    assert finalized.status_code == 200
    assert plan["slots"][0]["historical_peak_e1rm"] == pytest.approx(150.0)
    assert plan["slots"][1]["historical_peak_e1rm"] == pytest.approx(120.0)

    with sqlite3.connect(db_path) as after_first_week:
        assert after_first_week.execute(
            "SELECT tm, est1rm FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == pytest.approx((101.0, 150.0))
        assert after_first_week.execute(
            "SELECT tm, est1rm FROM strength_state WHERE slot_id = ?",
            (observation_only_slot_id,),
        ).fetchone() == pytest.approx((80.0, 120.0))

    with restarted.test_client() as client:
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "2",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "72.5",
                "reps": "10",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "0",
            },
        ).status_code == 200
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "2",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "140",
                "reps": "1",
                "warmup": "0",
                "drives_progression": "0",
                "e1rm_qualified": "1",
            },
        ).status_code == 200
        finalized = client.post("/training/finalize", data={"expected_week": "2"})

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as after_second_week:
        assert after_second_week.execute(
            "SELECT tm, est1rm FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == pytest.approx((101.0, 150.0))
