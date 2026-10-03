import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from webapp import backup, repo
from webapp.routes import plan as plan_routes
from webapp.services.training import training_history


def _set_data(slot_id, set_number, reps, *, week=1, actual_added_weight=None):
    data = {
        "expected_week": str(week),
        "slot_id": str(slot_id),
        "set_number": str(set_number),
        "save_sequence": "1",
        "focused_slot_id": str(slot_id),
        "focus_sequence": "1",
        f"set_{slot_id}_{set_number}": str(reps),
    }
    if actual_added_weight is not None:
        data[f"actual_added_weight_{slot_id}"] = str(actual_added_weight)
    return data


def _save_set(client, slot_id, set_number, reps, *, week=1,
              actual_added_weight=None):
    return client.post(
        f"/log/save?lid={slot_id}&set_number={set_number}",
        data=_set_data(
            slot_id,
            set_number,
            reps,
            week=week,
            actual_added_weight=actual_added_weight,
        ),
    )


def _slot_facts(conn, slot_id):
    return [row for row in training_history(conn) if row["slot_id"] == slot_id]


def _workspace_snapshot(html):
    marker = '<script type="application/json" id="week-workspace-snapshot">'
    payload = html.split(marker, 1)[1].split("</script>", 1)[0]
    return json.loads(payload)


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


@pytest.mark.parametrize(
    "tm, actual_weight, reps, next_tm, next_weight",
    [(100.0, 90.0, 8, 100.0, 80.0),
     (100.0, 90.0, 6, 95.0, 75.0),
     (100.0, 70.0, 8, 100.0, 80.0),
     (100.5, 75.0, 9, 101.0025, 80.0),
     (100.0, 0.0, 0, 95.0, 75.0)],
)
def test_sbs_actual_weight_does_not_rebase_default_preview_or_settlement(
        client, make_lift, db_conn, tm, actual_weight, reps, next_tm, next_weight):
    lid = make_lift(name="Squat", mode="sbs", max=tm, lift_kind="main", sets=5)
    db_conn.execute("UPDATE settings SET week = 8")
    db_conn.execute(
        "UPDATE sbs_schedule SET intensity = .75, repout = 8 "
        "WHERE kind = 'main' AND week = 8"
    )
    db_conn.execute(
        "UPDATE sbs_schedule SET intensity = .8 WHERE kind = 'main' AND week = 9"
    )
    db_conn.commit()
    before = client.get("/training/plan").get_json()

    saved = _save_set(client, lid, 5, reps, week=8, actual_added_weight=actual_weight)
    assert saved.status_code == 200
    assert f"下一周 Working Weight {next_weight} kg" in saved.get_data(as_text=True)
    assert client.get("/training/plan").get_json() == before
    review = client.post("/log/review", data={"expected_week": "8"})
    assert review.status_code == 200
    assert f"下一周 Working Weight {next_weight} kg" in review.get_data(as_text=True)
    assert client.post("/training/finalize", data={"expected_week": "8"}).status_code == 200
    after = client.get("/training/plan").get_json()
    assert after["expected_week"] == 9
    assert after["slots"][0]["planned_added_weight"] == next_weight
    assert repo.get_training_state(db_conn, lid)["tm"] == next_tm
    assert _slot_facts(db_conn, lid)[0]["actual_added_weight"] == actual_weight


@pytest.mark.parametrize("weights", [[90, 95, 90, 90], [90, 75, 75]])
def test_sbs_editing_and_undo_use_original_prescription(
        client, make_lift, db_conn, weights):
    lid = make_lift(mode="sbs", max=100.5, lift_kind="main")
    db_conn.execute(
        "UPDATE sbs_schedule SET intensity = .75, repout = 8 WHERE kind = 'main' AND week = 1"
    )
    db_conn.commit()
    before = client.get("/training/plan").get_json()
    for weight in weights:
        data = _set_data(lid, 3, 8, actual_added_weight=weight)
        preview = client.post(f"/log/preview?lid={lid}", data=data)
        assert preview.status_code == 200
        saved = _save_set(client, lid, 3, 8, actual_added_weight=weight)
        assert saved.status_code == 200
        assert client.get("/training/plan").get_json() == before
    assert "Training Max 100.5 → 100.5" in saved.get_data(as_text=True)
    assert client.post("/training/finalize", data={"expected_week": "1"}).status_code == 200
    assert repo.get_training_state(db_conn, lid)["tm"] == 100.5


@pytest.mark.parametrize("endpoint", ["/log", "/training/finalize"])
@pytest.mark.parametrize(
    "actual_weight,reps,next_tm,next_weight",
    [(90.0, 8, 120.0, 95.0), (90.0, 6, 114.0, 90.0),
     (70.0, 8, 70 / .75, 75.0), (75.0, 8, 100.0, 80.0)],
)
def test_sbs_explicit_calibration_preview_matches_commit(
        client, make_lift, db_conn, endpoint, actual_weight, reps, next_tm, next_weight):
    lid = make_lift(name="Squat", mode="sbs", max=100.5, lift_kind="main")
    other_id = make_lift(name="Bench", mode="sbs", max=100.5, lift_kind="main")
    with db_conn:
        db_conn.execute("UPDATE settings SET week = 8")
        db_conn.execute(
            "UPDATE sbs_schedule SET intensity = .75, repout = 8 "
            "WHERE kind = 'main' AND week = 8"
        )
        db_conn.execute(
            "UPDATE sbs_schedule SET intensity = .8, repout = 8 "
            "WHERE kind = 'main' AND week = 9"
        )
    for slot_id in (lid, other_id):
        assert _save_set(client, slot_id, 3, reps, week=8,
                         actual_added_weight=actual_weight).status_code == 200
    before = client.get("/training/plan").get_json()
    default_html = client.post("/log/review", data={"expected_week": "8"}).get_data(as_text=True)
    assert 'name="calibrate_tm_slot_ids"' in default_html
    assert "checked" not in default_html
    data = {"expected_week": "8", "calibrate_tm_slot_ids": str(lid)}
    review = client.post("/log/review", data=data)
    assert review.status_code == 200
    html = review.get_data(as_text=True)
    assert "checked" in html
    assert f"下一周 Working Weight {next_weight} kg" in html
    assert client.get("/training/plan").get_json() == before
    # Clearing the selection previews the original rule without changing the draft.
    assert client.post("/log/review", data={"expected_week": "8"}).get_data(as_text=True) == default_html
    assert client.post(endpoint, data=data).status_code in (200, 302)
    assert repo.get_training_state(db_conn, lid)["tm"] == pytest.approx(next_tm)
    assert repo.get_training_state(db_conn, other_id)["tm"] == pytest.approx(
        100.5 * (.95 if reps == 6 else 1)
    )
    assert _slot_facts(db_conn, lid)[0]["actual_added_weight"] == actual_weight
    # Calibration is a choice for this settlement, never a saved preference.
    for slot_id in (lid, other_id):
        assert _save_set(client, slot_id, 3, 8, week=9,
                         actual_added_weight=50).status_code == 200
    next_review = client.post("/log/review", data={"expected_week": "9"})
    assert "checked" not in next_review.get_data(as_text=True)
    assert client.post(endpoint, data={"expected_week": "9"}).status_code in (200, 302)
    assert repo.get_training_state(db_conn, lid)["tm"] == pytest.approx(next_tm)


@pytest.mark.parametrize("endpoint", ["/log/review", "/log", "/training/finalize"])
@pytest.mark.parametrize("selection", ["bad", "unknown", "non_sbs", "skipped"])
def test_invalid_tm_calibration_selection_does_not_settle(
        client, make_lift, db_conn, app, endpoint, selection):
    lid = make_lift(mode="sbs", max=100, lift_kind="main")
    other_id = make_lift(mode="linear_t3", start=30)
    skipped_id = make_lift(mode="sbs", max=100, lift_kind="main")
    for slot_id in (lid, other_id):
        assert _save_set(client, slot_id, 3, 8, actual_added_weight=90).status_code == 200
    invalid_id = {"bad": "not-an-id", "unknown": "99999",
                  "non_sbs": str(other_id), "skipped": str(skipped_id)}[selection]
    before = client.get("/training/plan").get_json()
    response = client.post(endpoint, data={
        "expected_week": "1", "skipped_slot_ids": str(skipped_id),
        "calibrate_tm_slot_ids": invalid_id,
    })
    assert response.status_code == 400
    assert client.get("/training/plan").get_json() == before
    assert all(row["finalized_at"] is None for row in training_history(db_conn))
    assert not list(Path(app.config["BACKUP_DIR"]).glob("*.db.bak"))


@pytest.mark.parametrize("intensity", [None, float("inf")])
def test_invalid_sbs_snapshot_cannot_rebase_or_finalize(
        client, make_lift, db_conn, intensity):
    lid = make_lift(mode="sbs", max=100, lift_kind="main")
    assert _save_set(client, lid, 3, 8, actual_added_weight=90).status_code == 200
    before = client.get("/training/plan").get_json()
    db_conn.execute("UPDATE progression_event SET planned_intensity = ?", (intensity,))
    db_conn.commit()
    preview = client.post(
        f"/log/preview?lid={lid}", data=_set_data(lid, 3, 8, actual_added_weight=95),
    )
    assert preview.status_code == 200
    assert "Training Max" not in preview.get_data(as_text=True)
    assert client.post("/training/finalize", data={"expected_week": "1"}).status_code == 400
    assert client.get("/training/plan").get_json() == before
    assert client.get("/training/history").get_json()[0]["actual_added_weight"] == 90


@pytest.mark.parametrize(
    "mode, load_model, target, streak, actual_weight, reps, next_weight, next_target, next_streak",
    [
        ("linear_t2", "barbell", 8, 0, 60, 8, 63, 8, 0),
        ("linear_t2", "barbell", 8, 0, 60, 7, 60, 6, 1),
        ("linear_t2", "barbell", 6, 1, 60, 6, 63, 6, 0),
        ("linear_t2", "barbell", 6, 1, 60, 5, 60, 4, 2),
        ("linear_t2", "barbell", 4, 2, 60, 3, 57, 8, 0),
        ("linear_t2", "bodyweight", 8, 0, 7.5, 2, 7.5, 4, 0),
        ("linear_t2", "bodyweight", 8, 0, 7.5, 12, 7.5, 10, 0),
        ("linear_t3", "barbell", None, 0, 40, 15, 43, None, 0),
        ("linear_t3", "barbell", None, 0, 40, 14, 40, None, 0),
        ("linear_t3", "barbell", None, 0, 0, 0, 0, None, 0),
    ],
)
def test_actual_weight_keeps_each_linear_modes_progression(
        client, make_lift, db_conn, mode, load_model, target, streak,
        actual_weight, reps, next_weight, next_target, next_streak):
    lid = make_lift(mode=mode, load_model=load_model, start=30, incr=3,
                    bodyweight_pct=1.0 if load_model == "bodyweight" else 0.0)
    db_conn.execute(
        "UPDATE strength_state SET target = ?, streak = ?, est1rm = 200 WHERE slot_id = ?",
        (target, streak, lid),
    )
    db_conn.commit()
    before = client.get("/training/plan").get_json()
    for _ in range(2):
        saved = _save_set(client, lid, 3, reps, actual_added_weight=actual_weight)
        assert saved.status_code == 200, saved.get_data(as_text=True)
        assert client.get("/training/plan").get_json() == before
    review = client.post("/log/review", data={"expected_week": "1"})
    assert review.status_code == 200
    assert client.post("/training/finalize", data={"expected_week": "1"}).status_code == 200
    state = repo.get_training_state(db_conn, lid)
    assert (state["weight"], state["target"], state["streak"]) == (
        next_weight, next_target, next_streak,
    )
    if mode == "linear_t2" and load_model == "barbell":
        assert state["est1rm"] == (None if target == 4 and reps < 4 else 200)
    next_slot = client.get("/training/plan").get_json()["slots"][0]
    assert next_slot["planned_added_weight"] == next_weight
    assert next_slot["planned_target"] == (15 if mode == "linear_t3" else next_target)


def test_live_week_pages_load_app_script_once_without_changing_offline_export(
        client):
    app_script = '<script src="/static/app.js"></script>'

    workspace = client.get("/").get_data(as_text=True)
    review = client.post(
        "/log/review", data={"expected_week": "1"}
    ).get_data(as_text=True)
    lifts = client.get("/lifts").get_data(as_text=True)
    offline_export = client.get("/export/week.html").get_data(as_text=True)

    assert workspace.count(app_script) == 1
    assert review.count(app_script) == 1
    assert lifts.count(app_script) == 1
    assert app_script not in offline_export


def test_homepage_renders_week_ledger_in_day_and_plan_order(client, make_lift):
    day_two = make_lift(name="Day two row", day=2, sort_order=0, start=30.0)
    day_one_second = make_lift(
        name="Day one second", day=1, sort_order=2, start=35.0
    )
    day_one_first = make_lift(
        name="Day one first", day=1, sort_order=1, start=40.0
    )

    html = client.get("/").get_data(as_text=True)

    assert 'class="week-ledger"' in html
    assert html.count('class="week-ledger-row is-unresolved"') == 3
    assert html.index("Day one first") < html.index("Day one second")
    assert html.index("Day one second") < html.index("Day two row")
    assert f'id="ledger-row-{day_one_first}"' in html
    assert f'id="ledger-row-{day_one_second}"' in html
    assert f'id="ledger-row-{day_two}"' in html
    assert "variant=" not in html and "flow=" not in html


def test_week_ledger_defaults_to_weight_and_driver_then_popovers_earlier_sets(
        client, make_lift):
    lid = make_lift(name="Curl", sets=4, start=30.0)

    html = client.get("/").get_data(as_text=True)
    row = html[html.index(f'id="ledger-row-{lid}"'):]
    row = row[:row.index("</tr>")]
    popover_marker = f'<div id="earlier-sets-{lid}"'
    default_controls, marker, earlier_sets = row.partition(popover_marker)

    assert marker
    assert f'name="actual_added_weight_{lid}"' in default_controls
    assert f'name="set_{lid}_4"' in default_controls
    assert f'popovertarget="earlier-sets-{lid}"' in default_controls
    assert f'id="earlier-progress-{lid}"' in default_controls
    assert "补录 0/3" in default_controls
    assert 'popover="auto"' in earlier_sets
    assert "前置组补录" in earlier_sets
    assert all(
        f'name="set_{lid}_{set_number}"' in earlier_sets
        for set_number in (1, 2, 3)
    )
    assert f'name="set_{lid}_4"' not in earlier_sets
    assert "<details" not in row


def test_week_ledger_shares_confirmed_weight_with_earlier_sets(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)

    earlier = _save_set(
        client, lid, 1, 8, actual_added_weight=32.5
    )
    driver = _save_set(
        client, lid, 3, 0, actual_added_weight=35.0
    )
    edited_driver = _save_set(
        client, lid, 3, 0, actual_added_weight=37.5
    )

    assert earlier.status_code == 200
    assert driver.status_code == 200
    assert edited_driver.status_code == 200
    assert [
        (
            row["set_number"],
            row["actual_added_weight"],
            row["reps"],
            row["drives_progression"],
        )
        for row in _slot_facts(db_conn, lid)
    ] == [
        (1, 37.5, 8, 0),
        (3, 37.5, 0, 1),
    ]


def test_week_ledger_preserves_load_model_weight_semantics(
        client, make_lift, db_conn):
    repo.update_settings(db_conn, bodyweight=75.0)
    weighted = make_lift(
        name="Weighted chin-up",
        load_model="bodyweight",
        mode="linear_t2",
        start=0.0,
        bodyweight_pct=1.0,
    )
    pure = make_lift(
        name="Push-up",
        load_model="pure_bodyweight",
        mode="none",
        start=0.0,
        bodyweight_pct=1.0,
    )

    html = client.get("/").get_data(as_text=True)
    weighted_row = html[html.index(f'id="ledger-row-{weighted}"'):]
    weighted_row = weighted_row[:weighted_row.index("</tr>")]
    pure_row = html[html.index(f'id="ledger-row-{pure}"'):]
    pure_row = pure_row[:pure_row.index("</tr>")]

    assert f'name="actual_added_weight_{weighted}"' in weighted_row
    assert "Planned Working Weight 75.0 kg" in weighted_row
    assert (
        f'type="hidden" name="actual_added_weight_{pure}" value="0"'
        in pure_row
    )
    assert "Actual Added 0 kg" in pure_row
    assert "Planned Working Weight 75.0 kg" in pure_row

    weighted_response = _save_set(
        client, weighted, 3, 8, actual_added_weight=10.0
    )
    weighted_fragment = weighted_response.get_data(as_text=True)
    weighted_page = client.get("/").get_data(as_text=True)
    weighted_row = weighted_page[
        weighted_page.index(f'id="ledger-row-{weighted}"'):
    ]
    weighted_row = weighted_row[:weighted_row.index("</tr>")]

    assert weighted_response.status_code == 200
    assert f'id="working-weight-{weighted}"' in weighted_fragment
    assert 'data-fragment-role="persistent"' in weighted_fragment
    assert 'hx-swap-oob' not in weighted_fragment
    assert "Actual Working Weight 不可用" in weighted_fragment
    assert "Actual Working Weight 不可用" in weighted_row

    recorded = client.post(
        "/training/sets/full",
        data={
            "expected_week": "1",
            "slot_id": str(weighted),
            "set_number": "3",
            "actual_added_weight": "10",
            "reps": "8",
            "warmup": "0",
            "drives_progression": "1",
            "e1rm_qualified": "0",
            "bodyweight_kg": "80",
        },
    )
    recorded_page = client.get("/").get_data(as_text=True)
    recorded_row = recorded_page[
        recorded_page.index(f'id="ledger-row-{weighted}"'):
    ]
    recorded_row = recorded_row[:recorded_row.index("</tr>")]

    assert recorded.status_code == 200
    assert "Actual Working Weight 90.0 kg" in recorded_row

    response = _save_set(
        client, pure, 3, 8, actual_added_weight=2.5
    )
    assert response.status_code == 400
    assert _slot_facts(db_conn, pure) == []


def test_week_ledger_renders_zero_reps_as_a_logged_failure(client, make_lift):
    lid = make_lift(name="Curl", sets=3, start=30.0)

    response = _save_set(
        client, lid, 3, 0, actual_added_weight=32.5
    )
    fragment = response.get_data(as_text=True)
    page = client.get("/").get_data(as_text=True)

    assert response.status_code == 200
    assert '"settlementReady": true' in fragment
    assert '"driverReps": 0' in fragment
    assert 'hx-swap-oob' not in fragment
    assert f'id="ledger-row-{lid}"' in page
    assert 'class="week-ledger-row is-logged is-zero"' in page
    assert "已补录 · 0 次失败" in page


def test_plan_renders_duplicate_names_with_distinct_state(client, make_lift):
    """Same name on two days must render each day's own weight (id-keyed, not clobbered)."""
    first_id = make_lift(name="Face Pull", day=2, start=30.0)
    second_id = make_lift(name="Face Pull", day=4, start=45.0)
    html = client.get("/").get_data(as_text=True)
    first_row = html.split(f'id="ledger-row-{first_id}"', 1)[1].split("</tr>", 1)[0]
    second_row = html.split(f'id="ledger-row-{second_id}"', 1)[1].split("</tr>", 1)[0]
    assert "Face Pull" in first_row and "30.0 kg" in first_row
    assert "Face Pull" in second_row and "45.0 kg" in second_row


def test_plan_and_export_hide_slots_outside_days_per_week(client, make_lift):
    make_lift(name="Displayed", day=1, start=30.0)
    make_lift(name="Outside program", day=5, start=45.0)

    homepage = client.get("/").get_data(as_text=True)
    export = client.get("/export/week.html").get_data(as_text=True)

    assert "Displayed" in homepage and "Displayed" in export
    assert "Outside program" not in homepage
    assert "Outside program" not in export


def test_plan_submit_advances(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    assert _save_set(client, lid, 5, 13).status_code == 200
    rv = client.post("/log", data={"expected_week": "1"})
    assert rv.status_code == 302
    assert repo.get_settings(db_conn)["week"] == 2


def test_plan_submit_rejects_stale_expected_week(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    assert _save_set(client, lid, 5, 13).status_code == 200
    data = {"expected_week": "1"}

    assert client.post("/log", data=data).status_code == 302
    assert client.post("/log", data=data).status_code == 409

    assert repo.get_settings(db_conn)["week"] == 2
    facts = _slot_facts(db_conn, lid)
    assert [(row["program_week"], row["set_number"], row["reps"])
            for row in facts] == [(1, 5, 13)]


def test_plan_submit_allows_only_one_concurrent_expected_week(app, make_lift, db_conn,
                                                              monkeypatch):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    with app.test_client() as setup_client:
        assert _save_set(setup_client, lid, 5, 13).status_code == 200
        assert setup_client.post("/log/review", data={"expected_week": "1"}).status_code == 200
    both_submitting = threading.Barrier(2)
    real_finalize = plan_routes.finalize_week

    def synchronized_finalize(*args, **kwargs):
        both_submitting.wait(timeout=5)
        return real_finalize(*args, **kwargs)

    snapshot_calls = []
    snapshot_lock = threading.Lock()
    second_snapshot = threading.Event()

    def recording_snapshot(*args, **kwargs):
        with sqlite3.connect(app.config["DB_PATH"]) as snapshot_source:
            snapshot_week = snapshot_source.execute(
                "SELECT week FROM settings WHERE id = 1"
            ).fetchone()[0]
        with snapshot_lock:
            snapshot_calls.append(snapshot_week)
            call_number = len(snapshot_calls)
        if call_number == 1:
            second_snapshot.wait(timeout=0.2)
        else:
            second_snapshot.set()
        return "unused.db.bak"

    monkeypatch.setattr(plan_routes, "finalize_week", synchronized_finalize)
    monkeypatch.setattr(backup, "snapshot", recording_snapshot)

    def submit():
        with app.test_client() as thread_client:
            return thread_client.post(
                "/log", data={"expected_week": "1"}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _n: submit(), range(2)))

    assert sorted(statuses) == [302, 409]
    assert snapshot_calls == [1]
    assert repo.get_settings(db_conn)["week"] == 2
    assert len(_slot_facts(db_conn, lid)) == 1


def test_plan_submit_requires_expected_week(client):
    assert client.post("/log", data={}).status_code == 400


def test_plan_submit_snapshot_contains_pre_advance_state(client, app, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 3, 18).status_code == 200
    rv = client.post("/log", data={"expected_week": "1"})

    assert rv.status_code == 302
    backup_path = next(Path(app.config["BACKUP_DIR"]).glob("sbs-w1-*.db.bak"))
    with sqlite3.connect(backup_path) as snapshot_conn:
        assert snapshot_conn.execute(
            "SELECT week FROM settings WHERE id = 1"
        ).fetchone()[0] == 1
        assert snapshot_conn.execute(
            "SELECT COUNT(*) FROM progression_event"
        ).fetchone()[0] == 1
        assert snapshot_conn.execute(
            "SELECT set_number, reps FROM set_log WHERE slot_id = ?", (lid,)
        ).fetchall() == [(3, 18)]
        assert snapshot_conn.execute(
            "SELECT weight FROM strength_state WHERE slot_id = ?", (lid,)
        ).fetchone() == (30.0,)


def test_plan_submit_rolls_back_when_week_advance_fails(
        client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    assert _save_set(client, lid, 5, 13).status_code == 200
    db_conn.execute("""
        CREATE TRIGGER fail_week_advance
        BEFORE UPDATE OF week ON settings
        BEGIN
            SELECT RAISE(ABORT, 'simulated week advance failure');
        END
    """)
    db_conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="simulated week advance failure"):
        client.post("/log", data={"expected_week": "1"})

    assert repo.get_settings(db_conn)["week"] == 1
    assert db_conn.execute("SELECT COUNT(*) FROM progression_event").fetchone()[0] == 1
    assert [(row["program_week"], row["set_number"], row["reps"])
            for row in _slot_facts(db_conn, lid)] == [(1, 5, 13)]


def test_plan_submit_form_has_double_click_guard(client):
    """Submit form must disable its buttons on submit (ADR 0010).

    plan.submit is non-idempotent: a double-click double-advances the week.
    The guard is client-side JS, so at the pytest level we assert the opt-in
    marker is present on the rendered form; the JS body itself is not
    unit-tested here (no browser/JS runner in the suite).
    """
    html = client.post(
        "/log/review", data={"expected_week": "1"}
    ).get_data(as_text=True)
    submit_form = html.split('action="/log"', 1)[1].split("</form>", 1)[0]
    assert "data-disable-submit" in submit_form


def test_plan_form_carries_expected_program_week(client):
    html = client.get("/").get_data(as_text=True)
    assert 'type="hidden" name="expected_week" value="1"' in html


def test_week_workspace_bootstraps_from_structured_snapshot_without_old_htmx_coordination(
        client, make_lift):
    logged_id = make_lift(name="Curl", start=30.0)
    unresolved_id = make_lift(name="Row", start=40.0, day=2)
    assert _save_set(
        client, logged_id, 3, 0, actual_added_weight=30.0
    ).status_code == 200

    html = client.get("/").get_data(as_text=True)
    snapshot = _workspace_snapshot(html)

    assert snapshot["expectedWeek"] == 1
    assert snapshot["focusedSlotId"] is None
    assert snapshot["focusSequence"] == 0
    assert [lift["slotId"] for lift in snapshot["lifts"]] == [
        logged_id, unresolved_id
    ]
    logged, unresolved = snapshot["lifts"]
    assert logged["driverSetNumber"] == 3
    assert logged["draft"]["driverReps"] == 0
    assert logged["serverSnapshot"] == {
        "coverage": ["addedWeight", "driverReps"],
        "driverReps": 0,
        "hasDriverFact": True,
        "settlementReady": True,
    }
    assert unresolved["draft"]["driverReps"] == ""
    assert unresolved["serverSnapshot"] == {
        "coverage": [],
        "driverReps": None,
        "hasDriverFact": False,
        "settlementReady": False,
    }
    workspace = html.split('data-week-settlement', 1)[1]
    for obsolete in (
        "hx-sync", "hx-target", "hx-swap", "hx-post",
        "data-settlement-state", "data-server-state", "data-server-zero",
    ):
        assert obsolete not in workspace
    assert '<script src="/static/week_workspace.js"></script>' in html


def test_week_request_errors_have_one_coordinator_owned_region_and_return_details(
        client, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    html = client.get("/").get_data(as_text=True)
    row = html.split(f'id="ledger-row-{lid}"', 1)[1].split("</tr>", 1)[0]

    assert row.count('data-workspace-error') == 1
    assert row.count('role="alert"') == 1
    assert 'data-request-error-id' not in row
    assert 'data-server-state' not in row

    saved = _save_set(client, lid, 3, 10, actual_added_weight=30.0)
    assert saved.status_code == 200
    assert '"settlementReady": true' in saved.get_data(as_text=True)

    invalid = _save_set(client, lid, 3, -1, actual_added_weight=30.0)
    assert invalid.status_code == 400
    assert invalid.get_data(as_text=True) == (
        "week, slot, and set number must be positive; reps must be nonnegative"
    )
    assert "<input" not in invalid.get_data(as_text=True)
    assert "<tr" not in invalid.get_data(as_text=True)


def test_export_week_standalone_with_progress(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    assert _save_set(client, lid, 5, 11).status_code == 200
    rv = client.get("/export/week.html")
    assert rv.status_code == 200
    assert "attachment" in rv.headers.get("Content-Disposition", "")
    assert f'week-1.html' in rv.headers.get("Content-Disposition", "")
    html = rv.get_data(as_text=True)
    assert "Week 1" in html and "Squat" in html
    # standalone / offline: no server-relative deps
    assert "hx-post" not in html and "/log/" not in html and "htmx" not in html


def test_plan_view_shows_week2_schedule_values(client, make_lift, db_conn):
    """Week-2 plan view pulls intensity/reps/repout from sbs_schedule, not lifts columns.

    Week 2 main schedule = 0.75 / 4 / 8. With tm=100, working weight is
    MROUND(100*0.75, 2.5) = 75.0; the rendered reps/repout come from the schedule
    row (4 / 8), ignoring whatever stale values sit in lifts.intensity/reps/repout.
    """
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=100.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    repo.save_training_state(db_conn, lid, mode="sbs", tm=100.0, weight=None,
                         target=None, streak=0, est1rm=None)
    repo.set_week(db_conn, 2)
    db_conn.commit()
    html = client.get("/").get_data(as_text=True)
    assert "Week 2" in html
    assert "75.0 kg" in html          # schedule-driven weight (MROUND(100*0.75,2.5))
    assert "x 4 x 5" in html          # schedule-driven reps (4) x sets (5)
    assert "rep-out 8" in html        # schedule-driven repout (8)


def test_autosave_persists_and_prefills_then_advances(client, make_lift, db_conn):
    """Daily logging saves one set, prefills it, then finalization keeps the fact."""
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    rv = _save_set(client, lid, 5, 11)
    assert rv.status_code == 200
    assert "已保存" in rv.get_data(as_text=True)
    page = client.get("/").get_data(as_text=True)
    assert 'value="11"' in page and "已保存" in page
    rv = client.post("/log", data={"expected_week": "1"})
    assert rv.status_code == 302
    assert repo.get_settings(db_conn)["week"] == 2
    assert [(row["program_week"], row["set_number"], row["reps"])
            for row in _slot_facts(db_conn, lid)] == [(1, 5, 11)]


def test_autosave_rejects_stale_expected_week(client, make_lift, db_conn):
    lid = make_lift(name="Curl", start=30.0)
    assert client.post(
        "/log",
        data={"expected_week": "1", "skipped_slot_ids": str(lid)},
    ).status_code == 302

    rv = _save_set(client, lid, 3, 18, week=1)

    assert rv.status_code == 409
    assert _slot_facts(db_conn, lid) == []


def test_plan_view_prefills_every_saved_set(client, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 1, 15).status_code == 200
    assert _save_set(client, lid, 2, 15).status_code == 200
    assert _save_set(client, lid, 3, 18).status_code == 200
    html = client.get("/").get_data(as_text=True)
    assert html.count("已保存") == 3
    assert html.count('value="15"') == 2
    assert 'value="18"' in html


def test_earlier_set_zero_updates_confirmed_progress(client, make_lift):
    lid = make_lift(name="Curl", sets=3, start=30.0)

    first = _save_set(client, lid, 1, 0)

    assert first.status_code == 200
    first_fragment = first.get_data(as_text=True)
    assert f'id="earlier-progress-{lid}"' in first_fragment
    assert "补录 1/2" in first_fragment
    assert "补录 1/2" in client.get("/").get_data(as_text=True)

    completed = _save_set(client, lid, 2, 8)

    assert completed.status_code == 200
    completed_fragment = completed.get_data(as_text=True)
    assert f'id="earlier-progress-{lid}"' in completed_fragment
    assert "✓ 补录完成 2/2" in completed_fragment
    assert "✓ 补录完成 2/2" in client.get("/").get_data(as_text=True)


def test_save_returns_identity_tagged_inert_fragments_for_driver_and_earlier_set(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", start=30.0)

    driver_data = _set_data(lid, 3, 18, actual_added_weight=30.0)
    driver_data.update(save_sequence="7", focus_sequence="11")
    driver = client.post(
        f"/log/save?lid={lid}&set_number=3", data=driver_data
    )
    assert driver.status_code == 200
    driver_fragment = driver.get_data(as_text=True)
    assert 'data-week-workspace-response' in driver_fragment
    assert 'data-response-role="save"' in driver_fragment
    assert 'data-expected-week="1"' in driver_fragment
    assert f'data-slot-id="{lid}"' in driver_fragment
    assert 'data-save-sequence="7"' in driver_fragment
    assert f'data-focused-slot-id="{lid}"' in driver_fragment
    assert 'data-focus-sequence="11"' in driver_fragment
    assert 'data-fragment-role="persistent"' in driver_fragment
    assert 'data-fragment-role="inspector"' in driver_fragment
    assert 'hx-swap-oob' not in driver_fragment
    assert f'id="save-{lid}-3"' in driver_fragment
    assert 'id="focus-inspector"' in driver_fragment
    assert '"coverage": ["addedWeight", "driverReps"]' in driver_fragment

    earlier_data = _set_data(lid, 1, 10, actual_added_weight=99.0)
    earlier_data.update(save_sequence="8", focus_sequence="12")
    earlier = client.post(
        f"/log/save?lid={lid}&set_number=1", data=earlier_data
    )
    assert earlier.status_code == 200
    earlier_fragment = earlier.get_data(as_text=True)
    assert 'data-save-sequence="8"' in earlier_fragment
    assert 'data-focus-sequence="12"' in earlier_fragment
    assert '"coverage": ["earlierSetReps.1"]' in earlier_fragment
    assert 'hx-swap-oob' not in earlier_fragment
    assert [
        (row["set_number"], row["actual_added_weight"], row["reps"])
        for row in _slot_facts(db_conn, lid)
    ] == [(1, 30.0, 10), (3, 30.0, 18)]


def test_earlier_set_first_stays_unresolved_until_driver_can_be_previewed(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)
    unresolved_id = make_lift(
        name="Still unresolved", mode="linear_t3", sets=3, start=20.0
    )
    assert _save_set(
        client, unresolved_id, 3, 10, actual_added_weight=20.0
    ).status_code == 200
    assert client.post(
        f"/lifts/{unresolved_id}/mode",
        data={"mode": "linear_t2", "weight": "20.0"},
    ).status_code == 302
    state_before = dict(repo.get_training_state(db_conn, lid))

    earlier = _save_set(
        client, lid, 1, 15, actual_added_weight=32.5
    )

    assert earlier.status_code == 200
    earlier_fragment = earlier.get_data(as_text=True)
    assert "已保存" in earlier_fragment
    assert '<input' not in earlier_fragment and '<tr' not in earlier_fragment
    assert '"settlementReady": false' in earlier_fragment
    assert "待有效输入" in earlier_fragment
    assert "Training volume 450 kg" in earlier_fragment
    assert "est1RM" not in earlier_fragment
    assert "Program week 2" not in earlier_fragment
    assert "下一周处方" not in earlier_fragment
    assert dict(repo.get_training_state(db_conn, lid)) == state_before
    assert [
        (
            row["set_number"],
            row["actual_added_weight"],
            row["reps"],
            row["warmup"],
            row["drives_progression"],
        )
        for row in _slot_facts(db_conn, lid)
    ] == [(1, 30.0, 15, 0, 0)]

    driver = _save_set(
        client, lid, 3, 20, actual_added_weight=30.0
    )

    assert driver.status_code == 200
    driver_fragment = driver.get_data(as_text=True)
    assert '"settlementReady": true' in driver_fragment
    assert "待有效输入" not in driver_fragment
    assert "Program week 2" in driver_fragment
    assert "Working Weight 30.0 → 32.5 kg" in driver_fragment
    assert "下一周处方 Working Weight 32.5 kg" in driver_fragment
    assert "Training volume 1050 kg" in driver_fragment
    assert "est1RM" in driver_fragment
    assert dict(repo.get_training_state(db_conn, lid)) == state_before

    incomplete = client.post("/log", data={"expected_week": "1"})
    assert incomplete.status_code == 400
    assert incomplete.get_data(as_text=True) == "unresolved training slots"
    assert repo.get_settings(db_conn)["week"] == 1
    assert dict(repo.get_training_state(db_conn, lid)) == state_before

    settled = client.post(
        "/log",
        data={
            "expected_week": "1",
            "skipped_slot_ids": str(unresolved_id),
        },
    )
    assert settled.status_code == 302
    assert repo.get_settings(db_conn)["week"] == 2
    assert repo.get_training_state(db_conn, lid)["weight"] == 32.5


def test_earlier_set_after_mode_switch_awaits_a_valid_current_driver(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)
    assert _save_set(
        client, lid, 3, 10, actual_added_weight=30.0
    ).status_code == 200
    assert client.post(
        f"/lifts/{lid}/mode",
        data={"mode": "linear_t2", "weight": "30.0"},
    ).status_code == 302
    state_before = dict(repo.get_training_state(db_conn, lid))

    earlier = _save_set(
        client, lid, 1, 8, actual_added_weight=30.0
    )

    assert earlier.status_code == 200
    fragment = earlier.get_data(as_text=True)
    assert '"settlementReady": false' in fragment
    assert "待有效输入" in fragment
    assert "Training volume 540 kg" in fragment
    assert "Program week 2" not in fragment
    assert "下一周处方" not in fragment
    assert dict(repo.get_training_state(db_conn, lid)) == state_before
    assert [
        (
            row["set_number"],
            row["mode"],
            row["drives_progression"],
        )
        for row in _slot_facts(db_conn, lid)
    ] == [
        (1, "linear_t3", 0),
        (3, "linear_t3", 1),
    ]


def test_focus_inspector_marks_first_recorded_week_without_inventing_a_delta(
        client, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    saved = _save_set(client, lid, 3, 18)
    assert saved.status_code == 200
    inspector = saved.get_data(as_text=True)
    assert "Training volume 540 kg" in inspector and inspector.count("首次") == 2
    assert "↗" not in inspector and "↘" not in inspector
    html = client.get("/").get_data(as_text=True)
    assert "Training volume" not in html and "est1RM" not in html


def test_plan_view_omits_comparison_until_driver_set_is_logged(client, make_lift):
    make_lift(name="Curl", start=30.0)
    html = client.get("/").get_data(as_text=True)
    assert "Training volume" not in html and "est1RM" not in html


def test_save_log_response_confirms_the_v1_set_fact(client, make_lift, db_conn):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 1, 15).status_code == 200
    assert _save_set(client, lid, 2, 15).status_code == 200
    rv = _save_set(client, lid, 3, 18)
    assert rv.status_code == 200
    assert "已保存" in rv.get_data(as_text=True)
    facts = _slot_facts(db_conn, lid)
    assert len(facts) == 3
    assert facts[-1]["recorded_volume"] == 1440.0


def test_plan_rep_edit_preserves_existing_actual_weight_and_set_roles(
        client, make_lift):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)
    for set_number, weight, reps, warmup, driver, qualified in (
        (1, 32.5, 8, 1, 0, 0),
        (2, 35.0, 6, 0, 1, 1),
    ):
        response = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(lid),
                "set_number": str(set_number),
                "actual_added_weight": str(weight),
                "reps": str(reps),
                "warmup": str(warmup),
                "drives_progression": str(driver),
                "e1rm_qualified": str(qualified),
            },
        )
        assert response.status_code == 200

    assert _save_set(
        client, lid, 1, 9, actual_added_weight=30.0
    ).status_code == 200
    assert _save_set(
        client, lid, 2, 7, actual_added_weight=30.0
    ).status_code == 200
    facts = [
        row for row in client.get("/training/history").get_json()
        if row["slot_id"] == lid
    ]

    assert [
        (
            row["set_number"],
            row["actual_added_weight"],
            row["reps"],
            row["warmup"],
            row["drives_progression"],
            row["e1rm_qualified"],
        )
        for row in facts
    ] == [
        (1, 32.5, 9, 1, 0, 0),
        (2, 35.0, 7, 0, 1, 1),
    ]


def test_plan_submit_preserves_existing_actual_weight_and_set_roles(
        client, make_lift):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)
    for set_number, weight, reps, warmup, driver, qualified in (
        (1, 32.5, 8, 1, 0, 0),
        (2, 35.0, 6, 0, 1, 1),
    ):
        response = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(lid),
                "set_number": str(set_number),
                "actual_added_weight": str(weight),
                "reps": str(reps),
                "warmup": str(warmup),
                "drives_progression": str(driver),
                "e1rm_qualified": str(qualified),
            },
        )
        assert response.status_code == 200

    for set_number, reps in ((1, 9), (2, 7)):
        response = client.post(
            f"/log/save?lid={lid}&set_number={set_number}",
            data=_set_data(lid, set_number, reps),
        )
        assert response.status_code == 200
    response = client.post("/log", data={"expected_week": "1"})
    assert response.status_code == 302
    facts = [
        row for row in client.get("/training/history").get_json()
        if row["slot_id"] == lid and row["program_week"] == 1
    ]

    assert [
        (
            row["set_number"],
            row["actual_added_weight"],
            row["reps"],
            row["warmup"],
            row["drives_progression"],
            row["e1rm_qualified"],
        )
        for row in facts
    ] == [
        (1, 32.5, 9, 1, 0, 0),
        (2, 35.0, 7, 0, 1, 1),
    ]


def test_focus_inspector_compares_recorded_volume_and_display_e1rm_to_last_week(
        client, make_lift):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)

    for set_number, reps in enumerate((15, 15, 20), start=1):
        assert _save_set(client, lid, set_number, reps, week=1).status_code == 200
    assert client.post("/log", data={"expected_week": "1"}).status_code == 302

    for set_number, reps in enumerate((15, 15, 5), start=1):
        assert _save_set(client, lid, set_number, reps, week=2).status_code == 200
    assert client.post("/log", data={"expected_week": "2"}).status_code == 302

    partial = _save_set(client, lid, 1, 15, week=3)
    assert partial.status_code == 200
    partial_fragment = partial.get_data(as_text=True)
    assert "Training volume 488 kg" in partial_fragment
    assert "↘-57%" in partial_fragment
    assert "est1RM" not in partial_fragment
    assert _save_set(client, lid, 2, 15, week=3).status_code == 200
    response = _save_set(client, lid, 3, 10, week=3)

    assert response.status_code == 200
    fragment = response.get_data(as_text=True)
    assert "Training volume 1300 kg" in fragment and "↗+14%" in fragment
    assert "est1RM 50.33 kg" in fragment and "↗+0.00 kg" in fragment

    page = client.get("/").get_data(as_text=True)
    assert "Training volume" not in page
    assert "est1RM" not in page


def test_sbs_supplement_updates_session_best_but_not_the_driver(
        client, make_lift, db_conn):
    lid = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=3
    )
    with db_conn:
        db_conn.execute(
            "UPDATE sbs_schedule SET intensity = .7, reps = 5, repout = 10 "
            "WHERE kind = 'main' AND week IN (1, 2)"
        )

    assert _save_set(
        client, lid, 3, 0, week=1, actual_added_weight=70.0
    ).status_code == 200
    stronger = _save_set(client, lid, 1, 10, week=1)

    assert stronger.status_code == 200
    first_preview = stronger.get_data(as_text=True)
    assert "Program week 2" in first_preview
    assert "est1RM 93.66 kg" in first_preview
    assert client.post("/log", data={"expected_week": "1"}).status_code == 302
    first_state = repo.get_training_state(db_conn, lid)
    assert first_state["tm"] == pytest.approx(95.0)
    assert first_state["est1rm"] == pytest.approx(93.6631187679488)

    assert _save_set(
        client, lid, 3, 0, week=2, actual_added_weight=65.0
    ).status_code == 200
    weaker = _save_set(client, lid, 1, 1, week=2)

    assert weaker.status_code == 200
    second_preview = weaker.get_data(as_text=True)
    assert "est1RM 65.00 kg" in second_preview
    assert "↘-28.66 kg" in second_preview
    assert client.post("/log", data={"expected_week": "2"}).status_code == 302
    second_state = repo.get_training_state(db_conn, lid)
    # Different actual weight is a recorded fact; the driver's failure adjusts old TM.
    assert second_state["tm"] == pytest.approx(95 * .95)
    assert second_state["est1rm"] == pytest.approx(93.6631187679488)


def test_t3_supplement_drives_shared_peak_but_not_progression(
        client, make_lift, db_conn):
    with db_conn:
        db_conn.execute("UPDATE settings SET t3_target = 8 WHERE id = 1")
    lid = make_lift(
        name="Curl", mode="linear_t3", start=50.0, sets=3, lift_kind="main"
    )

    assert _save_set(
        client, lid, 3, 5, actual_added_weight=50.0
    ).status_code == 200
    stronger = _save_set(client, lid, 1, 10)

    assert stronger.status_code == 200
    assert "est1RM 66.90 kg" in stronger.get_data(as_text=True)
    assert client.post("/log", data={"expected_week": "1"}).status_code == 302
    state = repo.get_training_state(db_conn, lid)
    assert state["weight"] == 50.0
    assert state["est1rm"] == pytest.approx(66.902227691392)

    with db_conn:
        db_conn.execute(
            "UPDATE strength_state SET est1rm = 50, weight = 200 WHERE slot_id = ?",
            (lid,),
        )
        db_conn.execute(
            "UPDATE program_slot SET start_weight = 200 WHERE id = ?", (lid,)
        )
    assert client.post(
        f"/lifts/{lid}/mode", data={"mode": "sbs"}
    ).status_code == 302
    state = repo.get_training_state(db_conn, lid)
    assert state["tm"] == pytest.approx(66.902227691392)
    assert state["est1rm"] == pytest.approx(66.902227691392)

    assert _save_set(
        client, lid, 3, 5, week=2, actual_added_weight=60.0
    ).status_code == 200
    assert client.post("/log", data={"expected_week": "2"}).status_code == 302
    assert repo.get_training_state(db_conn, lid)["est1rm"] > 66.902227691392

    with db_conn:
        db_conn.execute(
            "UPDATE strength_state SET est1rm = 80 WHERE slot_id = ?", (lid,)
        )
    assert client.post(
        f"/lifts/{lid}/mode", data={"mode": "linear_t3"}
    ).status_code == 302
    assert repo.get_training_state(db_conn, lid)["est1rm"] == 80.0

    assert _save_set(
        client, lid, 3, 1, week=3, actual_added_weight=20.0
    ).status_code == 200
    assert client.post("/log", data={"expected_week": "3"}).status_code == 302
    assert repo.get_training_state(db_conn, lid)["est1rm"] == 80.0

    assert client.post(
        f"/lifts/{lid}/mode", data={"mode": "linear_t2"}
    ).status_code == 302
    assert repo.get_training_state(db_conn, lid)["est1rm"] is None


def test_save_log_rejects_blank_without_erasing_the_fact(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 3, 18).status_code == 200
    rv = client.post(
        f"/log/save?lid={lid}&set_number=3",
        data=_set_data(lid, 3, ""),
    )
    assert rv.status_code == 400
    assert [(row["set_number"], row["reps"])
            for row in _slot_facts(db_conn, lid)] == [(3, 18)]


def test_plan_view_uses_the_current_v1_t2_state(client, make_lift, db_conn):
    lid = make_lift(name="Rows", mode="linear_t2", start=50.0)
    db_conn.execute(
        "UPDATE strength_state SET weight = 55, target = 6, streak = 2 "
        "WHERE slot_id = ?", (lid,)
    )
    db_conn.commit()
    html = client.get("/").get_data(as_text=True)
    assert "55.0" in html and "x 6 x 3" in html
    assert "streak 2" in html


def test_plan_view_renders_bodyweight_added_plus_working_weight(client, make_lift, db_conn):
    """Bodyweight lift renders '+added (working)' meta format (Task 11).

    Chin-ups t2, start=0, bodyweight=75, pct=1.0 -> working_weight = 0 + 75*1.0 = 75.
    Meta line shows '+0 (75.0) kg' — added is the user's load, working_weight is the
    parenthetical. Non-bodyweight lifts keep the plain '{{ weight }} kg' format.
    """
    repo.update_settings(db_conn, bodyweight=75.0)
    make_lift(name="Chin-ups", load_model="bodyweight", mode="linear_t2",
              day=1, sort_order=1, start=0.0, bodyweight_pct=1.0)
    body = client.get("/").get_data(as_text=True)
    assert "+0" in body              # added load shown with + prefix
    assert "(75" in body             # working_weight shown in parens


def test_export_week_plate_loading_structure(client, make_lift):
    """装片清单只保留加载动作所需的重量、方案和 mode tag。"""
    make_lift(name="Squat", mode="sbs", sets=5, max=100.0, start=None, lift_kind="main")
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1"' in html
    assert 'class="wt"' in html and "kg" in html      # 大数字 + 单位
    assert "rep-out" in html                            # sbs 方案行
    assert 'class="tag sbs"' in html                    # mode tag accent
    assert "容量" not in html and "est 1RM" not in html
    assert "最佳 1RM" not in html and "streak" not in html


def test_export_week_bodyweight_shows_added_only(client, make_lift, db_conn):
    """bodyweight 动作只显示 +added kg，不显示工作重量括号。"""
    repo.update_settings(db_conn, bodyweight=75.0)
    make_lift(name="Chin-up", load_model="bodyweight", mode="linear_t2",
              start=15.0, bodyweight_pct=1.0)
    html = client.get("/export/week.html").get_data(as_text=True)
    assert "+15" in html          # 加重
    assert "(90." not in html     # 工作重量括号已砍 (15 + 75*1.0 = 90.0); dot avoids CSS rotate(90deg)


@pytest.mark.parametrize(
    "load_model, mode, set_number, actual_weight, warmup, expected_weight",
    [
        ("barbell", "linear_t3", 3, 42.5, False, "42.5"),
        ("barbell", "linear_t3", 1, 42.5, False, "42.5"),
        ("barbell", "linear_t3", 4, 42.5, False, "42.5"),
        ("barbell", "linear_t3", 1, 0, False, "0.0"),
        ("barbell", "linear_t3", 1, 10, True, "30.0"),
        ("bodyweight", "linear_t2", 1, 7.5, False, "+7.5"),
        ("pure_bodyweight", "none", 3, 0, False, None),
    ],
)
def test_export_uses_confirmed_work_weight_without_changing_completion(
        client, make_lift, load_model, mode, set_number, actual_weight, warmup,
        expected_weight):
    lid = make_lift(name="Logged", load_model=load_model, mode=mode,
                    start=0 if mode == "none" else 30,
                    bodyweight_pct=0.0 if load_model == "barbell" else 1.0)
    original_export = client.get("/export/week.html").get_data(as_text=True)
    saved = client.post("/training/sets/full", data={
        "expected_week": "1", "slot_id": lid, "set_number": set_number,
        "actual_added_weight": actual_weight, "reps": 8,
        "warmup": int(warmup), "drives_progression": int(set_number == 3),
    })
    assert saved.status_code == 200
    html = client.get("/export/week.html").get_data(as_text=True)
    if expected_weight is None:
        assert '<span class="wt">' not in html
    else:
        assert f'<span class="wt">{expected_weight}<span class="unit">kg</span>' in html
    done = set_number == 3
    assert ('class="name done">✓ Logged' in html) == done
    assert f'class="st-{"full" if done else "empty"}"' in html
    assert "<script" not in html
    assert 'class="name done"' not in original_export


def test_export_week_day_tristate_and_default_open(client, make_lift, db_conn):
    """day 三态：全空 day1 + 部分填 day2 → day2 标 ◐ 且默认展开（最小非全填是 day1，但 day1 全空也非全填）。

    构造：day1 一个动作不填（全空）；day2 两动作填一个（部分填）。最小非全填 = day1 → day1 open。
    day2 st-part 带 ◐。"""
    make_lift(name="A", day=1, sort_order=0, start=30.0)
    lid_b1 = make_lift(name="B1", day=2, sort_order=0, start=30.0)
    make_lift(name="B2", day=2, sort_order=1, start=30.0)
    assert _save_set(client, lid_b1, 3, 12).status_code == 200
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1" class="st-empty" open>' in html   # 最小非全填默认展开
    assert '<details data-day="2" class="st-part">' in html         # 部分填折叠
    assert "◐" in html                                               # 欠账标记


def test_export_week_card_done_mark(client, make_lift, db_conn):
    """卡片级进度：已填末组的动作名字带 ✓ + done class（绿），未填无标记。

    健身房扫一眼即可见 day 内哪些动作练过、哪些待练 — 不靠回忆。"""
    lid_done = make_lift(name="Squat", mode="sbs", sets=5, max=100.0,
                         start=None, lift_kind="main", sort_order=0)
    make_lift(name="Bench", mode="sbs", sets=4, max=80.0,
              start=None, lift_kind="main", sort_order=1)
    assert _save_set(client, lid_done, 5, 10).status_code == 200
    html = client.get("/export/week.html").get_data(as_text=True)
    assert 'class="name done">✓ Squat' in html    # 已填：✓ + done class
    assert 'class="name">Bench' in html            # 未填：无 done、无 ✓
