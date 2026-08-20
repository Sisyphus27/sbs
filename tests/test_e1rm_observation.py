import sqlite3

import pytest

from tests.v1_helpers import insert_v1_slot
from webapp.app import create_app
from webapp.db import connect
from webapp.migration import migrate_v0_to_v1


def test_sbs_work_sets_automatically_keep_the_historical_peak(
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
        supplementary = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "150",
                "reps": "10",
                "warmup": "0",
                "drives_progression": "0",
                "e1rm_qualified": "0",
            },
        )
        warmup = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "2",
                "actual_added_weight": "300",
                "reps": "1",
                "warmup": "1",
                "drives_progression": "0",
                "e1rm_qualified": "1",
            },
        )
        observation_slot_driver = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(observation_only_slot_id),
                "set_number": "3",
                "actual_added_weight": "56",
                "reps": "10",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "0",
            },
        )

    assert [
        driver_only.status_code,
        supplementary.status_code,
        warmup.status_code,
        observation_slot_driver.status_code,
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
    assert current_rows[1]["e1rm_qualified"] == 0
    assert current_rows[1]["canonical_e1rm"] == pytest.approx(93.6631187679488)
    assert current_rows[2]["warmup"] == 1
    assert current_rows[2]["canonical_e1rm"] is None
    assert finalized.status_code == 200
    assert plan["slots"][0]["historical_peak_e1rm"] == pytest.approx(
        93.6631187679488
    )
    assert plan["slots"][1]["historical_peak_e1rm"] == pytest.approx(
        74.93049501435905
    )

    with sqlite3.connect(db_path) as after_first_week:
        assert after_first_week.execute(
            "SELECT tm, est1rm FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == pytest.approx((101.0, 93.6631187679488))
        assert after_first_week.execute(
            "SELECT tm, est1rm FROM strength_state WHERE slot_id = ?",
            (observation_only_slot_id,),
        ).fetchone() == pytest.approx((80.0, 74.93049501435905))

    with restarted.test_client() as client:
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "2",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "72.5",
                "reps": "1",
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
                "e1rm_qualified": "0",
            },
        ).status_code == 200
        finalized = client.post(
            "/training/finalize",
            data={
                "expected_week": "2",
                "skipped_slot_ids": str(observation_only_slot_id),
            },
        )

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as after_second_week:
        assert after_second_week.execute(
            "SELECT est1rm FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == pytest.approx((93.6631187679488,))


def test_loadable_t2_keeps_one_peak_through_the_complete_reset_cycle(tmp_path):
    db_path = tmp_path / "t2-reset-cycle.db"
    backup_dir = tmp_path / "backups"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        slot_id = insert_v1_slot(
            conn,
            name="Row",
            mode="linear_t3",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=105.0,
            increment=7.0,
            weight=105.0,
            est1rm=250.0,
        )
        conn.commit()

    with app.test_client() as client:
        switched = client.post(
            f"/lifts/{slot_id}/mode",
            data={"mode": "linear_t2", "weight": "105"},
        )

    assert switched.status_code == 302
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT mode, weight, target, streak, est1rm FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == ("linear_t2", 105.0, 8, 0, None)

    for week, driver_weight, supplementary_reps, driver_reps, expected_state in (
        (1, 80.0, 10, 7, (105.0, 6, 1, 107.04356430622721)),
        (2, 60.0, None, 5, (105.0, 4, 2, 107.04356430622721)),
        (3, 100.0, 10, 3, (98.0, 8, 0, None)),
    ):
        with app.test_client() as client:
            if supplementary_reps is not None:
                assert client.post(
                    "/training/sets/full",
                    data={
                        "expected_week": str(week),
                        "slot_id": str(slot_id),
                        "set_number": "1",
                        "actual_added_weight": str(driver_weight),
                        "reps": str(supplementary_reps),
                        "warmup": "0",
                        "drives_progression": "0",
                    },
                ).status_code == 200
            with sqlite3.connect(db_path) as conn:
                before_weight, before_target = conn.execute(
                    "SELECT weight, target FROM strength_state "
                    "WHERE slot_id = ?",
                    (slot_id,),
                ).fetchone()
            preview = client.post(
                f"/log/preview?lid={slot_id}",
                data={
                    "expected_week": str(week),
                    "slot_id": str(slot_id),
                    "focus_sequence": "1",
                    f"actual_added_weight_{slot_id}": str(driver_weight),
                    f"set_{slot_id}_3": str(driver_reps),
                },
            )
            assert preview.status_code == 200
            preview_html = preview.get_data(as_text=True)
            assert f"目标 {before_target} → {expected_state[1]}" in preview_html
            assert (
                f"Working Weight {before_weight} → {expected_state[0]} kg"
                in preview_html
            )
            assert client.post(
                "/training/sets/full",
                data={
                    "expected_week": str(week),
                    "slot_id": str(slot_id),
                    "set_number": "3",
                    "actual_added_weight": str(driver_weight),
                    "reps": str(driver_reps),
                    "warmup": "0",
                    "drives_progression": "1",
                    "e1rm_qualified": "0",
                },
            ).status_code == 200
            finalized = client.post(
                "/training/finalize", data={"expected_week": str(week)}
            )

        assert finalized.status_code == 200
        with sqlite3.connect(db_path) as conn:
            assert conn.execute(
                "SELECT weight, target, streak, est1rm FROM strength_state "
                "WHERE slot_id = ?",
                (slot_id,),
            ).fetchone() == pytest.approx(expected_state)

    with app.test_client() as client:
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "4",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "80",
                "reps": "1",
                "warmup": "0",
                "drives_progression": "0",
            },
        ).status_code == 200
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "4",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "80",
                "reps": "8",
                "warmup": "0",
                "drives_progression": "1",
                "e1rm_qualified": "0",
            },
        ).status_code == 200
        finalized = client.post(
            "/training/finalize", data={"expected_week": "4"}
        )

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT weight, target, streak, est1rm FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == pytest.approx(
            (105.0, 8, 0, 100.92693780842751)
        )


def test_bodyweight_t2_keeps_the_historical_work_set_peak_without_reset(tmp_path):
    db_path = tmp_path / "bodyweight-t2-peak.db"
    backup_dir = tmp_path / "backups"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET bodyweight = 80 WHERE id = 1")
        slot_id = insert_v1_slot(
            conn,
            name="Weighted pull-up",
            load_model="bodyweight",
            mode="linear_t2",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=10.0,
            weight=10.0,
            target=8,
            bodyweight_pct=1.0,
        )
        for week, bodyweight, bodyweight_pct in (
            (98, None, 1.0),
            (99, 80.0, None),
        ):
            session_id = conn.execute(
                "INSERT INTO training_session "
                "(program_week, day, bodyweight_kg, finalized_at) "
                "VALUES (?, 1, ?, 'legacy')",
                (week, bodyweight),
            ).lastrowid
            conn.execute(
                "INSERT INTO progression_event "
                "(session_id, slot_id, mode, bodyweight_pct) "
                "VALUES (?, ?, 'linear_t2', ?)",
                (session_id, slot_id, bodyweight_pct),
            )
            conn.execute(
                "INSERT INTO set_log "
                "(session_id, slot_id, set_number, actual_added_weight, reps) "
                "VALUES (?, ?, 1, 1000, 1)",
                (session_id, slot_id),
            )
        conn.commit()

    with app.test_client() as client:
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "4",
                "warmup": "0",
                "drives_progression": "1",
                "bodyweight_kg": "80",
            },
        ).status_code == 200
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "10",
                "reps": "10",
                "warmup": "0",
                "drives_progression": "0",
            },
        ).status_code == 200
        preview = client.post(
            f"/log/preview?lid={slot_id}",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "focus_sequence": "1",
                f"actual_added_weight_{slot_id}": "10",
                f"set_{slot_id}_3": "4",
            },
        )
        finalized = client.post(
            "/training/finalize", data={"expected_week": "1"}
        )

    assert preview.status_code == 200
    assert "est1RM 120.42 kg" in preview.get_data(as_text=True)
    assert "目标 8 → 4" in preview.get_data(as_text=True)
    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT weight, target, streak, est1rm FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == pytest.approx((10.0, 4, 0, 120.42400984450562))
        conn.execute("UPDATE settings SET bodyweight = 120 WHERE id = 1")
        conn.execute(
            "UPDATE program_slot SET bodyweight_pct = .5 WHERE id = ?",
            (slot_id,),
        )
        conn.commit()

    with app.test_client() as client:
        history = client.get("/training/history").get_json()
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "2",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "10",
                "reps": "3",
                "warmup": "0",
                "drives_progression": "1",
                "bodyweight_kg": "70",
            },
        ).status_code == 200
        finalized = client.post(
            "/training/finalize", data={"expected_week": "2"}
        )

    legacy_rows = [row for row in history if row["program_week"] in (98, 99)]
    week_one_rows = [row for row in history if row["program_week"] == 1]
    assert [row["actual_working_weight"] for row in legacy_rows] == [None, None]
    assert {row["actual_working_weight"] for row in week_one_rows} == {90.0}
    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT weight, target, streak, est1rm FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == pytest.approx((10.0, 4, 0, 120.42400984450562))


def test_switching_to_bodyweight_t2_does_not_apply_a_loadable_reset(tmp_path):
    db_path = tmp_path / "bodyweight-t2-switch.db"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        slot_id = insert_v1_slot(
            conn,
            name="Weighted dip",
            load_model="bodyweight",
            mode="linear_t3",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=10.0,
            weight=10.0,
            bodyweight_pct=0.0,
            est1rm=150.0,
        )
        conn.commit()

    with app.test_client() as client:
        switched = client.post(
            f"/lifts/{slot_id}/mode",
            data={"mode": "linear_t2"},
        )

    assert switched.status_code == 302
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT weight, target, streak, est1rm FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == (10.0, 8, 0, 150.0)
