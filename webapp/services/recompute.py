"""Recompute a t2/t3 lift's working weight by replaying progression from its
configured start over the immutable history. Triggered when ``start`` is edited
in the lift CRUD (see webapp/routes/lifts.py::edit)."""
import sqlite3
from typing import Optional

from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state, recompute_sbs_tm as _engine_recompute_sbs_tm
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
    profile = advance_service._profile_from_rows(settings, [], repo.load_schedule(conn))
    ls = recompute_state(lift, history, profile)
    repo.save_lift_state(conn, lift_id, tier=ls.tier, tm=None, weight=ls.weight,
                         target=ls.target, streak=ls.streak, est1rm=ls.est1rm)
    return ls


def recompute_sbs_tm(conn: sqlite3.Connection, lift_id: int) -> Optional[float]:
    """Replay an sbs lift's TM from its max over history and write the corrected tm.
    Returns the recomputed TM, or None for non-sbs lifts (no-op). est1rm is
    preserved (it is derived from the immutable history and was never corrupted
    by the TM-rounding bug)."""
    lift_row = repo.get_lift(conn, lift_id)
    if lift_row["tier"] != "sbs":
        return None
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    lift = advance_service._lift_from_row(lift_row)
    schedule = repo.load_schedule(conn)
    tm = _engine_recompute_sbs_tm(lift, history, schedule)
    st = repo.get_lift_state(conn, lift_id)
    repo.save_lift_state(conn, lift_id, tier="sbs", tm=tm, weight=None,
                         target=None, streak=0, est1rm=st["est1rm"])
    return tm
