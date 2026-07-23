from webapp import repo


def _lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None, lift_kind="main")
    conn.close()
    return lid


def test_lifts_view_lists_lift(client, app):
    _lift(app)
    rv = client.get("/lifts")
    assert rv.status_code == 200 and b"Squat" in rv.data


def test_create_lift_via_post(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Press", "load_model": "barbell", "mode": "sbs",
        "day": "2", "sets": "5",
        "max": "60", "intensity": "0.7", "reps": "5", "repout": "10",
    })
    assert rv.status_code == 200  # returns updated row fragment
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Press") is not None
        conn.close()


def test_new_rejects_illegal_combo(client, app):
    # bodyweight + sbs is not in LEGAL_COMBOS -> 400
    rv = client.post("/lifts/new", data={"name": "X", "load_model": "bodyweight",
                                         "mode": "sbs", "day": 1})
    assert rv.status_code == 400


def test_new_rejects_bad_load_model(client, app):
    rv = client.post("/lifts/new", data={"name": "X", "load_model": "kettlebell",
                                         "mode": "sbs", "day": 1})
    assert rv.status_code == 400


def test_new_pure_bodyweight_defaults_pct(client, app):
    # pure_bodyweight + none: pct defaults to 1.0 when bodyweight_pct is omitted
    rv = client.post("/lifts/new", data={"name": "Pull-up", "load_model": "pure_bodyweight",
                                         "mode": "none", "day": 1})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Pull-up")["bodyweight_pct"] == 1.0
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


def test_mode_preview_then_apply(client, app):
    lid = _lift(app)
    # build some history so est1rm exists
    client.post("/log", data={f"log_{lid}": "12"})
    rv = client.get(f"/lifts/{lid}/mode?mode=linear_t3")
    assert rv.status_code == 200 and b"linear_t3" in rv.data
    rv = client.post(f"/lifts/{lid}/mode", data={"mode": "linear_t3"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["mode"] == "linear_t3"
        conn.close()


def test_mode_apply_rejects_illegal_combo(client, app):
    # barbell lift cannot switch to none (not in LEGAL_COMBOS)
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/mode", data={"mode": "none"})
    assert rv.status_code == 302  # flash + redirect per spec
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        # mode unchanged
        assert repo.get_lift(conn, lid)["mode"] == "sbs"
        conn.close()


def _t2_lift(app):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    lid = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=0, sets=4, max=None, intensity=None,
                           reps=None, repout=None, start=85.0)
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


def test_create_sbs_persists_lift_kind(client, app):
    # sbs lifts get an explicit main/aux kind from the form
    rv = client.post("/lifts/new", data={
        "name": "Bench", "load_model": "barbell", "mode": "sbs",
        "day": "1", "sets": "5", "max": "100", "lift_kind": "aux",
    })
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = repo.get_lift_by_name(conn, "Bench")
        assert row["lift_kind"] == "aux"
        conn.close()


def test_edit_changes_lift_kind(client, app):
    lid = _lift(app)  # created with lift_kind="main"
    rv = client.post(f"/lifts/{lid}/edit", data={"lift_kind": "aux"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["lift_kind"] == "aux"
        conn.close()


def _t2_lift_with_incr(app, incr=None):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    kwargs = dict(name="Rows", load_model="barbell", mode="linear_t2", day=1,
                  sort_order=0, sets=4, max=None, intensity=None, reps=None,
                  repout=None, start=85.0)
    if incr is not None:
        kwargs["incr"] = incr
    lid = repo.create_lift(conn, **kwargs)
    conn.close()
    return lid


def test_create_t2_with_incr(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Face Pull", "load_model": "barbell", "mode": "linear_t3",
        "day": "2", "sets": "3", "start": "30", "incr": "5",
    })
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Face Pull")["incr"] == 5.0
        conn.close()


def test_create_sbs_does_not_write_incr(client, app):
    # 即使表单带了 incr，sbs 创建也必须写 None（incr 仅 linear_t2/t3）
    rv = client.post("/lifts/new", data={
        "name": "Bench", "load_model": "barbell", "mode": "sbs",
        "day": "1", "sets": "5", "max": "100", "lift_kind": "main", "incr": "5",
    })
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Bench")["incr"] is None
        conn.close()


def test_create_rejects_nonpositive_incr(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Bad", "load_model": "barbell", "mode": "linear_t3",
        "day": "1", "sets": "3", "start": "30", "incr": "0",
    })
    assert rv.status_code == 400
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Bad") is None  # not created
        conn.close()


def test_edit_changes_incr(client, app):
    lid = _t2_lift_with_incr(app)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": "5"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] == 5.0
        conn.close()


def test_edit_clears_incr_to_null(client, app):
    lid = _t2_lift_with_incr(app, incr=5.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": ""})  # empty -> NULL
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] is None
        conn.close()


def test_edit_rejects_nonpositive_incr_and_preserves_original(client, app):
    lid = _t2_lift_with_incr(app, incr=5.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": "-1"})
    assert rv.status_code == 400
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] == 5.0  # original preserved
        conn.close()


def test_edit_rejects_illegal_mode_combo(client, app):
    # barbell sbs lift cannot be edited to mode=none (bad combo) -> 400, mode unchanged
    lid = _lift(app)
    rv = client.post(f"/lifts/{lid}/edit", data={"mode": "none"})
    assert rv.status_code == 400
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["mode"] == "sbs"
        conn.close()


def test_edit_changes_bodyweight_pct(client, app):
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Crunch", load_model="bodyweight",
                               mode="linear_t3", day=4, sort_order=1, sets=3,
                               max=None, intensity=None, reps=None, repout=None,
                               start=0.0)
        conn.close()
    rv = client.post(f"/lifts/{lid}/edit", data={"bodyweight_pct": "1.0"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["bodyweight_pct"] == 1.0
        conn.close()
