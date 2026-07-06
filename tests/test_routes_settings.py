from webapp import repo


def test_settings_view(client):
    rv = client.get("/settings")
    text = rv.data.decode("utf-8")
    assert rv.status_code == 200
    assert "最小变动" in text            # gym-increment field relabeled
    assert "全局参数" in text            # page title still present


def test_settings_update(client, app):
    rv = client.post("/settings", data={"incr": "5.0", "t3_target": "20"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        s = repo.get_settings(conn)
        assert s["incr"] == 5.0 and s["t3_target"] == 20
        conn.close()
