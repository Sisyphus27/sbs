import pytest

from webapp import repo


def _source_state(conn, slot_id):
    return {
        "week": conn.execute(
            "SELECT week FROM settings WHERE id = 1"
        ).fetchone()["week"],
        "state": tuple(
            conn.execute(
                "SELECT mode, tm, weight, target, streak, est1rm "
                "FROM strength_state WHERE slot_id = ?",
                (slot_id,),
            ).fetchone()
        ),
        "sessions": conn.execute(
            "SELECT COUNT(*) FROM training_session"
        ).fetchone()[0],
        "sets": conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0],
        "events": conn.execute(
            "SELECT COUNT(*) FROM progression_event"
        ).fetchone()[0],
    }


def _save_set(client, slot_id, set_number, reps, *, week, weight):
    return client.post(
        f"/log/save?lid={slot_id}&set_number={set_number}",
        data={
            "expected_week": str(week),
            f"actual_added_weight_{slot_id}": str(weight),
            f"set_{slot_id}_{set_number}": str(reps),
        },
    )


def test_sbs_preview_names_tm_and_next_working_weight_without_writing_source(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=5
    )
    before = _source_state(db_conn, slot_id)

    response = client.post(
        f"/log/preview?lid={slot_id}",
        data={
            "expected_week": "1",
            f"actual_added_weight_{slot_id}": "70",
            f"set_{slot_id}_5": "30",
        },
    )

    assert response.status_code == 200
    inspector = response.get_data(as_text=True)
    assert "Squat" in inspector
    assert "Program week 2" in inspector
    assert "Training Max" in inspector
    assert "下一周 Working Weight" in inspector
    assert _source_state(db_conn, slot_id) == before


@pytest.mark.parametrize(
    ("lift", "actual_added_weight", "reps"),
    (
        ({"name": "Bench", "mode": "sbs", "max": 100.0,
          "lift_kind": "main", "sets": 5}, 70.0, 30),
        ({"name": "Row", "mode": "linear_t2", "start": 30.0,
          "sets": 3}, 30.0, 8),
        ({"name": "Curl", "mode": "linear_t3", "start": 30.0,
          "sets": 3}, 30.0, 15),
        ({"name": "Push-up", "mode": "none",
          "load_model": "pure_bodyweight", "bodyweight_pct": 1.0,
          "start": 0.0, "sets": 3}, 0.0, 10),
    ),
)
def test_preview_matches_canonical_finalize_for_each_progression_mode(
        client, make_lift, db_conn, lift, actual_added_weight, reps):
    slot_id = make_lift(**lift)
    current_plan = client.get("/training/plan").get_json()
    current_slot = next(
        item for item in current_plan["slots"] if item["slot_id"] == slot_id
    )
    set_number = current_slot["planned_sets"]
    data = {
        "expected_week": "1",
        f"actual_added_weight_{slot_id}": str(actual_added_weight),
        f"set_{slot_id}_{set_number}": str(reps),
    }
    before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone())

    preview = client.post(f"/log/preview?lid={slot_id}", data=data)
    assert preview.status_code == 200
    preview_html = preview.get_data(as_text=True)

    saved = client.post(
        f"/log/save?lid={slot_id}&set_number={set_number}", data=data
    )
    assert saved.status_code == 200
    assert client.post(
        "/training/finalize", data={"expected_week": "1"}
    ).status_code == 200

    after = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone())
    next_plan = client.get("/training/plan").get_json()
    next_slot = next(
        item for item in next_plan["slots"] if item["slot_id"] == slot_id
    )

    if lift["mode"] == "sbs":
        assert f"Training Max {before['tm']} → {after['tm']}" in preview_html
        assert (
            f"下一周 Working Weight {next_slot['planned_working_weight']} kg"
            in preview_html
        )
    elif lift["mode"] == "linear_t2":
        assert (
            f"Working Weight {before['weight']} → {after['weight']} kg"
            in preview_html
        )
        assert f"目标 {before['target']} → {after['target']}" in preview_html
        assert f"streak {before['streak']} → {after['streak']}" in preview_html
        assert (
            f"下一周处方 Working Weight {next_slot['planned_working_weight']} kg"
            in preview_html
        )
    elif lift["mode"] == "linear_t3":
        assert (
            f"Working Weight {before['weight']} → {after['weight']} kg"
            in preview_html
        )
        assert (
            f"下一周处方 Working Weight {next_slot['planned_working_weight']} kg"
            in preview_html
        )
        assert f"目标 {next_slot['planned_target']} 次" in preview_html
    else:
        assert "record-only：无自动 Progression" in preview_html
        assert after["weight"] == before["weight"]


def test_performance_comparison_appears_only_in_the_focused_inspector(
        client, make_lift):
    slot_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    for set_number, reps in enumerate((15, 15, 20), start=1):
        assert _save_set(
            client, slot_id, set_number, reps, week=1, weight=30.0
        ).status_code == 200
    assert client.post(
        "/training/finalize", data={"expected_week": "1"}
    ).status_code == 200

    assert _save_set(
        client, slot_id, 1, 15, week=2, weight=32.5
    ).status_code == 200
    assert _save_set(
        client, slot_id, 2, 15, week=2, weight=32.5
    ).status_code == 200

    page = client.get("/").get_data(as_text=True)
    ledger = page.split('<table class="week-ledger">', 1)[1].split(
        "</table>", 1
    )[0]
    assert "容量" not in ledger
    assert "est 1RM" not in ledger

    preview = client.post(
        f"/log/preview?lid={slot_id}",
        data={
            "expected_week": "2",
            f"actual_added_weight_{slot_id}": "32.5",
            f"set_{slot_id}_3": "15",
        },
    )
    assert preview.status_code == 200
    inspector = preview.get_data(as_text=True)
    assert "本次表现" in inspector
    assert "Training volume" in inspector
    assert "est1RM" in inspector


def test_skip_preview_is_read_only_and_does_not_implement_settlement_state(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Press", mode="linear_t2", start=30.0, sets=3
    )
    before = _source_state(db_conn, slot_id)

    response = client.post(
        f"/log/preview?lid={slot_id}",
        data={"expected_week": "1", "intent": "skip"},
    )

    assert response.status_code == 200
    preview = response.get_data(as_text=True)
    assert "本周跳过" in preview
    assert "不生成 Training Fact" in preview
    assert "Progression 不变" in preview
    assert _source_state(db_conn, slot_id) == before


def test_week_workspace_has_one_input_free_inspector_refreshed_by_driver_save(
        client, make_lift):
    first_id = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=5
    )
    make_lift(name="Curl", mode="linear_t3", start=20.0, sets=3, day=2)

    page = client.get("/").get_data(as_text=True)
    assert page.count('id="focus-inspector"') == 1
    assert page.count('hx-target="#focus-inspector"') == 2
    inspector = page.split('id="focus-inspector"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "actual_added_weight" not in inspector
    assert "set_" not in inspector

    saved = _save_set(
        client, first_id, 5, 30, week=1, weight=70.0
    )
    assert saved.status_code == 200
    fragment = saved.get_data(as_text=True)
    assert 'id="focus-inspector"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert "Squat" in fragment
    assert "Training Max" in fragment


def test_bodyweight_preview_distinguishes_added_from_working_weight_without_fallback(
        client, make_lift, db_conn):
    repo.update_settings(db_conn, bodyweight=80.0)
    slot_id = make_lift(
        name="Dip",
        load_model="bodyweight",
        mode="linear_t2",
        bodyweight_pct=1.0,
        start=10.0,
        sets=3,
    )
    before = _source_state(db_conn, slot_id)

    response = client.post(
        f"/log/preview?lid={slot_id}",
        data={
            "expected_week": "1",
            f"actual_added_weight_{slot_id}": "10",
            f"set_{slot_id}_3": "8",
        },
    )

    assert response.status_code == 200
    preview = response.get_data(as_text=True)
    assert "Added weight 10.0 → 10.0 kg" in preview
    assert "下一周处方 Working Weight 90.0 kg" in preview
    performance = preview.split("本次表现", 1)[1]
    assert "Training volume" not in performance
    assert "est1RM" not in performance
    assert _source_state(db_conn, slot_id) == before


@pytest.mark.parametrize(
    ("expected_week", "reps", "status", "message"),
    ((1, -1, 400, "reps must be nonnegative"), (2, 8, 409, "stale week")),
)
def test_preview_error_keeps_the_lift_unresolved_and_source_unchanged(
        client, make_lift, db_conn, expected_week, reps, status, message):
    slot_id = make_lift(
        name="Row", mode="linear_t2", start=30.0, sets=3
    )
    before = _source_state(db_conn, slot_id)

    response = client.post(
        f"/log/save?lid={slot_id}&set_number=3",
        data={
            "expected_week": str(expected_week),
            f"actual_added_weight_{slot_id}": "30",
            f"set_{slot_id}_3": str(reps),
        },
    )

    assert response.status_code == status
    assert message in response.get_data(as_text=True)
    assert _source_state(db_conn, slot_id) == before
    assert "待处理" in client.get("/").get_data(as_text=True)


def test_focusing_an_unlogged_lift_selects_context_without_inventing_a_preview(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=5
    )
    before = _source_state(db_conn, slot_id)

    response = client.post(
        f"/log/preview?lid={slot_id}",
        data={"expected_week": "1", "intent": "focus"},
    )

    assert response.status_code == 200
    inspector = response.get_data(as_text=True)
    assert "Squat" in inspector
    assert "待有效输入" in inspector
    assert "Training Max" not in inspector
    assert _source_state(db_conn, slot_id) == before


def test_preview_preserves_existing_set_roles_when_matching_formal_finalize(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    for set_number, reps, warmup, driver in (
        (2, 15, 0, 1),
        (3, 5, 1, 0),
    ):
        response = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": str(set_number),
                "actual_added_weight": "30",
                "reps": str(reps),
                "warmup": str(warmup),
                "drives_progression": str(driver),
                "e1rm_qualified": "0",
            },
        )
        assert response.status_code == 200

    saved = _save_set(
        client, slot_id, 3, 5, week=1, weight=30.0
    )
    assert saved.status_code == 200
    preview = saved.get_data(as_text=True)

    assert client.post(
        "/training/finalize", data={"expected_week": "1"}
    ).status_code == 200
    finalized = repo.get_training_state(db_conn, slot_id)
    assert finalized["weight"] == 32.5
    assert "Working Weight 30.0 → 32.5 kg" in preview


def test_earlier_set_edit_refreshes_the_focused_performance_volume(
        client, make_lift):
    slot_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    assert _save_set(
        client, slot_id, 3, 15, week=1, weight=30.0
    ).status_code == 200

    earlier = _save_set(
        client, slot_id, 1, 10, week=1, weight=30.0
    )

    assert earlier.status_code == 200
    fragment = earlier.get_data(as_text=True)
    assert 'id="focus-inspector"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert "Training volume 750 kg" in fragment
    assert "est1RM" in fragment


def test_est1rm_comparison_ignores_history_without_a_confirmed_prescription(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    assert _save_set(
        client, slot_id, 3, 15, week=1, weight=30.0
    ).status_code == 200
    with db_conn:
        db_conn.execute(
            "UPDATE progression_event SET mode = NULL WHERE slot_id = ?",
            (slot_id,),
        )
        repo.set_week(db_conn, 2)

    preview = client.post(
        f"/log/preview?lid={slot_id}",
        data={
            "expected_week": "2",
            f"actual_added_weight_{slot_id}": "30",
            f"set_{slot_id}_3": "15",
        },
    )

    assert preview.status_code == 200
    inspector = preview.get_data(as_text=True)
    assert "Training volume" in inspector
    est1rm_line = inspector.split("est1RM", 1)[1].split("</p>", 1)[0]
    assert "首次" in est1rm_line
    assert "↗" not in est1rm_line and "↘" not in est1rm_line


def test_canonical_preview_failure_is_explicit_and_does_not_save_the_candidate(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=5
    )
    with db_conn:
        db_conn.execute(
            "DELETE FROM sbs_schedule WHERE kind = 'main' AND week = 2"
        )
    before = _source_state(db_conn, slot_id)

    response = _save_set(
        client, slot_id, 5, 30, week=1, weight=70.0
    )

    assert response.status_code == 500
    assert response.get_data(as_text=True) == "preview failed"
    assert _source_state(db_conn, slot_id) == before
    assert "待处理" in client.get("/").get_data(as_text=True)
