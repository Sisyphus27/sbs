from webapp import repo


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


def test_plan_renders_duplicate_names_with_distinct_state(client, app):
    """Same name on two days must render each day's own weight (id-keyed, not clobbered)."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.create_lift(conn, name="Face Pull", tier="t3", day=4, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=45.0)
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert html.count("Face Pull") == 2
    assert "30.0 kg" in html and "45.0 kg" in html   # each day keeps its own weight
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
