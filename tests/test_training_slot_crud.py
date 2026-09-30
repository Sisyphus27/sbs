"""Current UI uses the same schema as a normal fresh startup."""
import pytest

from webapp import repo
from webapp.services.training import save_draft_set, finalize_week


@pytest.mark.parametrize("load_model,mode", [
    ("barbell", "sbs"), ("barbell", "linear_t2"), ("barbell", "linear_t3"),
    ("bodyweight", "linear_t2"), ("bodyweight", "linear_t3"),
    ("pure_bodyweight", "none"),
])
def test_ui_create_refresh_edit_delete_current_schema(client, db_conn, load_model, mode):
    tables = {r[0] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"lifts", "lift_state", "history", "week_log"}.isdisjoint(tables)
    created = client.post("/lifts/new", data={
        "name": "Audit Lift", "load_model": load_model, "mode": mode,
        "day": 1, "sets": 3, "max": 100, "start": 20,
        "lift_kind": "main", "bodyweight_pct": 1,
    })
    assert created.status_code == 200
    slot = repo.list_training_slots(db_conn)[0]
    slot_id = slot["id"]
    assert slot["load_model"] == load_model
    assert repo.get_training_state(db_conn, slot_id)["mode"] == mode
    assert "Audit Lift" in client.get("/lifts").get_data(as_text=True)
    assert [s["slot_id"] for s in client.get("/training/plan").get_json()["slots"]] == [slot_id]
    changed = client.post(f"/lifts/{slot_id}/edit", data={"name": "Renamed", "day": 2})
    assert changed.status_code == 200
    assert "Renamed" in client.get("/lifts").get_data(as_text=True)
    assert repo.get_training_slot(db_conn, slot_id)["day"] == 2
    deleted = client.post(f"/lifts/{slot_id}/delete")
    assert deleted.status_code == 200 and deleted.data == b""
    assert "Renamed" not in client.get("/lifts").get_data(as_text=True)
    assert client.get("/training/plan").get_json()["slots"] == []
    assert repo.get_training_state(db_conn, slot_id) is None
    assert db_conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 0
    assert db_conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("finalized", [False, True])
def test_delete_preserves_draft_and_finalized_training(client, db_conn, make_lift, finalized):
    slot_id = make_lift(name="Recorded")
    save_draft_set(db_conn, expected_week=1, slot_id=slot_id, set_number=3,
                   actual_added_weight=30, reps=15, drives_progression=True)
    if finalized:
        finalize_week(db_conn, expected_week=1)
    before = [tuple(row) for row in repo.list_training_facts(db_conn)]
    state = dict(repo.get_training_state(db_conn, slot_id))
    response = client.post(f"/lifts/{slot_id}/delete")
    # A rendered error card must replace the card rather than hiding the Lift.
    assert response.status_code == 200
    assert "cannot be deleted" in response.get_data(as_text=True)
    assert "Recorded" in client.get("/lifts").get_data(as_text=True)
    assert [tuple(row) for row in repo.list_training_facts(db_conn)] == before
    assert dict(repo.get_training_state(db_conn, slot_id)) == state
    assert db_conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_creation_rolls_back_exercise_and_slot(client, db_conn):
    response = client.post("/lifts/new", data={
        "name": "Invalid", "load_model": "barbell", "mode": "linear_t3",
        "day": 1, "sets": 0, "start": 20,
    })
    assert response.status_code == 400
    for table in ("exercise", "program_slot", "strength_state"):
        assert db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_delete_unknown_slot_returns_not_found(client):
    assert client.post("/lifts/999/delete").status_code == 404
