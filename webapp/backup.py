"""Snapshot the SQLite db before destructive operations."""
from collections.abc import Callable
from contextlib import closing
import os
import sqlite3
import tempfile


_MAX_BACKUPS = 10


def _integrity_check(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchall()
    if result != [("ok",)]:
        raise RuntimeError(f"backup integrity check failed: {result!r}")


def _remove_candidate(path: str) -> None:
    for candidate in (path, f"{path}-wal", f"{path}-shm"):
        try:
            os.remove(candidate)
        except FileNotFoundError:
            pass


def _prune(dest_dir: str) -> None:
    backups = [
        os.path.join(dest_dir, name)
        for name in os.listdir(dest_dir)
        if name.startswith("sbs-w") and name.endswith(".db.bak")
    ]
    backups.sort(key=lambda path: (os.path.getmtime(path), path), reverse=True)
    for path in backups[_MAX_BACKUPS:]:
        os.remove(path)


def snapshot(src_db: str, *, dest_dir: str, week: int, ts: str) -> str:
    """Create and validate a SQLite snapshot, then retain the latest ten."""
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(src_db):
        raise FileNotFoundError(src_db)
    dest = os.path.join(dest_dir, f"sbs-w{week}-{ts}.db.bak")
    fd, candidate = tempfile.mkstemp(prefix=".sbs-backup-", suffix=".tmp", dir=dest_dir)
    os.close(fd)
    try:
        with closing(sqlite3.connect(src_db)) as source, closing(sqlite3.connect(candidate)) as target:
            source.backup(target)
            _integrity_check(target)
        os.replace(candidate, dest)
    except Exception:
        _remove_candidate(candidate)
        raise
    _prune(dest_dir)
    return dest


def make_snapshot_before_advance(
        src_db: str, *, dest_dir: str, week: int,
        timestamp: Callable[[], str]) -> Callable[[], None]:
    """Bind one pre-advance snapshot callback for the finalization command."""
    def snapshot_before_advance() -> None:
        snapshot(
            src_db,
            dest_dir=dest_dir,
            week=week,
            ts=timestamp(),
        )

    return snapshot_before_advance
