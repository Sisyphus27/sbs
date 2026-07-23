"""Mode switch: keep history, recompute est1rm, derive new-mode start state. Read-only."""
import sqlite3
from sbs_cli.data.schema import SetEntry, is_legal_combo
from sbs_cli.program import _est1rm_from_history
from sbs_cli.engine.modes import get_mode
from .. import repo


def derive_state(conn: sqlite3.Connection, lift_id: int, new_mode: str,
                 settings) -> dict:
    """Compute the new-mode starting state from preserved history. Read-only.

    Legal-combo guard (ADR 0005): rejects cross-load_model switches that the
    ``LEGAL_COMBOS`` table forbids (e.g. ``barbell`` lift -> ``none``).
    est1rm is threaded through the working-weight seam (ADR 0004) so a
    pure-bodyweight lift's est1rm reflects bodyweight, not raw added=0.
    Per-mode derivation (ADR 0003 incr snap; ADR 0001 sbs tm seed) is delegated
    to the registered Mode handler via ``derive_on_switch``.
    """
    lift = repo.get_lift(conn, lift_id)
    if not is_legal_combo(lift["load_model"], new_mode):
        raise ValueError(
            f"illegal mode {new_mode} for load_model {lift['load_model']}"
        )
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lift_id)]
    # ADR 0004: history.weight is ADDED weight — thread bodyweight through the
    # working-weight seam so a pure-bodyweight lift (added=0, bw=75, pct=1.0)
    # yields est1rm ~= estimate_1rm(75, reps), NOT ~0.
    pct = lift["bodyweight_pct"] if "bodyweight_pct" in lift.keys() else 0.0
    bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
    est1rm = _est1rm_from_history(hist, bw, pct)
    # Build a Lift dataclass for the handler (handlers read lift.incr / .max /
    # .start / .bodyweight_pct). Circular-safe local import: advance imports
    # nothing from mode at module load time.
    from . import advance as advance_service
    lift_dc = advance_service._lift_from_row(lift)
    # derive_on_switch reads the settings DICT (subscript access, same shape as
    # the rest of the service layer), NOT a Profile dataclass.
    state = get_mode(new_mode).derive_on_switch(lift_dc, hist, settings, est1rm)
    state["est1rm"] = est1rm
    return state


def apply_switch(conn: sqlite3.Connection, lift_id: int, state: dict) -> None:
    """Write the derived state to lifts.mode + lift_state. History is NOT modified."""
    repo.update_lift(conn, lift_id, mode=state["mode"])
    repo.save_lift_state(
        conn, lift_id, mode=state["mode"], tm=state["tm"], weight=state["weight"],
        target=state["target"], streak=state["streak"], est1rm=state["est1rm"],
    )
