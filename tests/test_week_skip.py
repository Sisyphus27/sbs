"""Saved week skips survive reload/export without inventing training facts."""
import json
import re

from tests.test_week_settlement import _save_driver


def _intent(client, slot_id, intent="skip", week=1):
    return client.post(
        f"/log/intent?lid={slot_id}",
        data={"expected_week": str(week), "slot_id": str(slot_id),
              "focus_sequence": "1", "intent": intent},
    )


def _snapshot(client):
    page = client.get("/").get_data(as_text=True)
    return json.loads(re.search(
        r'id="week-workspace-snapshot">(.*?)</script>', page, re.S
    ).group(1))


def test_saved_skip_survives_reload_export_and_resume(client, make_lift, db_conn):
    finished = make_lift(name="Finished")
    skipped = make_lift(name="Skipped")
    make_lift(name="NextDay", day=2)
    assert _save_driver(client, finished, set_number=3, reps=15, weight=30).status_code == 200
    facts_before = db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0]
    state_before = list(map(tuple, db_conn.execute("SELECT * FROM strength_state")))
    old_export = client.get("/export/week.html").get_data(as_text=True)

    assert _intent(client, skipped).status_code == 200
    assert _intent(client, skipped).status_code == 200  # safe retry
    saved = next(it for it in _snapshot(client)["lifts"] if it["slotId"] == skipped)
    assert saved["settlementIntent"] == "skip"
    exported = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1" class="st-full">' in exported
    assert '<details data-day="2" class="st-empty" open>' in exported
    assert 'class="name skipped">Skipped · 已跳过' in exported
    assert '✓ Skipped' not in exported
    assert '已完成 1 · 已跳过 1' in exported
    assert '<script' not in exported
    assert '<details data-day="1" class="st-part" open>' in old_export
    assert db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == facts_before
    assert list(map(tuple, db_conn.execute("SELECT * FROM strength_state"))) == state_before

    assert _intent(client, skipped, "record").status_code == 200
    assert _intent(client, skipped, "record").status_code == 200
    assert next(it for it in _snapshot(client)["lifts"] if it["slotId"] == skipped)["settlementIntent"] == "record"
    assert '<details data-day="1" class="st-part" open>' in client.get("/export/week.html").get_data(as_text=True)


def test_all_skipped_collapses_without_completed_marks_and_resets_next_week(client, make_lift, db_conn):
    slot = make_lift(name="Rested")
    assert _intent(client, slot).status_code == 200
    exported = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1" class="st-full">' in exported
    assert '已完成 0 · 已跳过 1' in exported
    assert 'class="mark">✓' not in exported
    assert db_conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 0
    review = client.post("/log/review", data={"expected_week": "1"})
    assert review.status_code == 200
    assert "本周跳过 1" in review.get_data(as_text=True)
    assert client.post("/log", data={"expected_week": "1"}).status_code == 302
    assert _snapshot(client)["lifts"][0]["settlementIntent"] == "record"
    assert _intent(client, slot, "record", week=1).status_code == 409


def test_skip_validation_and_resuming_before_recording(client, make_lift, db_conn):
    slot = make_lift(name="Partial")
    other = make_lift(name="Outside", day=5)
    for target, intent in ((slot, "bad"), (99999, "skip"), (other, "skip")):
        assert _intent(client, target, intent).status_code == 400
    assert _intent(client, slot).status_code == 200
    assert _save_driver(client, slot, set_number=3, reps=15, weight=30).status_code == 400
    assert db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 0
    assert _intent(client, slot, "record").status_code == 200
    assert _save_driver(client, slot, set_number=3, reps=15, weight=30).status_code == 200
    assert _intent(client, slot).status_code == 400


def test_skip_keeps_partial_sets_and_is_scoped_to_one_scheduled_lift(client, make_lift, db_conn):
    skipped = make_lift(name="Same exercise", day=1)
    other = make_lift(name="Same exercise", day=2)
    partial = client.post("/training/sets/full", data={
        "expected_week": "1", "slot_id": str(skipped), "set_number": "1",
        "actual_added_weight": "30", "reps": "10", "warmup": "0",
        "drives_progression": "0", "e1rm_qualified": "1",
    })
    assert partial.status_code == 200
    sets_before = list(map(tuple, db_conn.execute("SELECT * FROM set_log")))
    assert _intent(client, skipped).status_code == 200
    intents = {row["slotId"]: row["settlementIntent"] for row in _snapshot(client)["lifts"]}
    assert intents == {skipped: "skip", other: "record"}
    assert list(map(tuple, db_conn.execute("SELECT * FROM set_log"))) == sets_before
    assert client.post("/log/review", data={"expected_week": "1"}).status_code == 400
    assert _intent(client, skipped, "record").status_code == 200
    assert list(map(tuple, db_conn.execute("SELECT * FROM set_log"))) == sets_before


def test_skip_rejects_invalid_request_identity(client, make_lift):
    slot = make_lift()
    for data in ({}, {"expected_week": "1", "slot_id": "2", "focus_sequence": "1", "intent": "skip"}):
        assert client.post(f"/log/intent?lid={slot}", data=data).status_code == 400
