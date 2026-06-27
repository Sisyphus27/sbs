from webapp import repo


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


def test_plan_submit_advances(client, app):
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
        conn.close()
    rv = client.post("/log", data={f"log_{lid}": "13"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_settings(conn)["week"] == 2
        conn.close()
