"""Per-lift actual tonnage (training volume) for a given program week.

Reads the same DB the plan view reads; computes weight x total reps where
every set but the last is taken at its planned rep count and the last set
uses the logged reps (the 末组 entry). Read-only; writes nothing.
See docs/superpowers/specs/2026-07-15-per-lift-volume-comparison-design.md
"""


def _actual_tonnage(weight: float, sets: int, planned_reps: int, last_set_reps: int) -> float:
    """weight x total reps: (sets-1) sets at planned_reps + last set at last_set_reps."""
    sets = sets or 3
    return weight * ((sets - 1) * planned_reps + last_set_reps)


import sqlite3

from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state
from .. import repo
from . import advance as advance_service


def _t2_target_as_of(conn: sqlite3.Connection, lift_id: int, target_week: int) -> int:
    """t2 target ENTERING target_week = replay history rows with week < target_week.

    Reuses program.recompute_state by feeding it the history filtered to
    week < target_week; it returns the lift state as of that cutoff, whose
    .target is the target used during target_week. Mirrors
    webapp/services/recompute.py::recompute_on_start_change (lifts=[] is safe;
    recompute_state does not iterate profile.lifts). Returns initial 8 when
    there is no prior history.
    """
    lift_row = repo.get_lift(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lift_id) if h["week"] < target_week]
    if not hist:
        return 8  # initial t2 target (see repo._init_lift_state / advance_lift)
    lift = advance_service._lift_from_row(lift_row)
    profile = advance_service._profile_from_rows(settings, [], schedule)
    return recompute_state(lift, hist, profile).target
