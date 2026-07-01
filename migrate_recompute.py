"""One-shot migration: bump t2_reset_pct 0.70 -> 0.75 and resync every t2/t3
lift_state.weight to a replay from its configured start over history. Backs up
the db first. Idempotent (re-running re-derives the same state).

Run:  conda run -n sbs python migrate_recompute.py
      conda run -n sbs python migrate_recompute.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sys
from datetime import datetime, timezone

from webapp import db, repo
from webapp.services import recompute as recompute_service


def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-start-recompute-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        repo.update_settings(conn, t2_reset_pct=0.75)
        print("settings.t2_reset_pct -> 0.75")

        n = 0
        for row in repo.list_lifts(conn):
            if row["tier"] in ("t2", "t3"):
                recompute_service.recompute_on_start_change(conn, row["id"], row["start"])
                n += 1
    finally:
        conn.close()
    print(f"recomputed {n} t2/t3 lifts from start -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_recompute")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
