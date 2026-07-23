import sqlite3
from webapp import db
from migrate_modes import migrate_modes


def _old_schema_db(tmp_path):
    """Build a pre-refactor DB with tier/progression columns + sample rows."""
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), week INT NOT NULL,
      days_per_week INT NOT NULL, rounding REAL NOT NULL, incr REAL NOT NULL,
      t2_reset_pct REAL NOT NULL, t2_fail INT NOT NULL, t3_target INT NOT NULL,
      bodyweight REAL NOT NULL DEFAULT 0);
    INSERT INTO settings VALUES (1,1,4,2.5,2.5,0.75,3,15,75.0);
    CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      tier TEXT NOT NULL, day INT NOT NULL, sort_order INT NOT NULL DEFAULT 0,
      sets INT NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INT, repout INT,
      start REAL, lift_kind TEXT, incr REAL,
      bodyweight_pct REAL NOT NULL DEFAULT 0.0,
      progression TEXT NOT NULL DEFAULT 'weight');
    CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT NOT NULL,
      tm REAL, weight REAL, target INT, streak INT NOT NULL DEFAULT 0,
      est1rm REAL, reseeded_cycle INT NOT NULL DEFAULT 0);
    CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INT NOT NULL,
      week INT NOT NULL, weight REAL NOT NULL, reps INT NOT NULL, ts TEXT NOT NULL);
    """)
    # sbs barbell, t2 barbell, t2 bodyweight(weighted pull-up), pure-bodyweight crunch
    conn.execute("INSERT INTO lifts (name,tier,day,max,lift_kind) VALUES ('Squat','sbs',1,100,'main')")
    conn.execute("INSERT INTO lifts (name,tier,day,start) VALUES ('Bench','t2',1,60)")
    conn.execute("INSERT INTO lifts (name,tier,day,start,bodyweight_pct) VALUES ('Pull-up','t2',2,10,1.0)")
    conn.execute("INSERT INTO lifts (name,tier,day,bodyweight_pct,progression) VALUES ('Crunch','t3',2,1.0,'none')")
    conn.execute("INSERT INTO lift_state VALUES (1,'sbs',100,NULL,NULL,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (2,'t2',NULL,60,8,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (3,'t2',NULL,10,8,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (4,'t3',NULL,NULL,NULL,0,NULL,0)")
    conn.commit()
    return p, conn


def test_migrate_maps_rows(tmp_path):
    p, conn = _old_schema_db(tmp_path)
    migrate_modes(conn)
    rows = {r["name"]: (r["load_model"], r["mode"]) for r in
            conn.execute("SELECT name, load_model, mode FROM lifts")}
    assert rows["Squat"] == ("barbell", "sbs")
    assert rows["Bench"] == ("barbell", "linear_t2")
    assert rows["Pull-up"] == ("bodyweight", "linear_t2")
    assert rows["Crunch"] == ("pure_bodyweight", "none")
    # lift_state tier -> mode
    st = {r["lift_id"]: r["mode"] for r in conn.execute("SELECT lift_id, mode FROM lift_state")}
    assert st[1] == "sbs" and st[2] == "linear_t2" and st[4] == "none"
    # old columns gone
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(lifts)")}
    assert "tier" not in cols and "progression" not in cols
    conn.close()


def test_migrate_idempotent(tmp_path):
    p, conn = _old_schema_db(tmp_path)
    migrate_modes(conn)
    n = migrate_modes(conn)   # second run no-op
    assert n == 0
    conn.close()


def test_migrate_handles_pathological_sbs_with_bodyweight_pct(tmp_path):
    """A pathological legacy row with tier='sbs' AND bodyweight_pct>0 must not
    KeyError; it maps defensively to ('barbell', 'sbs') (sbs is barbell-only,
    the stray pct is ignored). T8 Minor 2 guard."""
    p, conn = _old_schema_db(tmp_path)
    # Insert a row that violates the sbs-is-barbell-only invariant.
    conn.execute(
        "INSERT INTO lifts (name,tier,day,max,bodyweight_pct,lift_kind) "
        "VALUES ('Squat-BW','sbs',3,100,1.0,'main')"
    )
    conn.execute(
        "INSERT INTO lift_state (lift_id,tier,tm) VALUES (5,'sbs',100.0)"
    )
    conn.commit()
    migrate_modes(conn)
    rows = {r["name"]: (r["load_model"], r["mode"]) for r in
            conn.execute("SELECT name, load_model, mode FROM lifts")}
    assert rows["Squat-BW"] == ("barbell", "sbs")
    st = {r["lift_id"]: r["mode"] for r in
          conn.execute("SELECT lift_id, mode FROM lift_state")}
    assert st[5] == "sbs"
    conn.close()
