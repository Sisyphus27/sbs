"""One-shot migration: add the nullable ``lifts.incr REAL`` column to a live ``sbs.db``.

The per-lift t2/t3 progression step. NULL = inherit the global ``settings.incr``
(live inheritance — re-read every advance). Existing rows get NULL, so every
existing lift keeps behaving exactly as before (eff_incr falls back to the global).

Idempotent: ``PRAGMA table_info(lifts)`` guards the ALTER — re-running is a no-op
once the column exists. Does NOT touch the live ``sbs.db`` except via the explicit
``--db`` flag. New DBs get the column from ``db.init_schema`` directly.

Run:  conda run -n sbs python migrate_incr.py
      conda run -n sbs python migrate_incr.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sys
import sqlite3
from datetime import datetime, timezone

from webapp import db


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def _add_incr(conn: sqlite3.Connection) -> bool:
    """``ALTER TABLE lifts ADD COLUMN incr REAL``. Idempotent. Returns True if added."""
    if _column_exists(conn, "lifts", "incr"):
        return False
    conn.execute("ALTER TABLE lifts ADD COLUMN incr REAL")
    conn.commit()
    return True


def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-incr-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        added = _add_incr(conn)
    finally:
        conn.close()
    # existing rows are NULL by default of the new nullable column -> inherit global
    print(f"migrated incr ({'added' if added else 'already present'}) -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_incr")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
