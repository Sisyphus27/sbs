from webapp.app import create_app


def test_rendered_pure_bodyweight_creation_can_save_record_only_fact(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = create_app(
        db_path=db_path,
        backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    client = app.test_client()

    lift_page = client.get("/lifts")
    assert lift_page.status_code == 200
    assert 'hx-post="/lifts/new"' in lift_page.get_data(as_text=True)
    assert '<option value="pure_bodyweight">pure_bodyweight</option>' in (
        lift_page.get_data(as_text=True)
    )
    assert '"pure_bodyweight": ["none"]' in lift_page.get_data(as_text=True)

    created = client.post(
        "/lifts/new",
        data={
            "name": "Pull-up",
            "load_model": "pure_bodyweight",
            "mode": "none",
            "day": "1",
            "sets": "3",
            "bodyweight_pct": "",
        },
    )
    assert created.status_code == 200
    created_html = created.get_data(as_text=True)
    assert "Pull-up" in created_html
    assert "pure_bodyweight" in created_html
    assert "none" in created_html

    plan = client.get("/training/plan").get_json()
    slot = next(item for item in plan["slots"] if item["name"] == "Pull-up")
    assert slot["planned_added_weight"] == 0.0
    assert "Pull-up" in client.get("/").get_data(as_text=True)

    slot_id = slot["slot_id"]
    set_number = slot["planned_sets"]
    saved = client.post(
        f"/log/save?lid={slot_id}&set_number={set_number}",
        data={
            "expected_week": "1",
            f"actual_added_weight_{slot_id}": "0",
            f"set_{slot_id}_{set_number}": "10",
        },
    )

    assert saved.status_code == 200
    saved_html = saved.get_data(as_text=True)
    inspector = saved_html.split('<section id="focus-inspector"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "record-only：无自动 Progression" in inspector
    assert "Working Weight" not in inspector
    assert "→" not in inspector
    facts = [
        fact
        for fact in client.get("/training/history").get_json()
        if fact["slot_id"] == slot_id
    ]
    assert [
        (
            fact["set_number"],
            fact["actual_added_weight"],
            fact["reps"],
            fact["drives_progression"],
        )
        for fact in facts
    ] == [(3, 0.0, 10, 1)]
