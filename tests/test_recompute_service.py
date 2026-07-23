from webapp import db, repo
from webapp.services import recompute as recompute_service


def _t2(conn, start=85.0):
    return repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                            day=1, sort_order=0,
                            sets=4, max=None, intensity=None, reps=None, repout=None, start=start)


def test_recompute_t2_no_history_sets_weight_to_start(tmp_path):
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = _t2(conn, start=85.0)
    recompute_service.recompute_on_start_change(conn, lid, 65.0)  # lower the start
    st = repo.get_lift_state(conn, lid)
    assert st["weight"] == 65.0 and st["target"] == 8 and st["streak"] == 0
    conn.close()


def test_recompute_sbs_is_noop(tmp_path):
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    tm_before = repo.get_lift_state(conn, lid)["tm"]
    assert recompute_service.recompute_on_start_change(conn, lid, 100.0) is None
    assert repo.get_lift_state(conn, lid)["tm"] == tm_before  # sbs untouched
    conn.close()


def test_recompute_preserves_est1rm_from_history(tmp_path):
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn = db.connect(str(tmp_path / "t.db")); db.init_schema(conn)
    lid = _t2(conn, start=50.0)
    for wk, w, r in [(1, 50.0, 10), (2, 52.5, 8)]:
        repo.append_history(conn, lid, week=wk, weight=w, reps=r)
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lid)]
    expected_est = _est1rm_from_history(hist)
    recompute_service.recompute_on_start_change(conn, lid, 55.0)  # change start; est1rm must not move
    assert repo.get_lift_state(conn, lid)["est1rm"] == expected_est
    conn.close()


def test_recompute_on_start_change_uses_per_lift_incr(tmp_path):
    """recompute 服务经 _lift_from_row(incr) + recompute_state(eff_incr) 自动继承 per-lift incr。
    锁定 recompute.py 零改动路径（D3）：编辑 start 后重放按 lift.incr=5 累加，而非全局 2.5。"""
    from webapp.services import advance
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Curls", load_model="barbell", mode="linear_t3",
                           day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=40.0, incr=5.0)
    # 一次命中 -> history；advance 用 eff_incr=5 -> 40+5=45
    advance.advance_week(conn, {lid: 16})
    repo.set_week(conn, 1)
    # 编辑 start=20 -> 重放：20 + 5（per-lift incr）= 25
    ls = recompute_service.recompute_on_start_change(conn, lid, 20.0)
    assert ls is not None and ls.weight == 25.0  # 不是 20+2.5=22.5
    assert repo.get_lift_state(conn, lid)["weight"] == 25.0
    conn.close()
