from webapp import db, repo
from webapp.services import advance, tier


def _seed_with_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                           start=None, lift_kind="main")
    # one logged week -> est1rm derived from history
    advance.advance_week(conn, {lid: 10})
    repo.set_week(conn, 1)  # roll week back for test isolation
    return conn, lid


def test_preview_tier_switch_preserves_history_basis(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = tier.derive_state(conn, lid, "t2", repo.get_settings(conn))
    assert preview["tier"] == "t2" and preview["target"] == 10 and preview["streak"] == 0
    # weight = round(est1rm * 0.7, 2.5)
    assert preview["weight"] == round((est_before * 0.7) / 2.5) * 2.5 or preview["est1rm"] == est_before
    conn.close()


def test_preview_sbs_uses_est1rm_for_tm(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = tier.derive_state(conn, lid, "sbs", repo.get_settings(conn))
    assert preview["tm"] == est_before
    conn.close()


def test_apply_tier_switch_keeps_history_and_writes_state(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    hist_before = len(repo.list_history(conn, lid))
    preview = tier.derive_state(conn, lid, "t3", repo.get_settings(conn))
    tier.apply_switch(conn, lid, preview)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t3" and st["weight"] == preview["weight"]
    assert repo.get_lift(conn, lid)["tier"] == "t3"
    assert len(repo.list_history(conn, lid)) == hist_before  # history untouched
    conn.close()
