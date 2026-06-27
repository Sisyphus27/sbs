import sqlite3
from webapp import db, repo


def _fresh(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    return conn


def test_get_settings_returns_defaults(tmp_path):
    conn = _fresh(tmp_path)
    s = repo.get_settings(conn)
    assert s["week"] == 1 and s["rounding"] == 2.5 and s["t3_target"] == 15
    conn.close()


def test_set_week_updates_week(tmp_path):
    conn = _fresh(tmp_path)
    repo.set_week(conn, 7)
    assert repo.get_settings(conn)["week"] == 7
    conn.close()


def test_update_settings_partial(tmp_path):
    conn = _fresh(tmp_path)
    repo.update_settings(conn, incr=5.0, t3_target=20)
    s = repo.get_settings(conn)
    assert s["incr"] == 5.0 and s["t3_target"] == 20 and s["rounding"] == 2.5
    conn.close()
