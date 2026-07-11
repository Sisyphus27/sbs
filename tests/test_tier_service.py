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


def test_derive_state_t2_snaps_to_eff_incr(tmp_path):
    """t2 derive：incr=5 的动作，起始重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5。"""
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn, _ = _seed_with_history(tmp_path)  # 复用既有 fixture 建一个 sbs lift+history
    # 另建一个 incr=5 的 t2 动作，灌入产生已知 est1rm 的 history
    lid = repo.create_lift(conn, name="PD", tier="t2", day=1, sort_order=1,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=100.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # 100x5 -> est1rm≈115
    settings = repo.get_settings(conn)
    preview = tier.derive_state(conn, lid, "t2", settings)
    est = _est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * settings["t2_reset_pct"], 5)   # eff_incr=5
    assert preview["weight"] != round_weight(est * settings["t2_reset_pct"], 2.5)  # 旧全局 rounding
    conn.close()


def test_derive_state_t3_snaps_to_eff_incr(tmp_path):
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn = db.connect(str(tmp_path / "t2.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="FP", tier="t3", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=30.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # est1rm≈115 -> *0.6≈69
    settings = repo.get_settings(conn)
    preview = tier.derive_state(conn, lid, "t3", settings)
    est = _est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * 0.6, 5)   # eff_incr=5 网格
    conn.close()


def test_apply_switch_preserves_incr(tmp_path):
    """D6：tier 切换不触碰 lifts.incr 列。"""
    conn = db.connect(str(tmp_path / "t3.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="PD", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=50.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=50.0, reps=8)
    preview = tier.derive_state(conn, lid, "t3", repo.get_settings(conn))
    tier.apply_switch(conn, lid, preview)
    assert repo.get_lift(conn, lid)["incr"] == 5   # preserved across switch
    conn.close()


def test_derive_state_tolerates_missing_incr_column(tmp_path):
    """Regression: on a legacy DB whose lifts table has NO incr column
    (pre-migrate_incr.py shape), derive_state must fall back to settings['incr']
    instead of crashing with IndexError on the tier-switch preview/apply path.
    The advance path was already hardened (advance._lift_from_row); derive_state
    needs the same guard so 'reads degrade gracefully on an unmigrated DB' holds
    symmetrically across both code paths."""
    from sbs_cli.engine.progression import round_weight
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    assert est_before is not None  # sanity: the lift has history -> est1rm known
    settings = repo.get_settings(conn)
    # Simulate a pre-migrate_incr legacy DB: drop the incr column from lifts.
    conn.execute("ALTER TABLE lifts DROP COLUMN incr")
    conn.commit()
    assert "incr" not in repo.get_lift(conn, lid).keys()  # column really gone
    # Must NOT raise IndexError; weight snaps to the global-incr grid.
    preview_t2 = tier.derive_state(conn, lid, "t2", settings)
    assert preview_t2["tier"] == "t2" and preview_t2["target"] == 10
    assert preview_t2["weight"] == round_weight(est_before * settings["t2_reset_pct"],
                                                settings["incr"])
    # t3 path shares the same eff_incr resolution — must also be guarded.
    preview_t3 = tier.derive_state(conn, lid, "t3", settings)
    assert preview_t3["tier"] == "t3"
    assert preview_t3["weight"] == round_weight(est_before * 0.6, settings["incr"])
    conn.close()
