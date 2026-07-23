"""One-shot migration: recompute every sbs lift's stored TM by replaying from its
``lifts.max`` over the immutable history, RAW (no rounding). Fixes TMs rounded
under the old bug. Backs up the db first. Idempotent (re-running replays the
same history to the same raw TM). Non-sbs lifts are skipped.

Run:  conda run -n sbs python migrate_sbs_tm.py
      conda run -n sbs python migrate_sbs_tm.py --db sbs.db --backup-dir backups
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
    bak = os.path.join(backup_dir, f"sbs-tm-recompute-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        n = 0
        for row in repo.list_lifts(conn):
            if row["mode"] == "sbs" and \
               recompute_service.recompute_sbs_tm(conn, row["id"]) is not None:
                n += 1
    finally:
        conn.close()
    print(f"recomputed {n} sbs lift TMs from max -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_sbs_tm")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
