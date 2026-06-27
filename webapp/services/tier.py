"""Tier switch: keep history, recompute est1rm, derive new-tier start state."""
import sqlite3
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import _est1rm_from_history
from sbs_cli.engine.progression import round_weight
from .. import repo


def derive_state(conn: sqlite3.Connection, lift_id: int, new_tier: str,
                 settings) -> dict:
    """Compute the new-tier starting state from preserved history. Read-only."""
    if new_tier not in ("sbs", "t2", "t3"):
        raise ValueError(f"unknown tier: {new_tier}")
    hist_rows = repo.list_history(conn, lift_id)
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"]) for h in hist_rows]
    est1rm = _est1rm_from_history(history)
    lift = repo.get_lift(conn, lift_id)
    quantum = settings["rounding"]

    if new_tier == "sbs":
        tm = est1rm if est1rm is not None else (lift["max"] or 0.0)
        return {"tier": "sbs", "tm": tm, "weight": None, "target": None,
                "streak": 0, "est1rm": est1rm}
    if new_tier == "t2":
        if est1rm is not None:
            w = round_weight(est1rm * settings["t2_reset_pct"], quantum)
        else:
            w = lift["start"] or 0.0
        return {"tier": "t2", "tm": None, "weight": w, "target": 10,
                "streak": 0, "est1rm": est1rm}
    # t3
    if est1rm is not None:
        w = round_weight(est1rm * 0.6, quantum)
    else:
        w = lift["start"] or 0.0
    return {"tier": "t3", "tm": None, "weight": w, "target": None,
            "streak": 0, "est1rm": est1rm}


def apply_switch(conn: sqlite3.Connection, lift_id: int, state: dict) -> None:
    """Write the derived state to lifts.tier + lift_state. History is NOT modified."""
    repo.update_lift(conn, lift_id, tier=state["tier"])
    repo.save_lift_state(
        conn, lift_id, tier=state["tier"], tm=state["tm"], weight=state["weight"],
        target=state["target"], streak=state["streak"], est1rm=state["est1rm"],
    )
