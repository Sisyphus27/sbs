import sqlite3

from webapp.app import create_app
from tests.v1_helpers import insert_v1_slot


def _app_with_slots(tmp_path):
    db_path = tmp_path / "slot-state.db"
    app = create_app(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        primary_id = insert_v1_slot(
            conn,
            name="Squat",
            mode="sbs",
            day=1,
            sort_order=0,
            sets=5,
            max_seed=135.0,
            lift_kind="main",
            intensity=0.7,
            reps=5,
            repout=10,
            tm=135.0,
            est1rm=150.0,
            reseeded_cycle=1,
        )
        other_id = insert_v1_slot(
            conn,
            name="Curl",
            mode="linear_t3",
            day=2,
            sort_order=0,
            sets=3,
            start_weight=30.0,
            increment=2.5,
            weight=30.0,
            est1rm=40.0,
        )
    return app, db_path, primary_id, other_id


def _slot_state_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        return (
            conn.execute("SELECT * FROM program_slot ORDER BY id").fetchall(),
            conn.execute("SELECT * FROM strength_state ORDER BY slot_id").fetchall(),
        )


def test_mode_preview_is_read_only_at_the_flask_sqlite_seam(tmp_path):
    app, db_path, slot_id, _ = _app_with_slots(tmp_path)
    before = _slot_state_rows(db_path)

    with app.test_client() as client:
        response = client.get(f"/lifts/{slot_id}/mode?mode=linear_t2")

    assert response.status_code == 200
    assert b"linear_t2" in response.data
    assert _slot_state_rows(db_path) == before
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0


def test_edit_ui_routes_each_legal_mode_change_through_preview(tmp_path):
    app, _, slot_id, _ = _app_with_slots(tmp_path)

    with app.test_client() as client:
        response = client.get(f"/lifts/{slot_id}/edit")

    assert response.status_code == 200
    assert b'name="mode"' not in response.data
    assert f"/lifts/{slot_id}/mode?mode=linear_t2".encode() in response.data
    assert f"/lifts/{slot_id}/mode?mode=linear_t3".encode() in response.data


def test_mode_apply_updates_only_the_slot_and_its_unique_state(tmp_path):
    app, db_path, slot_id, other_id = _app_with_slots(tmp_path)
    with sqlite3.connect(db_path) as conn:
        other_before = (
            conn.execute(
                "SELECT mode, sets, start_weight FROM program_slot WHERE id = ?",
                (other_id,),
            ).fetchone(),
            conn.execute(
                "SELECT mode, tm, weight, target, streak, est1rm, reseeded_cycle "
                "FROM strength_state WHERE slot_id = ?",
                (other_id,),
            ).fetchone(),
        )

    with app.test_client() as client:
        response = client.post(
            f"/lifts/{slot_id}/mode",
            data={"mode": "linear_t2", "weight": "82.5"},
        )

    assert response.status_code == 302
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT mode FROM program_slot WHERE id = ?", (slot_id,)
        ).fetchone() == ("linear_t2",)
        assert conn.execute(
            "SELECT mode, tm, weight, target, streak, est1rm, reseeded_cycle "
            "FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == ("linear_t2", None, 82.5, 8, 0, 150.0, 1)
        other_after = (
            conn.execute(
                "SELECT mode, sets, start_weight FROM program_slot WHERE id = ?",
                (other_id,),
            ).fetchone(),
            conn.execute(
                "SELECT mode, tm, weight, target, streak, est1rm, reseeded_cycle "
                "FROM strength_state WHERE slot_id = ?",
                (other_id,),
            ).fetchone(),
        )
        assert other_after == other_before
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0


def test_manual_tm_override_is_a_direct_state_update(tmp_path):
    app, db_path, slot_id, other_id = _app_with_slots(tmp_path)
    with sqlite3.connect(db_path) as conn:
        slot_before = conn.execute(
            "SELECT * FROM program_slot WHERE id = ?", (slot_id,)
        ).fetchone()
        other_state_before = conn.execute(
            "SELECT * FROM strength_state WHERE slot_id = ?", (other_id,)
        ).fetchone()

    with app.test_client() as client:
        response = client.post(
            f"/lifts/{slot_id}/mode",
            data={"mode": "sbs", "tm": "142.75"},
        )

    assert response.status_code == 302
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT * FROM program_slot WHERE id = ?", (slot_id,)
        ).fetchone() == slot_before
        assert conn.execute(
            "SELECT mode, tm, weight, target, streak, est1rm, reseeded_cycle "
            "FROM strength_state WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == ("sbs", 142.75, None, None, 0, 150.0, 1)
        assert conn.execute(
            "SELECT * FROM strength_state WHERE slot_id = ?", (other_id,)
        ).fetchone() == other_state_before
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0


def test_ordinary_edit_updates_plan_fields_but_cannot_change_mode(tmp_path):
    app, db_path, slot_id, _ = _app_with_slots(tmp_path)
    with sqlite3.connect(db_path) as conn:
        state_before = conn.execute(
            "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone()

    with app.test_client() as client:
        response = client.post(
            f"/lifts/{slot_id}/edit",
            data={"sets": "4", "day": "3", "mode": "linear_t2"},
        )

    assert response.status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT day, sets, mode FROM program_slot WHERE id = ?", (slot_id,)
        ).fetchone() == (3, 4, "sbs")
        assert conn.execute(
            "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
        ).fetchone() == state_before
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0


def test_manual_tm_reseed_updates_only_the_current_slot_state(tmp_path):
    app, db_path, slot_id, other_id = _app_with_slots(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET week = 22 WHERE id = 1")
        other_before = (
            conn.execute(
                "SELECT * FROM program_slot WHERE id = ?", (other_id,)
            ).fetchone(),
            conn.execute(
                "SELECT * FROM strength_state WHERE slot_id = ?", (other_id,)
            ).fetchone(),
        )

    with app.test_client() as client:
        response = client.post(f"/reseed/{slot_id}", data={"max": "142.75"})

    assert response.status_code == 302
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT mode, max_seed FROM program_slot WHERE id = ?", (slot_id,)
        ).fetchone() == ("sbs", 142.75)
        assert conn.execute(
            "SELECT mode, tm, est1rm, reseeded_cycle FROM strength_state "
            "WHERE slot_id = ?",
            (slot_id,),
        ).fetchone() == ("sbs", 142.75, 150.0, 2)
        other_after = (
            conn.execute(
                "SELECT * FROM program_slot WHERE id = ?", (other_id,)
            ).fetchone(),
            conn.execute(
                "SELECT * FROM strength_state WHERE slot_id = ?", (other_id,)
            ).fetchone(),
        )
        assert other_after == other_before
        assert conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 0


def test_reseed_rejects_nonboundary_and_non_sbs_slot(tmp_path):
    app, db_path, slot_id, other_id = _app_with_slots(tmp_path)
    before = _slot_state_rows(db_path)

    with app.test_client() as client:
        nonboundary = client.post(f"/reseed/{slot_id}", data={"max": "160"})
    assert nonboundary.status_code == 302
    assert _slot_state_rows(db_path) == before

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET week = 22 WHERE id = 1")
    with app.test_client() as client:
        non_sbs = client.post(f"/reseed/{other_id}", data={"max": "60"})
    assert non_sbs.status_code == 302
    assert _slot_state_rows(db_path) == before
