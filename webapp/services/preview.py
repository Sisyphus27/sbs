"""Live (this-week, pre-advance) est1RM preview. Read-only; writes nothing."""
import sqlite3
from sbs_cli.data.schema import SetEntry
from sbs_cli.engine.onerm import estimate_1rm, est1rm_from_history
from sbs_cli.engine.modes import get_mode
from .. import repo
from .rows import lift_from_row, profile_from_rows, state_from_rows


def _working_weight(conn, lift, state, settings, schedule) -> float:
    """This week's working weight via the mode registry (single source, ADR 0005).

    Delegates to ``plan_fields(...)["weight"]`` — the WORKING weight (bodyweight
    term included, ADR 0004) — so no per-mode weight math is re-derived here."""
    profile = profile_from_rows(settings, [], schedule)
    lift_dc = lift_from_row(lift)
    state_dc = state_from_rows(state, repo.list_history(conn, lift["id"]))
    return get_mode(lift["mode"]).plan_fields(profile, lift_dc, state_dc,
                                              settings["week"])["weight"]


def live_preview(conn: sqlite3.Connection, lift_id: int, reps: int) -> dict:
    """Estimate this set's 1RM and the delta vs the historical best est1RM.

    Returns {weight, est1rm, best, delta}; delta/best are None when there is no history.
    """
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    w = _working_weight(conn, lift, state, settings, schedule)
    est = estimate_1rm(w, reps)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    best = est1rm_from_history(history)
    delta = None if best is None else est - best
    return {"weight": w, "est1rm": est, "best": best, "delta": delta}
