"""Recompute a t2/t3 lift's working weight by replaying progression from its
configured start over the immutable history. Triggered when ``start`` is edited
in the lift CRUD (see webapp/routes/lifts.py::edit)."""
import sqlite3

from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state
from .. import repo
from . import advance as advance_service


def recompute_on_start_change(conn: sqlite3.Connection, lift_id: int, new_start: float):
    """Replay t2/t3 progression from ``new_start`` over history and write the
    recomputed ``lift_state``. Returns the recomputed LiftState, or ``None`` for
    sbs lifts (no start-based progression -> no-op)."""
    lift_row = repo.get_lift(conn, lift_id)
    if lift_row["tier"] not in ("t2", "t3"):
        return None
    settings = repo.get_settings(conn)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    lift = advance_service._lift_from_row(lift_row)
    lift.start = new_start  # authoritative; the lifts row already holds it post-update
    profile = advance_service._profile_from_rows(settings, [])  # globals only
    ls = recompute_state(lift, history, profile)
    repo.save_lift_state(conn, lift_id, tier=ls.tier, tm=None, weight=ls.weight,
                         target=ls.target, streak=ls.streak, est1rm=ls.est1rm)
    return ls
