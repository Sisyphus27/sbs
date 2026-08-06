"""Mode switch: keep history, recompute est1rm, derive new-mode start state. Read-only."""
import sqlite3
from sbs_cli.data.schema import SetEntry, is_legal_combo
from sbs_cli.engine.onerm import est1rm_from_history
from sbs_cli.engine.modes import get_mode
from .. import repo
from .rows import lift_from_row


def _derive_start(lift, new_mode: str, settings, est1rm) -> dict:
    if not is_legal_combo(lift["load_model"], new_mode):
        raise ValueError(
            f"illegal mode {new_mode} for load_model {lift['load_model']}"
        )
    lift_dc = lift_from_row(lift)
    state = get_mode(new_mode).derive_on_switch(
        lift_dc, [], settings, est1rm
    )
    state["est1rm"] = est1rm
    return state


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
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lift_id)]
    # ADR 0004: history.weight is ADDED weight — thread bodyweight through the
    # working-weight seam so a pure-bodyweight lift (added=0, bw=75, pct=1.0)
    # yields est1rm ~= estimate_1rm(75, reps), NOT ~0.
    pct = repo.row_get(lift, "bodyweight_pct", 0.0)
    bw = repo.row_get(settings, "bodyweight", 0.0)
    est1rm = est1rm_from_history(hist, bw, pct)
    return _derive_start(lift, new_mode, settings, est1rm)


def derive_slot_state(conn: sqlite3.Connection, slot_id: int, new_mode: str,
                      settings) -> dict:
    """Preview a v1 slot's new state without writing either side of the pair."""
    slot = repo.get_training_slot(conn, slot_id)
    current_state = repo.get_training_state(conn, slot_id)
    if slot is None or current_state is None:
        raise ValueError("unknown training slot")
    return _derive_start(slot, new_mode, settings, current_state["est1rm"])


def apply_switch(conn: sqlite3.Connection, lift_id: int, state: dict) -> None:
    """Write the derived state to lifts.mode + lift_state. History is NOT modified."""
    repo.update_lift(conn, lift_id, mode=state["mode"])
    repo.save_lift_state(
        conn, lift_id, mode=state["mode"], tm=state["tm"], weight=state["weight"],
        target=state["target"], streak=state["streak"], est1rm=state["est1rm"],
    )


def apply_slot_switch(conn: sqlite3.Connection, slot_id: int, state: dict) -> None:
    """Write a v1 mode switch; the route owns the single transaction."""
    repo.switch_training_mode(
        conn,
        slot_id,
        mode=state["mode"],
        tm=state["tm"],
        weight=state["weight"],
        target=state["target"],
        streak=state["streak"],
        est1rm=state["est1rm"],
    )
