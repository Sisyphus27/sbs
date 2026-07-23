"""Tests for the one-shot `migrate_schedule` migration.

The helper `_build_modern_db` constructs a DB with the current init_schema
(load_model/mode columns, sbs_schedule table, reseeded_cycle column already
present) then seeds two lifts via the new create_lift API. After T8
(migrate_modes), the migration runs against the modern schema — its job becomes
the orthogonal backfill (sbs_schedule seed guard, lift_kind backfill for
mode='sbs' lifts, linear_t2 state replay) and it must remain idempotent.
"""
import sqlite3

from webapp import db, repo
import migrate_schedule


def _build_modern_db(db_path) -> tuple[int, int]:
    """Create a modern-schema DB + seed two lifts.

    Returns (squat_id, chin_id):
      - Squat  : mode='sbs', sets=5 (-> main after backfill), max=135, no history.
      - Chin-ups: mode='linear_t2', start=50, target=8 (default), one logged miss (5 < 8).
    """
    conn = db.connect(db_path)
    db.init_schema(conn)
    squat_id = repo.create_lift(
        conn, name="Squat", load_model="barbell", mode="sbs",
        day=1, sort_order=0, sets=5, max=135.0, intensity=0.70, reps=5, repout=10,
        start=None, lift_kind=None)
    chin_id = repo.create_lift(
        conn, name="Chin-ups", load_model="barbell", mode="linear_t2",
        day=2, sort_order=0, sets=4, max=None, intensity=None, reps=None,
        repout=None, start=50.0)
    # Set the linear_t2 lift's state to the legacy default (target=8, streak=0)
    # so the migration's replay has something to update.
    repo.save_lift_state(conn, chin_id, mode="linear_t2", tm=None, weight=50.0,
                         target=8, streak=0, est1rm=None)
    # One logged miss: 5 reps at weight 50, target was 8 -> 1-strike drops 8 -> 6.
    repo.append_history(conn, chin_id, week=1, weight=50.0, reps=5)
    # Clear Squat's lift_kind so the backfill has work to do.
    conn.execute("UPDATE lifts SET lift_kind=NULL WHERE id=?", (squat_id,))
    conn.commit()
    conn.close()
    return squat_id, chin_id


def test_migrate_seeds_42_schedule_rows(tmp_path):
    dbp = str(tmp_path / "t.db")
    _build_modern_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    n_main = conn.execute("SELECT COUNT(*) FROM sbs_schedule WHERE kind='main'").fetchone()[0]
    n_aux = conn.execute("SELECT COUNT(*) FROM sbs_schedule WHERE kind='aux'").fetchone()[0]
    conn.close()
    assert n_main == 21
    assert n_aux == 21
    assert n_main + n_aux == 42


def test_migrate_creates_sbs_schedule_table_with_legacy_21_week_rows(tmp_path):
    """Spot-check week-1 main + week-7 aux (deload) values to confirm the seed is DEFAULT_SCHEDULE."""
    dbp = str(tmp_path / "t.db")
    _build_modern_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    m1 = conn.execute(
        "SELECT intensity, reps, repout FROM sbs_schedule WHERE kind='main' AND week=1"
    ).fetchone()
    a7 = conn.execute(
        "SELECT intensity, reps, repout FROM sbs_schedule WHERE kind='aux' AND week=7"
    ).fetchone()
    conn.close()
    assert (m1["intensity"], m1["reps"], m1["repout"]) == (0.70, 5, 10)
    assert (a7["intensity"], a7["reps"], a7["repout"]) == (0.50, 8, 18)


def test_migrate_backfills_squat_lift_kind_main(tmp_path):
    dbp = str(tmp_path / "t.db")
    squat_id, _ = _build_modern_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    # Modern schema already has lift_kind column; migration backfills mode='sbs' rows.
    row = conn.execute(
        "SELECT lift_kind FROM lifts WHERE id=?", (squat_id,)
    ).fetchone()
    conn.close()
    assert row["lift_kind"] == "main"


def test_migrate_replays_t2_one_miss_to_target_6(tmp_path):
    """One logged miss under the new 1-strike rule drops target 8 -> 6."""
    dbp = str(tmp_path / "t.db")
    _, chin_id = _build_modern_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    st = repo.get_lift_state(conn, chin_id)
    conn.close()
    assert st["target"] == 6
    assert st["streak"] == 1
    assert st["weight"] == 50.0  # unchanged on a miss


def test_migrate_adds_reseeded_cycle_column_with_default_0(tmp_path):
    dbp = str(tmp_path / "t.db")
    squat_id, _ = _build_modern_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lift_state)").fetchall()]
    val = conn.execute(
        "SELECT reseeded_cycle FROM lift_state WHERE lift_id=?", (squat_id,)
    ).fetchone()
    conn.close()
    assert "reseeded_cycle" in cols
    assert val["reseeded_cycle"] == 0


def test_migrate_creates_backup(tmp_path):
    dbp = str(tmp_path / "t.db")
    _build_modern_db(dbp)
    bdir = tmp_path / "bak"
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    backups = list(bdir.glob("*.db.bak"))
    assert len(backups) == 1


def test_migrate_is_idempotent(tmp_path):
    """Re-running must not error, must not duplicate schedule rows, must converge
    on the same lift_kind + linear_t2 replay result."""
    dbp = str(tmp_path / "t.db")
    squat_id, chin_id = _build_modern_db(dbp)
    bdir = tmp_path / "bak"
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    conn = db.connect(dbp)
    # Schedule still exactly 42 rows (no duplicate seed).
    n = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
    assert n == 42
    # lift_kind still 'main' (backfill is guarded by IS NULL).
    assert repo.get_lift(conn, squat_id)["lift_kind"] == "main"
    # linear_t2 replay converges to the same target=6.
    assert repo.get_lift_state(conn, chin_id)["target"] == 6
    assert repo.get_lift_state(conn, chin_id)["streak"] == 1
    # reseeded_cycle still default 0.
    assert repo.get_lift_state(conn, squat_id)["reseeded_cycle"] == 0
    conn.close()
