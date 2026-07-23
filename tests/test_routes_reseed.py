from sbs_cli.engine.progression import schedule_week, cycle_number


def _seed_squat_at(app, week):
    from webapp.db import connect
    from webapp import repo
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        repo.set_week(conn, week)
        lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                               day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                               reps=None, repout=None, start=None, lift_kind="main")
        conn.close()
        return lid


def test_reseed_not_due_in_cycle_1(client, app):
    _seed_squat_at(app, 2)            # cycle 1, schedule week 2 -> not due
    rv = client.get("/reseed")
    assert rv.status_code == 200
    assert b"Squat" not in rv.data    # not listed as due


def test_reseed_due_at_cycle_2_week_22(client, app):
    lid = _seed_squat_at(app, 22)     # schedule_week(22)=1, cycle 2, reseeded_cycle 0 -> due
    rv = client.get("/reseed")
    assert b"Squat" in rv.data


def test_reseed_apply_sets_max_and_tm(client, app):
    lid = _seed_squat_at(app, 22)
    rv = client.post(f"/reseed/{lid}", data={"max": "120"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT max FROM lifts WHERE id=?", (lid,)).fetchone()
        st = conn.execute("SELECT tm, reseeded_cycle FROM lift_state WHERE lift_id=?", (lid,)).fetchone()
        assert row["max"] == 120.0
        assert st["tm"] == 120.0
        assert st["reseeded_cycle"] == 2
        conn.close()


def test_reseed_skip_keeps_tm_advances_cycle(client, app):
    lid = _seed_squat_at(app, 22)
    rv = client.post(f"/reseed/{lid}/skip")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        st = conn.execute("SELECT tm, reseeded_cycle FROM lift_state WHERE lift_id=?", (lid,)).fetchone()
        assert st["tm"] == 100.0      # unchanged
        assert st["reseeded_cycle"] == 2
        conn.close()


def test_plan_banner_lists_due_reseed(client, app):
    _seed_squat_at(app, 22)
    html = client.get("/").get_data(as_text=True)
    assert "reseed" in html.lower() or "重测" in html
