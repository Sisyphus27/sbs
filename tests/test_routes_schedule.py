from sbs_cli.defaults import DEFAULT_SCHEDULE


def test_schedule_view_lists_42_rows(client):
    rv = client.get("/schedule")
    assert rv.status_code == 200
    assert b"Main" in rv.data and b"Aux" in rv.data


def test_schedule_save_edits_a_row(client, app):
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        conn.close()
    # post an edit for main week 1 -> intensity 0.71
    rv = client.post("/schedule", data={"main_1_intensity": "0.71",
                                        "main_1_reps": "5", "main_1_repout": "10"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT intensity FROM sbs_schedule WHERE kind='main' AND week=1").fetchone()
        assert row["intensity"] == 0.71
        conn.close()


def test_schedule_reset_restores_defaults(client, app):
    client.post("/schedule", data={"main_1_intensity": "0.99", "main_1_reps": "1", "main_1_repout": "1"})
    rv = client.post("/schedule/reset")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        row = conn.execute("SELECT * FROM sbs_schedule WHERE kind='main' AND week=1").fetchone()
        assert (row["intensity"], row["reps"], row["repout"]) == (0.70, 5, 10)
        conn.close()


def test_schedule_save_rejects_bad_intensity(client):
    rv = client.post("/schedule", data={"main_1_intensity": "1.5", "main_1_reps": "5", "main_1_repout": "10"})
    assert rv.status_code == 400
