"""Live (this-week, pre-advance) est1RM preview. Read-only; writes nothing."""
import sqlite3
from sbs_cli.data.schema import SetEntry
from sbs_cli.engine.onerm import estimate_1rm
from sbs_cli.engine.progression import round_weight
from sbs_cli.program import _est1rm_from_history
from .. import repo


def _working_weight(lift, state, settings) -> float:
    """Same working-weight logic as the plan view (sbs = tm*intensity, else state.weight)."""
    if lift["tier"] == "sbs":
        return round_weight((state["tm"] or 0) * (lift["intensity"] or 0.0), settings["rounding"])
    return state["weight"]


def live_preview(conn: sqlite3.Connection, lift_id: int, reps: int) -> dict:
    """Estimate this set's 1RM and the delta vs the historical best est1RM.

    Returns {weight, est1rm, best, delta}; delta/best are None when there is no history.
    """
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    settings = repo.get_settings(conn)
    w = _working_weight(lift, state, settings)
    est = estimate_1rm(w, reps)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    best = _est1rm_from_history(history)
    delta = None if best is None else est - best
    return {"weight": w, "est1rm": est, "best": best, "delta": delta}
