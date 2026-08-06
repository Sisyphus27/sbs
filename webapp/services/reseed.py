"""Cycle-boundary TM reseed: which sbs lifts are due at the current week (ADR 0002).

Public service home for the due-lift query — previously a private fn in
routes/reseed.py, imported across blueprints by plan.py and app.py's nav badge."""
import sqlite3
from typing import List, Tuple

from .. import repo
from sbs_cli.engine.progression import schedule_week, cycle_number


def reseed_cycle(week: int):
    """Return the active reseed cycle, or None outside a cycle boundary."""
    if week == 1 or schedule_week(week) != 1:
        return None
    return cycle_number(week)


def due_lifts(conn: sqlite3.Connection) -> Tuple[List[Tuple], int]:
    """sbs lifts due for reseed at the current program week.

    A lift is due iff we're at a cycle boundary beyond cycle 1
    (``schedule_week == 1 AND week > 1``) and the lift's
    ``reseeded_cycle`` stamp hasn't caught up to the current cycle.
    Returns ``(due_list, cycle)`` where ``due_list`` is a list of
    ``(lift_row, state_row)`` tuples (raw sqlite3.Row pairs).
    """
    week = repo.get_settings(conn)["week"]
    cyc = reseed_cycle(week)
    if cyc is None:
        return [], cycle_number(week)
    out = []
    for r in repo.list_training_slots(conn):
        if r["mode"] != "sbs":
            continue
        st = repo.get_training_state(conn, r["id"])
        if (st["reseeded_cycle"] or 0) < cyc:
            out.append((r, st))
    return out, cyc
