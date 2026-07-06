"""Tests for the one-shot `migrate_schedule` migration.

The helper `_build_legacy_db` constructs a DB with the pre-Task-1/5/6 schema
(no ``lift_kind`` on lifts, no ``reseeded_cycle`` on lift_state, no
``sbs_schedule`` table). The migration must add all three, seed the 42-row
DEFAULT_SCHEDULE, backfill ``lift_kind`` for sbs lifts from ``sets``, and
replay every t2 lift's state through the new 1-strike ``t2_next`` via
``recompute_state``. It must be idempotent.
"""
import sqlite3

from webapp import db, repo
import migrate_schedule


def _build_legacy_db(db_path) -> tuple[int, int]:
    """Create a legacy (pre-Task 1/5/6) schema + seed two lifts.

    Returns (squat_id, chin_id):
      - Squat  : sbs, sets=5 (-> main after backfill), max=135, no history.
      - Chin-ups: t2, start=50, target=8 (legacy default), one logged miss (5 < 8).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE settings (
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            week          INTEGER NOT NULL,
            days_per_week INTEGER NOT NULL,
            rounding      REAL    NOT NULL,
            incr          REAL    NOT NULL,
            t2_reset_pct  REAL    NOT NULL,
            t2_fail       INTEGER NOT NULL,
            t3_target     INTEGER NOT NULL
        );
        CREATE TABLE lifts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            tier       TEXT NOT NULL CHECK (tier IN ('sbs','t2','t3')),
            day        INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            sets       INTEGER NOT NULL DEFAULT 3,
            max        REAL,
            intensity  REAL,
            reps       INTEGER,
            repout     INTEGER,
            start      REAL
        );
        CREATE TABLE lift_state (
            lift_id INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
            tier    TEXT NOT NULL,
            tm      REAL,
            weight  REAL,
            target  INTEGER,
            streak  INTEGER NOT NULL DEFAULT 0,
            est1rm  REAL
        );
        CREATE TABLE history (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
            week    INTEGER NOT NULL,
            weight  REAL NOT NULL,
            reps    INTEGER NOT NULL,
            ts      TEXT NOT NULL
        );
        CREATE TABLE week_log (
            lift_id INTEGER NOT NULL REFERENCES lifts(id) ON DELETE CASCADE,
            week    INTEGER NOT NULL,
            reps    INTEGER NOT NULL,
            PRIMARY KEY (lift_id, week)
        );
        INSERT INTO settings (id, week, days_per_week, rounding, incr,
                              t2_reset_pct, t2_fail, t3_target)
        VALUES (1, 1, 4, 2.5, 2.5, 0.75, 3, 15);
        """
    )
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start) "
        "VALUES ('Squat', 'sbs', 1, 0, 5, 135.0, 0.70, 5, 10, NULL)"
    )
    squat_id = cur.lastrowid
    conn.execute(
        "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
        "VALUES (?, 'sbs', 135.0, NULL, NULL, 0, NULL)",
        (squat_id,),
    )
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start) "
        "VALUES ('Chin-ups', 't2', 2, 0, 4, NULL, NULL, NULL, NULL, 50.0)"
    )
    chin_id = cur.lastrowid
    conn.execute(
        "INSERT INTO lift_state (lift_id, tier, tm, weight, target, streak, est1rm) "
        "VALUES (?, 't2', NULL, 50.0, 8, 0, NULL)",
        (chin_id,),
    )
    # One logged miss: 5 reps at weight 50, target was 8 -> 1-strike drops 8 -> 6.
    conn.execute(
        "INSERT INTO history (lift_id, week, weight, reps, ts) "
        "VALUES (?, 1, 50.0, 5, '2026-01-01T00:00:00Z')",
        (chin_id,),
    )
    conn.commit()
    conn.close()
    return squat_id, chin_id


def test_migrate_seeds_42_schedule_rows(tmp_path):
    dbp = str(tmp_path / "t.db")
    _build_legacy_db(dbp)
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
    _build_legacy_db(dbp)
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
    squat_id, _ = _build_legacy_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    # Legacy DB had no lift_kind column at all; migration must ALTER + backfill.
    row = conn.execute(
        "SELECT lift_kind FROM lifts WHERE id=?", (squat_id,)
    ).fetchone()
    conn.close()
    assert row["lift_kind"] == "main"


def test_migrate_replays_t2_one_miss_to_target_6(tmp_path):
    """One logged miss under the new 1-strike rule drops target 8 -> 6."""
    dbp = str(tmp_path / "t.db")
    _, chin_id = _build_legacy_db(dbp)
    migrate_schedule.main(db_path=dbp, backup_dir=str(tmp_path / "bak"))
    conn = db.connect(dbp)
    st = repo.get_lift_state(conn, chin_id)
    conn.close()
    assert st["target"] == 6
    assert st["streak"] == 1
    assert st["weight"] == 50.0  # unchanged on a miss


def test_migrate_adds_reseeded_cycle_column_with_default_0(tmp_path):
    dbp = str(tmp_path / "t.db")
    squat_id, _ = _build_legacy_db(dbp)
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
    _build_legacy_db(dbp)
    bdir = tmp_path / "bak"
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    backups = list(bdir.glob("*.db.bak"))
    assert len(backups) == 1


def test_migrate_is_idempotent(tmp_path):
    """Re-running must not error, must not duplicate schedule rows, must converge
    on the same lift_kind + T2 replay result."""
    dbp = str(tmp_path / "t.db")
    squat_id, chin_id = _build_legacy_db(dbp)
    bdir = tmp_path / "bak"
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    migrate_schedule.main(db_path=dbp, backup_dir=str(bdir))
    conn = db.connect(dbp)
    # Schedule still exactly 42 rows (no duplicate seed).
    n = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
    assert n == 42
    # lift_kind still 'main' (backfill is guarded by IS NULL).
    assert repo.get_lift(conn, squat_id)["lift_kind"] == "main"
    # T2 replay converges to the same target=6.
    assert repo.get_lift_state(conn, chin_id)["target"] == 6
    assert repo.get_lift_state(conn, chin_id)["streak"] == 1
    # reseeded_cycle still default 0.
    assert repo.get_lift_state(conn, squat_id)["reseeded_cycle"] == 0
    conn.close()
