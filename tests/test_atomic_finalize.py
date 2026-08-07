import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from sbs_cli.engine.onerm import estimate_1rm
from tests.v1_helpers import insert_v1_slot
from webapp import training_cli
from webapp.app import create_app
from webapp.services import training as training_service


def _app_with_t3_slot(tmp_path):
    db_path = tmp_path / "finalize.db"
    backup_dir = tmp_path / "backups"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(backup_dir),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET t3_target = 10 WHERE id = 1")
        slot_id = insert_v1_slot(
            conn,
            name="Curl",
            mode="linear_t3",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=30.0,
            weight=30.0,
        )
        conn.commit()
    return app, db_path, backup_dir, slot_id


def test_web_finalize_uses_only_driver_for_progression_and_canonical_e1rm(tmp_path):
    app, db_path, backup_dir, slot_id = _app_with_t3_slot(tmp_path)

    with app.test_client() as client:
        assert client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "1",
                "actual_added_weight": "100",
                "reps": "10",
                "warmup": "0",
                "drives_progression": "0",
            },
        ).status_code == 200
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "32.5",
                "reps": "10",
            },
        ).status_code == 200
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert finalized.status_code == 200
    assert finalized.get_json() == {"new_week": 2}
    with sqlite3.connect(db_path) as conn:
        state = conn.execute(
            "SELECT weight, est1rm FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()
        session = conn.execute(
            "SELECT finalized_at FROM training_session WHERE program_week = 1"
        ).fetchone()
        week = conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0]
    assert state[0] == 32.5
    assert state[1] == pytest.approx(estimate_1rm(32.5, 10))
    assert session[0] is not None
    assert week == 2
    assert list(backup_dir.glob("sbs-w1-*.db.bak"))


def test_cli_finalize_uses_the_same_domain_command(tmp_path, capsys):
    app, db_path, backup_dir, slot_id = _app_with_t3_slot(tmp_path)
    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "31",
                "reps": "10",
            },
        ).status_code == 200

    training_cli.run(
        [
            "finalize-week",
            "--db",
            str(db_path),
            "--backup-dir",
            str(backup_dir),
            "--expected-week",
            "1",
        ]
    )

    assert capsys.readouterr().out == "finalized week 1 to week 2\n"
    with sqlite3.connect(db_path) as conn:
        state = conn.execute(
            "SELECT weight, est1rm FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()
        week = conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0]
    assert state[0] == 32.5
    assert state[1] == pytest.approx(estimate_1rm(31.0, 10))
    assert week == 2
    assert list(backup_dir.glob("sbs-w1-*.db.bak"))


def test_duplicate_finalize_is_stale_and_does_not_progress_twice(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
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
        winner = client.post("/training/finalize", data={"expected_week": "1"})
        duplicate = client.post("/training/finalize", data={"expected_week": "1"})

    assert winner.status_code == 200
    assert duplicate.status_code == 409
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 2
        assert conn.execute(
            "SELECT weight FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone()[0] == 32.5


def test_concurrent_finalize_has_one_winner(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
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

    def finalize_once():
        with app.test_client() as client:
            return client.post(
                "/training/finalize", data={"expected_week": "1"}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: finalize_once(), range(2)))

    assert statuses == [200, 409]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 2
        assert conn.execute(
            "SELECT weight FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone()[0] == 32.5
        assert conn.execute(
            "SELECT COUNT(*) FROM training_session WHERE finalized_at IS NOT NULL"
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    "failure_stage",
    ["mode_advance", "state_write", "session_finalization", "week_transition"],
)
def test_finalize_failure_rolls_back_every_stage(tmp_path, monkeypatch, failure_stage):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
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

    if failure_stage == "mode_advance":
        class FailingMode:
            def advance(self, *args, **kwargs):
                raise RuntimeError("simulated mode advance failure")

        monkeypatch.setattr(training_service, "get_mode", lambda _mode: FailingMode())
    else:
        triggers = {
            "state_write": (
                "CREATE TRIGGER fail_state_write BEFORE UPDATE ON strength_state "
                "BEGIN SELECT RAISE(ABORT, 'simulated state write failure'); END"
            ),
            "session_finalization": (
                "CREATE TRIGGER fail_session_finalization BEFORE UPDATE ON training_session "
                "WHEN NEW.finalized_at IS NOT OLD.finalized_at "
                "BEGIN SELECT RAISE(ABORT, 'simulated session failure'); END"
            ),
            "week_transition": (
                "CREATE TRIGGER fail_week_transition BEFORE UPDATE ON settings "
                "WHEN NEW.week <> OLD.week "
                "BEGIN SELECT RAISE(ABORT, 'simulated week failure'); END"
            ),
        }
        with sqlite3.connect(db_path) as conn:
            conn.execute(triggers[failure_stage])
            conn.commit()

    with app.test_client() as client:
        with pytest.raises((RuntimeError, sqlite3.IntegrityError)):
            client.post("/training/finalize", data={"expected_week": "1"})

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 1
        assert conn.execute(
            "SELECT weight, est1rm FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == (30.0, None)
        assert conn.execute(
            "SELECT finalized_at FROM training_session WHERE program_week = 1"
        ).fetchone()[0] is None


@pytest.mark.parametrize("missing_projection_input", ["bodyweight", "percentage"])
def test_unavailable_bodyweight_projection_does_not_block_other_sessions(
    tmp_path, missing_projection_input
):
    db_path = tmp_path / "projection-gap.db"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET t3_target = 10 WHERE id = 1")
        bodyweight_slot = insert_v1_slot(
            conn,
            name="Pull-up",
            load_model="bodyweight",
            mode="linear_t3",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=10.0,
            weight=10.0,
            bodyweight_pct=1.0,
        )
        barbell_slot = insert_v1_slot(
            conn,
            name="Press",
            mode="linear_t3",
            day=2,
            sort_order=0,
            sets=3,
            start_weight=20.0,
            weight=20.0,
        )
        conn.commit()

    bodyweight_data = {
        "expected_week": "1",
        "slot_id": str(bodyweight_slot),
        "set_number": "3",
        "actual_added_weight": "10",
        "reps": "10",
    }
    if missing_projection_input == "percentage":
        bodyweight_data["bodyweight_kg"] = "80"
    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick", data=bodyweight_data
        ).status_code == 200
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(barbell_slot),
                "set_number": "3",
                "actual_added_weight": "20",
                "reps": "10",
            },
        ).status_code == 200
    if missing_projection_input == "percentage":
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE progression_event SET bodyweight_pct = NULL WHERE slot_id = ?",
                (bodyweight_slot,),
            )
            conn.commit()

    with app.test_client() as client:
        finalized = client.post("/training/finalize", data={"expected_week": "1"})
        history = client.get("/training/history")

    assert finalized.status_code == 200
    assert history.status_code == 200
    by_slot = {row["slot_id"]: row for row in history.get_json()}
    assert by_slot[bodyweight_slot]["actual_working_weight"] is None
    assert by_slot[bodyweight_slot]["canonical_e1rm"] is None
    assert by_slot[barbell_slot]["actual_working_weight"] == 20.0
    with sqlite3.connect(db_path) as conn:
        states = dict(conn.execute("SELECT slot_id, weight FROM strength_state"))
        assert states == {bodyweight_slot: 12.5, barbell_slot: 22.5}
        assert conn.execute(
            "SELECT COUNT(*) FROM training_session WHERE finalized_at IS NOT NULL"
        ).fetchone()[0] == 2
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 2


def test_finalize_uses_saved_progression_parameters_not_current_configuration(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "32.5",
                "reps": "10",
            },
        ).status_code == 200
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET incr = 10, t3_target = 20 WHERE id = 1")
        conn.execute(
            "UPDATE program_slot SET increment = 5 WHERE id = ?", (slot_id,)
        )
        conn.commit()

    with app.test_client() as client:
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT weight FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone()[0] == 32.5


def test_rough_driver_progresses_mode_without_updating_canonical_e1rm(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "30",
                "reps": "15",
            },
        ).status_code == 200
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        state = conn.execute(
            "SELECT weight, est1rm FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()
    assert state == (32.5, None)


def test_t2_reset_uses_saved_state_baseline_and_clears_cycle_peak(tmp_path):
    db_path = tmp_path / "t2-reset.db"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        slot_id = insert_v1_slot(
            conn,
            name="Row",
            mode="linear_t2",
            day=1,
            sort_order=0,
            sets=3,
            start_weight=100.0,
            weight=100.0,
            target=4,
            streak=2,
            est1rm=200.0,
        )
        conn.commit()

    with app.test_client() as client:
        assert client.post(
            "/training/sets/quick",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": "3",
                "actual_added_weight": "60",
                "reps": "3",
            },
        ).status_code == 200
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert finalized.status_code == 200
    with sqlite3.connect(db_path) as conn:
        state = conn.execute(
            "SELECT weight, target, streak, est1rm FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()
    assert state == (97.5, 8, 0, None)


def test_finalize_rejects_a_mode_changed_after_the_snapshot(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
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
        switched = client.post(
            f"/lifts/{slot_id}/mode", data={"mode": "linear_t2"}
        )
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert switched.status_code == 302
    assert finalized.status_code == 400
    with sqlite3.connect(db_path) as conn:
        modes = conn.execute(
            "SELECT ps.mode, ss.mode FROM program_slot AS ps "
            "JOIN strength_state AS ss ON ss.slot_id = ps.id WHERE ps.id = ?",
            (slot_id,),
        ).fetchone()
        assert modes == ("linear_t2", "linear_t2")
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 1
        assert conn.execute(
            "SELECT finalized_at FROM training_session WHERE program_week = 1"
        ).fetchone()[0] is None


def test_finalize_rejects_an_unconfirmed_migrated_progression_driver(tmp_path):
    app, db_path, _, slot_id = _app_with_t3_slot(tmp_path)
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
        finalized = client.post("/training/finalize", data={"expected_week": "1"})

    assert finalized.status_code == 400
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 1
        assert conn.execute(
            "SELECT finalized_at FROM training_session WHERE id = ?", (session_id,)
        ).fetchone()[0] is None
