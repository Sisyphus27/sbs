import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from webapp import backup, repo
from webapp.services.training import training_history


def _set_data(slot_id, set_number, reps, *, week=1, actual_added_weight=None):
    data = {
        "expected_week": str(week),
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


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


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


def test_week_ledger_defaults_to_weight_and_driver_then_discloses_earlier_sets(
        client, make_lift):
    lid = make_lift(name="Curl", sets=4, start=30.0)

    html = client.get("/").get_data(as_text=True)
    row = html[html.index(f'id="ledger-row-{lid}"'):]
    row = row[:row.index("</tr>")]
    disclosure_marker = f'<details id="earlier-sets-{lid}"'
    default_controls, marker, earlier_sets = row.partition(disclosure_marker)

    assert marker
    assert f'name="actual_added_weight_{lid}"' in default_controls
    assert f'name="set_{lid}_4"' in default_controls
    assert "补录前 3 组" in earlier_sets
    assert all(
        f'name="set_{lid}_{set_number}"' in earlier_sets
        for set_number in (1, 2, 3)
    )
    assert f'name="set_{lid}_4"' not in earlier_sets


def test_week_ledger_saves_weight_and_reps_for_driver_and_earlier_sets(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", mode="linear_t3", sets=3, start=30.0)

    earlier = _save_set(
        client, lid, 1, 8, actual_added_weight=32.5
    )
    driver = _save_set(
        client, lid, 3, 0, actual_added_weight=35.0
    )

    assert earlier.status_code == 200
    assert driver.status_code == 200
    assert [
        (
            row["set_number"],
            row["actual_added_weight"],
            row["reps"],
            row["drives_progression"],
        )
        for row in _slot_facts(db_conn, lid)
    ] == [
        (1, 32.5, 8, 0),
        (3, 35.0, 0, 1),
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
    assert "Planned Working 75.0 kg" in weighted_row
    assert (
        f'type="hidden" name="actual_added_weight_{pure}" value="0"'
        in pure_row
    )
    assert "Actual Added 0 kg" in pure_row
    assert "Planned Working 75.0 kg" in pure_row

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
    assert 'hx-swap-oob="outerHTML"' in weighted_fragment
    assert "Actual Working 不可用" in weighted_fragment
    assert "Actual Working 不可用" in weighted_row

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
    assert "Actual Working 90.0 kg" in recorded_row

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
    assert f'id="ledger-status-{lid}"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert "已补录 · 0 次失败" in fragment
    assert f'id="ledger-row-{lid}"' in page
    assert 'class="week-ledger-row is-logged is-zero"' in page
    assert "已补录 · 0 次失败" in page


def test_plan_renders_duplicate_names_with_distinct_state(client, make_lift):
    """Same name on two days must render each day's own weight (id-keyed, not clobbered)."""
    make_lift(name="Face Pull", day=2, start=30.0)
    make_lift(name="Face Pull", day=4, start=45.0)
    html = client.get("/").get_data(as_text=True)
    assert html.count("Face Pull") == 2
    assert "30.0 kg" in html and "45.0 kg" in html   # each day keeps its own weight


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
    rv = client.post("/log", data=_set_data(lid, 5, 13))
    assert rv.status_code == 302
    assert repo.get_settings(db_conn)["week"] == 2


def test_plan_submit_rejects_stale_expected_week(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    data = _set_data(lid, 5, 13)

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
    both_checked_week = threading.Barrier(2)

    def synchronized_snapshot(*args, **kwargs):
        both_checked_week.wait(timeout=5)
        return "unused.db.bak"

    monkeypatch.setattr(backup, "snapshot", synchronized_snapshot)

    def submit():
        with app.test_client() as thread_client:
            return thread_client.post(
                "/log", data=_set_data(lid, 5, 13)
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _n: submit(), range(2)))

    assert sorted(statuses) == [302, 409]
    assert repo.get_settings(db_conn)["week"] == 2
    assert len(_slot_facts(db_conn, lid)) == 1


def test_plan_submit_requires_expected_week(client):
    assert client.post("/log", data={}).status_code == 400


def test_plan_submit_snapshot_contains_pre_advance_state(client, app, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    rv = client.post(
        "/log", data=_set_data(lid, 3, 18)
    )

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
    html = client.get("/").get_data(as_text=True)
    assert "data-disable-submit" in html


def test_plan_form_carries_expected_program_week(client):
    html = client.get("/").get_data(as_text=True)
    assert 'type="hidden" name="expected_week" value="1"' in html


def test_autosave_includes_expected_program_week(client, make_lift):
    make_lift(name="Curl", start=30.0)
    html = client.get("/").get_data(as_text=True)
    assert 'hx-include="[name=\'expected_week\'],' in html


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
    repo.save_lift_state(db_conn, lid, mode="sbs", tm=100.0, weight=None,
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
    assert client.post("/log", data={"expected_week": "1"}).status_code == 302

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


def test_plan_keeps_queued_autosave_sources_stable_while_refreshing_comparison(
        client, make_lift):
    lid = make_lift(name="Curl", start=30.0)

    html = client.get("/").get_data(as_text=True)

    assert html.count('hx-sync="closest tr:queue all"') == 4
    assert 'hx-sync="this:queue all"' not in html
    assert html.count(f'hx-target="#save-{lid}-3"') == 2
    assert html.count(f'hx-target="#save-{lid}-1"') == 1
    assert html.count(f'hx-target="#save-{lid}-2"') == 1
    assert 'hx-target="closest .lift-row"' not in html

    fragment = _save_set(client, lid, 1, 15).get_data(as_text=True)
    assert fragment.count('hx-swap-oob="outerHTML"') == 2
    assert f'id="save-{lid}-1"' in fragment
    assert f'id="ledger-status-{lid}"' in fragment
    assert "<input" not in fragment and "<tr" not in fragment
    assert f'id="comparison-{lid}"' in fragment


def test_plan_view_marks_first_recorded_week_without_inventing_a_delta(
        client, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 3, 18).status_code == 200
    html = client.get("/").get_data(as_text=True)
    assert "容量 540kg" in html and html.count("首次") == 2
    assert "↗" not in html and "↘" not in html


def test_plan_view_omits_comparison_until_driver_set_is_logged(client, make_lift):
    make_lift(name="Curl", start=30.0)
    html = client.get("/").get_data(as_text=True)
    assert "容量" not in html and "est 1RM" not in html


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

    response = client.post(
        "/log",
        data={
            "expected_week": "1",
            f"set_{lid}_1": "9",
            f"set_{lid}_2": "7",
        },
    )
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


def test_plan_and_autosave_compare_recorded_volume_and_display_e1rm_to_last_week(
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
    assert "容量 488kg" in partial_fragment and "↘-57%" in partial_fragment
    assert "est 1RM" not in partial_fragment
    assert _save_set(client, lid, 2, 15, week=3).status_code == 200
    response = _save_set(client, lid, 3, 10, week=3)

    assert response.status_code == 200
    fragment = response.get_data(as_text=True)
    assert "容量 1300kg" in fragment and "↗+14%" in fragment
    assert "est 1RM 43.49kg" in fragment and "↗+6.03kg" in fragment

    page = client.get("/").get_data(as_text=True)
    assert "容量 1300kg" in page and "↗+14%" in page
    assert "est 1RM 43.49kg" in page and "↗+6.03kg" in page


def test_save_log_rejects_blank_without_erasing_the_fact(
        client, make_lift, db_conn):
    lid = make_lift(name="Curl", start=30.0)
    assert _save_set(client, lid, 3, 18).status_code == 200
    rv = client.post(
        f"/log/save?lid={lid}&set_number=3",
        data={"expected_week": "1", f"set_{lid}_3": ""},
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
