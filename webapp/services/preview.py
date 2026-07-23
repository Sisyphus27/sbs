"""Live (this-week, pre-advance) est1RM preview. Read-only; writes nothing."""
import sqlite3
from sbs_cli.data.schema import SetEntry
from sbs_cli.engine.onerm import estimate_1rm
from sbs_cli.engine.progression import round_weight, lookup_schedule
from sbs_cli.engine.load import working_weight
from sbs_cli.program import _est1rm_from_history
from .. import repo


def _working_weight(lift, state, settings, schedule) -> float:
    """Same working-weight logic as the plan view, routed through the
    ``working_weight`` seam (ADR 0004).

    - sbs: ``round_weight((state.tm or 0) * intensity, rounding)`` — intensity
      comes from sbs_schedule (single loader) keyed by (lift_kind, program week);
      the lifts.intensity column is a stale seed, ignored at read.
    - t2/t3: ``working_weight(state.weight or 0, bodyweight, bodyweight_pct)`` —
      bodyweight term is added back in for bodyweight lifts (pull-up/dip), zero
      for ordinary lifts so legacy behavior is unchanged.
    """
    if lift["mode"] == "sbs":
        sc = lookup_schedule(schedule, lift["lift_kind"], settings["week"])
        return round_weight((state["tm"] or 0) * sc.intensity, settings["rounding"])
    bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
    pct = lift["bodyweight_pct"] if "bodyweight_pct" in lift.keys() else 0.0
    return working_weight(state["weight"] or 0.0, bw, pct)


def live_preview(conn: sqlite3.Connection, lift_id: int, reps: int) -> dict:
    """Estimate this set's 1RM and the delta vs the historical best est1RM.

    Returns {weight, est1rm, best, delta}; delta/best are None when there is no history.
    """
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    w = _working_weight(lift, state, settings, schedule)
    est = estimate_1rm(w, reps)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    best = _est1rm_from_history(history)
    delta = None if best is None else est - best
    return {"weight": w, "est1rm": est, "best": best, "delta": delta}
