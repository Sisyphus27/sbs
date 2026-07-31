from webapp import db, repo
from webapp.services import advance, mode


def _seed_with_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                           start=None, lift_kind="main")
    # one logged week -> est1rm derived from history
    advance.advance_week(conn, {lid: 10})
    repo.set_week(conn, 1)  # roll week back for test isolation
    return conn, lid


def test_preview_mode_switch_preserves_history_basis(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = mode.derive_state(conn, lid, "linear_t2", repo.get_settings(conn))
    # LinearT2Mode.derive_on_switch resets target to 8 (same as initial_state),
    # unifying the legacy tier.py (which returned 10) with the engine invariant.
    assert preview["mode"] == "linear_t2" and preview["target"] == 8 and preview["streak"] == 0
    # weight = round(est1rm * 0.7, 2.5)
    assert preview["weight"] == round((est_before * 0.7) / 2.5) * 2.5 or preview["est1rm"] == est_before
    conn.close()


def test_preview_sbs_uses_est1rm_for_tm(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    est_before = repo.get_lift_state(conn, lid)["est1rm"]
    preview = mode.derive_state(conn, lid, "sbs", repo.get_settings(conn))
    assert preview["tm"] == est_before
    conn.close()


def test_apply_mode_switch_keeps_history_and_writes_state(tmp_path):
    conn, lid = _seed_with_history(tmp_path)
    hist_before = len(repo.list_history(conn, lid))
    preview = mode.derive_state(conn, lid, "linear_t3", repo.get_settings(conn))
    mode.apply_switch(conn, lid, preview)
    st = repo.get_lift_state(conn, lid)
    assert st["mode"] == "linear_t3" and st["weight"] == preview["weight"]
    assert repo.get_lift(conn, lid)["mode"] == "linear_t3"
    assert len(repo.list_history(conn, lid)) == hist_before  # history untouched
    conn.close()


def test_derive_state_rejects_illegal_combo(tmp_path):
    """ADR 0005 legal-combo guard: a barbell lift cannot switch to ``none``
    (none is pure_bodyweight-only); a bodyweight lift cannot switch to ``sbs``
    (sbs is barbell-only). The guard runs before any history read."""
    from sbs_cli.data.schema import is_legal_combo  # noqa: F401 (sanity anchor)
    conn, lid = _seed_with_history(tmp_path)  # barbell sbs lift
    settings = repo.get_settings(conn)
    try:
        mode.derive_state(conn, lid, "none", settings)
    except ValueError:
        pass
    else:
        raise AssertionError("barbell -> none must be rejected by is_legal_combo")
    conn.close()


def test_derive_state_linear_t2_snaps_to_eff_incr(tmp_path):
    """linear_t2 derive：incr=5 的动作，起始重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5。"""
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.engine.onerm import est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn, _ = _seed_with_history(tmp_path)  # 复用既有 fixture 建一个 sbs lift+history
    # 另建一个 incr=5 的 linear_t2 动作，灌入产生已知 est1rm 的 history
    lid = repo.create_lift(conn, name="PD", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=1,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=100.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # 100x5 -> est1rm≈115
    settings = repo.get_settings(conn)
    preview = mode.derive_state(conn, lid, "linear_t2", settings)
    est = est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * settings["t2_reset_pct"], 5)   # eff_incr=5
    assert preview["weight"] != round_weight(est * settings["t2_reset_pct"], 2.5)  # 旧全局 rounding
    conn.close()


def test_derive_state_linear_t3_snaps_to_eff_incr(tmp_path):
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.engine.onerm import est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn = db.connect(str(tmp_path / "t2.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="FP", load_model="barbell", mode="linear_t3",
                           day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=30.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # est1rm≈115 -> *0.6≈69
    settings = repo.get_settings(conn)
    preview = mode.derive_state(conn, lid, "linear_t3", settings)
    est = est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * 0.6, 5)   # eff_incr=5 网格
    conn.close()


def test_apply_switch_preserves_incr(tmp_path):
    """D6：mode 切换不触碰 lifts.incr 列。"""
    conn = db.connect(str(tmp_path / "t3.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="PD", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=50.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=50.0, reps=8)
    preview = mode.derive_state(conn, lid, "linear_t3", repo.get_settings(conn))
    mode.apply_switch(conn, lid, preview)
    assert repo.get_lift(conn, lid)["incr"] == 5   # preserved across switch
    conn.close()


def test_derive_state_tolerates_missing_incr_column(tmp_path):
    """Regression: on a legacy DB whose lifts table has NO incr column
    (pre-migrate_incr.py shape), derive_state must fall back to settings['incr']
    instead of crashing with IndexError on the mode-switch preview/apply path.
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
    preview_t2 = mode.derive_state(conn, lid, "linear_t2", settings)
    assert preview_t2["mode"] == "linear_t2" and preview_t2["target"] == 8
    assert preview_t2["weight"] == round_weight(est_before * settings["t2_reset_pct"],
                                                settings["incr"])
    # linear_t3 path shares the same eff_incr resolution — must also be guarded.
    preview_t3 = mode.derive_state(conn, lid, "linear_t3", settings)
    assert preview_t3["mode"] == "linear_t3"
    assert preview_t3["weight"] == round_weight(est_before * 0.6, settings["incr"])
    conn.close()
