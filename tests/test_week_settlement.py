"""Public Web contracts for complete and atomic Program-week settlement."""


def _save_driver(client, slot_id, *, set_number, reps, weight):
    return client.post(
        f"/log/save?lid={slot_id}&set_number={set_number}",
        data={
            "expected_week": "1",
            f"actual_added_weight_{slot_id}": str(weight),
            f"set_{slot_id}_{set_number}": str(reps),
        },
    )


def test_finalize_rejects_an_unresolved_planned_lift(
        client, make_lift, db_conn):
    logged_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    unresolved_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3, day=2
    )
    assert _save_driver(
        client, logged_id, set_number=3, reps=15, weight=30.0
    ).status_code == 200
    unresolved_before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (unresolved_id,)
    ).fetchone())

    response = client.post(
        "/training/finalize", data={"expected_week": "1"}
    )

    assert response.status_code == 400
    assert "unresolved" in response.get_data(as_text=True)
    assert db_conn.execute(
        "SELECT week FROM settings WHERE id = 1"
    ).fetchone()[0] == 1
    assert dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (unresolved_id,)
    ).fetchone()) == unresolved_before


def test_explicit_skip_advances_once_without_fact_session_or_progression(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3
    )
    state_before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone())
    request_data = {
        "expected_week": "1",
        "skipped_slot_ids": str(slot_id),
    }

    response = client.post("/training/finalize", data=request_data)

    assert response.status_code == 200
    assert response.get_json() == {"new_week": 2}
    assert db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 0
    assert db_conn.execute(
        "SELECT COUNT(*) FROM training_session"
    ).fetchone()[0] == 0
    assert dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone()) == state_before

    repeated = client.post("/training/finalize", data=request_data)
    assert repeated.status_code == 409
    assert db_conn.execute(
        "SELECT week FROM settings WHERE id = 1"
    ).fetchone()[0] == 2


def test_week_workspace_exposes_logged_zero_and_unresolved_settlement_controls(
        client, make_lift):
    failed_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    unresolved_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3, day=2
    )
    assert _save_driver(
        client, failed_id, set_number=3, reps=0, weight=30.0
    ).status_code == 200

    page = client.get("/").get_data(as_text=True)

    assert 'data-week-settlement' in page
    assert 'data-handled-count>1<' in page
    assert 'data-pending-count>1<' in page
    assert 'data-next-unresolved' in page
    assert 'id="settlement-review"' in page
    review_button = page.split('id="settlement-review"', 1)[1].split(
        ">", 1
    )[0]
    assert "disabled" in review_button
    assert f'id="ledger-status-{failed_id}"' in page
    assert "已补录 · 0 次失败" in page
    unresolved_row = page.split(
        f'id="ledger-row-{unresolved_id}"', 1
    )[1].split("</tr>", 1)[0]
    assert 'data-settlement-state="unresolved"' in unresolved_row
    assert 'data-skip-toggle' in unresolved_row
    assert f'name="skipped_slot_ids" value="{unresolved_id}"' in unresolved_row
    assert "本周跳过" in unresolved_row


def test_final_review_is_read_only_and_confirm_applies_logged_and_skipped(
        client, make_lift, db_conn):
    failed_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    skipped_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3, day=2
    )
    assert _save_driver(
        client, failed_id, set_number=3, reps=0, weight=30.0
    ).status_code == 200
    skipped_before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (skipped_id,)
    ).fetchone())
    request_data = {
        "expected_week": "1",
        "skipped_slot_ids": str(skipped_id),
    }

    review = client.post("/log/review", data=request_data)

    assert review.status_code == 200
    html = review.get_data(as_text=True)
    assert "最终复核" in html
    assert "已补录 1" in html
    assert "本周跳过 1" in html
    assert "0 次失败 1" in html
    assert "Curl" in html and "Row" in html
    assert "失败 Training Fact" in html
    assert "Progression 不变" in html
    assert 'type="number"' not in html
    assert f'name="skipped_slot_ids" value="{skipped_id}"' in html
    assert "确认并进入 Week 2" in html
    assert db_conn.execute(
        "SELECT week FROM settings WHERE id = 1"
    ).fetchone()[0] == 1

    confirmed = client.post("/log", data=request_data)
    assert confirmed.status_code == 302
    assert db_conn.execute(
        "SELECT week FROM settings WHERE id = 1"
    ).fetchone()[0] == 2
    assert dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (skipped_id,)
    ).fetchone()) == skipped_before
    next_week_row = client.get("/").get_data(as_text=True).split(
        f'id="ledger-row-{skipped_id}"', 1
    )[1].split("</tr>", 1)[0]
    assert 'data-settlement-state="unresolved"' in next_week_row
    assert "待处理" in next_week_row


def test_skipped_lift_keeps_state_even_with_a_qualified_non_driver_fact(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Squat", mode="sbs", max=100.0, lift_kind="main", sets=5
    )
    partial = client.post(
        "/training/sets/full",
        data={
            "expected_week": "1",
            "slot_id": str(slot_id),
            "set_number": "1",
            "actual_added_weight": "70",
            "reps": "5",
            "warmup": "0",
            "drives_progression": "0",
            "e1rm_qualified": "1",
        },
    )
    assert partial.status_code == 200
    state_before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone())

    response = client.post(
        "/training/finalize",
        data={"expected_week": "1", "skipped_slot_ids": str(slot_id)},
    )

    assert response.status_code == 200
    assert db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0] == 1
    assert dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone()) == state_before


def test_review_rejects_duplicate_unknown_invisible_and_logged_skips(
        client, make_lift, db_conn):
    logged_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    unresolved_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3, day=2
    )
    invisible_id = make_lift(
        name="Press", mode="linear_t3", start=50.0, sets=3, day=3
    )
    assert _save_driver(
        client, logged_id, set_number=3, reps=15, weight=30.0
    ).status_code == 200
    with db_conn:
        db_conn.execute("UPDATE settings SET days_per_week = 2 WHERE id = 1")

    cases = (
        ([unresolved_id, unresolved_id], "duplicate skipped training slot"),
        ([999999], "unknown skipped training slot"),
        ([invisible_id], "unknown skipped training slot"),
        ([logged_id, unresolved_id], "skipped training slot is already logged"),
    )
    for skipped_ids, message in cases:
        response = client.post(
            "/log/review",
            data={
                "expected_week": "1",
                "skipped_slot_ids": [str(slot_id) for slot_id in skipped_ids],
            },
        )
        assert response.status_code == 400
        assert response.get_data(as_text=True) == message
        assert db_conn.execute(
            "SELECT week FROM settings WHERE id = 1"
        ).fetchone()[0] == 1


def test_workspace_logged_state_uses_the_confirmed_progression_driver(
        client, make_lift):
    earlier_driver_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    final_non_driver_id = make_lift(
        name="Row", mode="linear_t3", start=40.0, sets=3, day=2
    )
    for slot_id, set_number, weight, reps, driver in (
        (earlier_driver_id, 1, 30.0, 0, 1),
        (earlier_driver_id, 3, 30.0, 10, 0),
        (final_non_driver_id, 3, 40.0, 10, 0),
    ):
        response = client.post(
            "/training/sets/full",
            data={
                "expected_week": "1",
                "slot_id": str(slot_id),
                "set_number": str(set_number),
                "actual_added_weight": str(weight),
                "reps": str(reps),
                "warmup": "0",
                "drives_progression": str(driver),
                "e1rm_qualified": "0",
            },
        )
        assert response.status_code == 200

    page = client.get("/").get_data(as_text=True)
    earlier_driver_row = page.split(
        f'id="ledger-row-{earlier_driver_id}"', 1
    )[1].split("</tr>", 1)[0]
    final_non_driver_row = page.split(
        f'id="ledger-row-{final_non_driver_id}"', 1
    )[1].split("</tr>", 1)[0]

    assert 'data-settlement-state="logged"' in earlier_driver_row
    assert "已补录 · 0 次失败" in earlier_driver_row
    assert 'data-settlement-state="unresolved"' in final_non_driver_row
    assert "待处理" in final_non_driver_row
    review = client.post(
        "/log/review",
        data={
            "expected_week": "1",
            "skipped_slot_ids": str(final_non_driver_id),
        },
    )
    assert review.status_code == 200


def test_workspace_reopens_driver_saved_before_a_training_mode_switch(
        client, make_lift, db_conn):
    slot_id = make_lift(
        name="Curl", mode="linear_t3", start=30.0, sets=3
    )
    assert _save_driver(
        client, slot_id, set_number=3, reps=10, weight=30.0
    ).status_code == 200
    assert client.post(
        f"/lifts/{slot_id}/mode",
        data={"mode": "linear_t2", "weight": "30.0"},
    ).status_code == 302

    page = client.get("/").get_data(as_text=True)
    row = page.split(f'id="ledger-row-{slot_id}"', 1)[1].split("</tr>", 1)[0]

    assert 'data-settlement-state="unresolved"' in row
    assert "待处理" in row

    state_before = dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone())
    fact_count = db_conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0]
    request_data = {
        "expected_week": "1",
        "skipped_slot_ids": str(slot_id),
    }

    assert client.post("/log/review", data=request_data).status_code == 200
    assert client.post("/log", data=request_data).status_code == 302
    assert db_conn.execute(
        "SELECT week FROM settings WHERE id = 1"
    ).fetchone()[0] == 2
    assert dict(db_conn.execute(
        "SELECT * FROM strength_state WHERE slot_id = ?", (slot_id,)
    ).fetchone()) == state_before
    assert db_conn.execute(
        "SELECT COUNT(*) FROM set_log"
    ).fetchone()[0] == fact_count
