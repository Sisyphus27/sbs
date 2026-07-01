from webapp import db, repo
import migrate_recompute


def _seed(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    # a divergent t2 lift: configured start 65, but state.weight stuck at 85 (the bug)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=65.0)
    repo.save_lift_state(conn, lid, tier="t2", tm=None, weight=85.0,
                         target=8, streak=0, est1rm=None)
    conn.close()
    return lid


def test_migrate_bumps_reset_pct_and_syncs_weight(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_recompute.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_settings(conn)["t2_reset_pct"] == 0.75
    assert repo.get_lift_state(conn, lid)["weight"] == 65.0  # replayed to start (no history)
    conn.close()


def test_migrate_creates_backup(tmp_path):
    dbp = str(tmp_path / "t.db")
    _seed(dbp)
    bdir = tmp_path / "bak"
    migrate_recompute.main(db_path=dbp, backup_dir=str(bdir))
    backups = list(bdir.glob("*.db.bak"))
    assert len(backups) == 1
