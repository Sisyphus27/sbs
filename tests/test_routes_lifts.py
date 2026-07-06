from webapp import repo


def _lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                           start=None, lift_kind="main")
    conn.close()
    return lid


def test_lifts_view_lists_lift(client, app):
    _lift(app)
    rv = client.get("/lifts")
    assert rv.status_code == 200 and b"Squat" in rv.data


def test_create_lift_via_post(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Press", "tier": "sbs", "day": "2", "sets": "5",
        "max": "60", "intensity": "0.7", "reps": "5", "repout": "10",
    })
    assert rv.status_code == 200  # returns updated row fragment
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Press") is not None
        conn.close()


def test_delete_lift_via_post(client, app):
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/delete")
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid) is None
        conn.close()


def test_edit_lift_params_via_post(client, app):
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/edit", data={"intensity": "0.75", "day": "2"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["intensity"] == 0.75
        conn.close()


def test_rename_lift_via_post(client, app):
    lid = _lift(app)
    client.post(f"/lifts/{lid}/edit", data={"name": "Back Squat"})
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["name"] == "Back Squat"
        conn.close()


def test_tier_preview_then_apply(client, app):
    lid = _lift(app)
    # build some history so est1rm exists
    client.post("/log", data={f"log_{lid}": "12"})
    rv = client.get(f"/lifts/{lid}/tier?tier=t3")
    assert rv.status_code == 200 and b"t3" in rv.data
    rv = client.post(f"/lifts/{lid}/tier", data={"tier": "t3"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["tier"] == "t3"
        conn.close()


def _t2_lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=85.0)
    conn.close()
    return lid


def test_edit_start_t2_recomputes_weight(client, app):
    lid = _t2_lift(app)  # created with start=85 -> lift_state.weight seeded 85
    rv = client.post(f"/lifts/{lid}/edit", data={"start": "65"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_state(conn, lid)["weight"] == 65.0  # recomputed to new start
        conn.close()


def test_edit_start_sbs_does_not_recompute(client, app):
    lid = _lift(app)  # sbs Squat
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        tm_before = repo.get_lift_state(conn, lid)["tm"]
        conn.close()
    client.post(f"/lifts/{lid}/edit", data={"start": "100"})
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_state(conn, lid)["tm"] == tm_before  # sbs tm unchanged
        conn.close()
