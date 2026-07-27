"""One-shot migration: bring a live ``sbs.db`` from the pre-schedule schema to the
current one (Tasks 1-6). Adds the ``sbs_schedule`` table + seeds
``DEFAULT_SCHEDULE``; adds ``lifts.lift_kind`` and ``lift_state.reseeded_cycle``
via ``ALTER TABLE``; backfills ``lift_kind`` for sbs lifts (``sets=5`` -> main,
``sets=4`` -> aux); replays every t2 lift's state through the new 1-strike
``t2_next`` via ``recompute_state`` (so an existing t2 history is interpreted
under the current rules). Backs up first.

Idempotent: re-running is a no-op. The schedule seed is guarded by
``COUNT(*) == 0``; both ``ALTER TABLE`` calls are guarded by ``PRAGMA
table_info``; the ``lift_kind`` backfill is guarded by ``IS NULL``; and the t2
replay converges to the same state on every run. Does NOT touch the live
``sbs.db`` except via the explicit ``--db`` flag.

Run:  conda run -n sbs python migrate_schedule.py
      conda run -n sbs python migrate_schedule.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sys
import sqlite3
from datetime import datetime, timezone

from webapp import db, repo
from webapp.services.rows import lift_from_row as _lift_from_row, profile_from_rows as _profile_from_rows
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def _ensure_schedule(conn: sqlite3.Connection) -> None:
    """Create ``sbs_schedule`` if absent and seed ``DEFAULT_SCHEDULE`` if empty.
    Idempotent: re-running does nothing once the 42 rows exist."""
    if not _table_exists(conn, "sbs_schedule"):
        conn.execute(
            """
            CREATE TABLE sbs_schedule (
                kind      TEXT NOT NULL,
                week      INTEGER NOT NULL,
                intensity REAL NOT NULL,
                reps      INTEGER NOT NULL,
                repout    INTEGER NOT NULL,
                PRIMARY KEY (kind, week)
            )
            """
        )
        conn.commit()
    if conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 0:
        from sbs_cli.defaults import DEFAULT_SCHEDULE
        conn.executemany(
            "INSERT INTO sbs_schedule (kind, week, intensity, reps, repout) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r.kind, r.week, r.intensity, r.reps, r.repout) for r in DEFAULT_SCHEDULE],
        )
        conn.commit()


def _add_lift_kind(conn: sqlite3.Connection) -> None:
    """``ALTER TABLE lifts ADD COLUMN lift_kind TEXT``. Idempotent."""
    if not _column_exists(conn, "lifts", "lift_kind"):
        conn.execute("ALTER TABLE lifts ADD COLUMN lift_kind TEXT")
        conn.commit()


def _add_reseeded_cycle(conn: sqlite3.Connection) -> None:
    """``ALTER TABLE lift_state ADD COLUMN reseeded_cycle INTEGER NOT NULL DEFAULT 0``.
    Idempotent."""
    if not _column_exists(conn, "lift_state", "reseeded_cycle"):
        conn.execute(
            "ALTER TABLE lift_state ADD COLUMN reseeded_cycle INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def _backfill_lift_kind(conn: sqlite3.Connection) -> tuple[int, int]:
    """SBS lifts get ``lift_kind`` from ``sets``: 5 -> main, 4 -> aux. The
    ``IS NULL`` guard makes this idempotent (existing classifications stick).
    Returns (n_main, n_aux)."""
    cm = conn.execute(
        "UPDATE lifts SET lift_kind='main' "
        "WHERE mode='sbs' AND sets=5 AND lift_kind IS NULL"
    ).rowcount
    ca = conn.execute(
        "UPDATE lifts SET lift_kind='aux' "
        "WHERE mode='sbs' AND sets=4 AND lift_kind IS NULL"
    ).rowcount
    conn.commit()
    return cm, ca


def _replay_t2(conn: sqlite3.Connection) -> int:
    """Replay every linear_t2 lift's state through the new 1-strike ``t2_next`` via
    ``recompute_state``. Writes via direct ``UPDATE`` on
    (mode, weight, target, streak, est1rm) — does NOT touch ``reseeded_cycle``
    (per ADR 0002 / F1: only ``set_reseed`` and this migration's ALTER + UPDATE
    default write that column). Idempotent: replaying the same history under the
    same profile converges."""
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    # An empty lift list is fine — recompute_state only reads globals + schedule.
    profile = _profile_from_rows(settings, [], schedule)
    n = 0
    for row in repo.list_lifts(conn):
        if row["mode"] != "linear_t2":
            continue
        history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
                   for h in repo.list_history(conn, row["id"])]
        lift = _lift_from_row(row)
        ls = recompute_state(lift, history, profile)
        conn.execute(
            "UPDATE lift_state SET mode=?, weight=?, target=?, streak=?, est1rm=? "
            "WHERE lift_id=?",
            (ls.mode, ls.weight, ls.target, ls.streak, ls.est1rm, row["id"]),
        )
        n += 1
    conn.commit()
    return n


def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-schedule-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        _ensure_schedule(conn)
        _add_lift_kind(conn)
        _add_reseeded_cycle(conn)
        # init_schema is now a safe no-op: every CREATE TABLE IF NOT EXISTS finds
        # the table present, and both seed guards (settings, sbs_schedule) see a
        # non-zero count and skip. Calling it lets a DB that somehow has no
        # settings row be repaired without affecting the migration result.
        db.init_schema(conn)
        n_main, n_aux = _backfill_lift_kind(conn)
        n_t2 = _replay_t2(conn)
    finally:
        conn.close()
    print(
        f"migrated schedule (42 rows), lift_kind ({n_main} main, {n_aux} aux), "
        f"reseeded_cycle (default 0); replayed {n_t2} linear_t2 lifts -> {db_path}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_schedule")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
