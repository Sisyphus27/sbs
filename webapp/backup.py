"""Snapshot the SQLite db before destructive operations."""
import os
import shutil
from typing import Optional


def snapshot(src_db: str, *, dest_dir: str, week: int, ts: str) -> str:
    """Copy src_db to dest_dir/sbs-w<week>-<ts>.db.bak. Creates dest_dir. Returns dest path."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"sbs-w{week}-{ts}.db.bak")
    shutil.copy2(src_db, dest)
    return dest
