from webapp import db, repo
import migrate_sbs_tm


def _seed(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    # sbs Squat: max=135, week-1 history 90x8 (repout 10 -> diff -2 -> -5%).
    # Faithful raw TM = 135*0.95 = 128.25. Stored (buggy, rounded) = 127.5.
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=3, max=135.0, intensity=0.7, reps=4, repout=10, start=None)
    repo.save_lift_state(conn, lid, tier="sbs", tm=127.5, weight=None,
                         target=None, streak=0, est1rm=120.0)
    repo.append_history(conn, lid, week=1, weight=90.0, reps=8)
    conn.close()
    return lid


def test_migrate_replays_sbs_tm_raw_from_max(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 128.25            # replayed raw from max, not 127.5
    assert st["est1rm"] == 120.0         # untouched
    conn.close()


def test_migrate_skips_non_sbs_lifts(tmp_path):
    dbp = str(tmp_path / "t.db")
    conn = db.connect(dbp)
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=4, max=None, intensity=None, reps=None, repout=None, start=65.0)
    repo.save_lift_state(conn, lid, tier="t2", tm=None, weight=85.0,
                         target=8, streak=0, est1rm=None)
    conn.close()
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_lift_state(conn, lid)["weight"] == 85.0   # unchanged
    conn.close()


def test_migrate_creates_backup(tmp_path):
    dbp = str(tmp_path / "t.db")
    _seed(dbp)
    bdir = tmp_path / "bak"
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(bdir))
    assert len(list(bdir.glob("*.db.bak"))) == 1


def test_migrate_is_idempotent(tmp_path):
    dbp = str(tmp_path / "t.db")
    lid = _seed(dbp)
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    migrate_sbs_tm.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    assert repo.get_lift_state(conn, lid)["tm"] == 128.25
    conn.close()
