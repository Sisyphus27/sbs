"""One-shot: rebuild lifts table with load_model/mode, rename lift_state.tier->mode.

Maps the old (tier, progression, bodyweight_pct) triple to the new dual enums
(ADR 0005). History table untouched. Idempotent: no-op once lifts.load_model
exists. Backs up the DB before touching it (run via --db / --backup-dir).

Run:  conda run -n sbs python migrate_modes.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone


def _has_col(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})"))


_MAP = {
    # (tier, pct>0) -> (load_model, mode); progression=="none" handled separately.
    # ("sbs", True) is a pathological row (sbs is barbell-only; pct should be 0),
    # but we map it defensively to ("barbell", "sbs") rather than KeyError.
    ("sbs", False): ("barbell", "sbs"),
    ("sbs", True):  ("barbell", "sbs"),
    ("t2", False):  ("barbell", "linear_t2"),
    ("t2", True):   ("bodyweight", "linear_t2"),
    ("t3", False):  ("barbell", "linear_t3"),
    ("t3", True):   ("bodyweight", "linear_t3"),
}


def _derive(tier, progression, pct):
    if progression == "none":
        return ("pure_bodyweight", "none")
    return _MAP[(tier, pct > 0)]


def migrate_modes(conn) -> int:
    """Rebuild lifts with load_model/mode. Returns rows migrated (0 if already done)."""
    if _has_col(conn, "lifts", "load_model"):
        return 0
    rows = conn.execute("SELECT * FROM lifts").fetchall()
    conn.executescript("""
    CREATE TABLE lifts_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        load_model TEXT NOT NULL DEFAULT 'barbell'
          CHECK (load_model IN ('barbell','bodyweight','pure_bodyweight')),
        mode TEXT NOT NULL DEFAULT 'none'
          CHECK (mode IN ('sbs','linear_t2','linear_t3','none')),
        day INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
        sets INTEGER NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INTEGER,
        repout INTEGER, start REAL, lift_kind TEXT, incr REAL,
        bodyweight_pct REAL NOT NULL DEFAULT 0.0);
    """)
    for r in rows:
        pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
        prog = r["progression"] if "progression" in r.keys() else "weight"
        lm, mode = _derive(r["tier"], prog, pct)
        conn.execute(
            "INSERT INTO lifts_new (id,name,load_model,mode,day,sort_order,sets,max,"
            "intensity,reps,repout,start,lift_kind,incr,bodyweight_pct) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["name"], lm, mode, r["day"], r["sort_order"], r["sets"],
             r["max"], r["intensity"], r["reps"], r["repout"], r["start"],
             r["lift_kind"], r["incr"] if "incr" in r.keys() else None, pct))
    conn.execute("DROP TABLE lifts")
    conn.execute("ALTER TABLE lifts_new RENAME TO lifts")
    # lift_state.tier -> mode (rebuild; SQLite can't rename column pre-3.25 reliably)
    st = conn.execute("SELECT * FROM lift_state").fetchall()
    conn.executescript("""
    CREATE TABLE lift_state_new (
        lift_id INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
        mode TEXT NOT NULL, tm REAL, weight REAL, target INTEGER,
        streak INTEGER NOT NULL DEFAULT 0, est1rm REAL,
        reseeded_cycle INTEGER NOT NULL DEFAULT 0);
    """)
    for s in st:
        pct_row = conn.execute("SELECT mode FROM lifts WHERE id=?", (s["lift_id"],)).fetchone()
        conn.execute(
            "INSERT INTO lift_state_new (lift_id,mode,tm,weight,target,streak,est1rm,reseeded_cycle) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (s["lift_id"], pct_row["mode"], s["tm"], s["weight"], s["target"],
             s["streak"], s["est1rm"],
             s["reseeded_cycle"] if "reseeded_cycle" in s.keys() else 0))
    conn.execute("DROP TABLE lift_state")
    conn.execute("ALTER TABLE lift_state_new RENAME TO lift_state")
    conn.commit()
    return len(rows)


def main(db_path="sbs.db", backup_dir="backups"):
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-modes-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")
    from webapp import db
    conn = db.connect(db_path)
    try:
        n = migrate_modes(conn)
    finally:
        conn.close()
    print(f"migrated {n} lift(s) -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_modes")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
