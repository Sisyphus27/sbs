from sbs_cli.engine.onerm import estimate_1rm
from webapp import db, repo
from webapp.services import preview


def _sbs(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    return conn, lid


def test_live_preview_no_history(tmp_path):
    conn, lid = _sbs(tmp_path)
    r = preview.live_preview(conn, lid, 11)
    # working weight = round(135 * 0.7, 2.5) = 95.0
    assert r["weight"] == 95.0
    assert r["est1rm"] == estimate_1rm(95.0, 11)
    assert r["best"] is None and r["delta"] is None
    conn.close()


def test_live_preview_delta_vs_history(tmp_path):
    conn, lid = _sbs(tmp_path)
    repo.append_history(conn, lid, week=1, weight=95.0, reps=10)  # prior best
    r = preview.live_preview(conn, lid, 11)
    best = estimate_1rm(95.0, 10)
    assert r["best"] == best
    assert r["delta"] == r["est1rm"] - best
    assert r["delta"] > 0   # 11 reps beats the 10-rep best
    conn.close()


def test_live_preview_negative_delta(tmp_path):
    conn, lid = _sbs(tmp_path)
    repo.append_history(conn, lid, week=1, weight=95.0, reps=13)  # strong prior best
    r = preview.live_preview(conn, lid, 9)   # weaker today
    assert r["delta"] < 0
    conn.close()


def test_live_preview_t2_uses_state_weight(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    r = preview.live_preview(conn, lid, 10)
    assert r["weight"] == 85.0   # t2 working weight = state.weight
    assert r["est1rm"] == estimate_1rm(85.0, 10)
    conn.close()
