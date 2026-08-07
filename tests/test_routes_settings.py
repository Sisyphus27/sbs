from webapp import repo


def test_settings_view(client):
    rv = client.get("/settings")
    text = rv.data.decode("utf-8")
    assert rv.status_code == 200
    assert "Rounding quantum" in text
    assert "Settings" in text


def test_settings_update(client, app):
    rv = client.post("/settings", data={"incr": "5.0", "t3_target": "20"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        s = repo.get_settings(conn)
        assert s["incr"] == 5.0 and s["t3_target"] == 20
        conn.close()


def test_reset_t2_fail_restores_default(client, app):
    with app.app_context():
        from webapp.db import connect
        from webapp import repo
        conn = connect(app.config["DB_PATH"])
        repo.update_settings(conn, t2_fail=5)
        conn.close()
    rv = client.post("/settings/t2_fail/reset")
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert conn.execute("SELECT t2_fail FROM settings WHERE id=1").fetchone()["t2_fail"] == 3
        conn.close()


def test_reset_rounding_is_not_a_route(client):
    # rounding is a weight setting — no reset endpoint
    rv = client.post("/settings/rounding/reset")
    assert rv.status_code == 404


def test_reset_unknown_field_is_404(client):
    rv = client.post("/settings/nope/reset")
    assert rv.status_code == 404


def test_update_settings_bodyweight(client, app):
    rv = client.post("/settings", data={"bodyweight": "75.5"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_settings(conn)["bodyweight"] == 75.5
        conn.close()
