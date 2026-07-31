"""Per-lift actual tonnage (training volume) for a given program week.

Reads the same DB the plan view reads; computes weight x total reps where
every set but the last is taken at its planned rep count and the last set
uses the logged reps (the 末组 entry). Read-only; writes nothing.
See docs/superpowers/specs/2026-07-15-per-lift-volume-comparison-design.md
"""

import sqlite3
from typing import Optional

from sbs_cli.data.schema import SetEntry
from sbs_cli.engine.load import working_weight
from sbs_cli.engine.progression import lookup_schedule
from sbs_cli.program import recompute_state
from .. import repo
from . import preview
from .rows import lift_from_row, profile_from_rows


def _actual_tonnage(weight: float, sets: int, planned_reps: int, last_set_reps: int) -> float:
    """weight x total reps: (sets-1) sets at planned_reps + last set at last_set_reps."""
    sets = sets or 3
    return weight * ((sets - 1) * planned_reps + last_set_reps)


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
    lift = lift_from_row(lift_row)
    profile = profile_from_rows(settings, [], schedule)
    return recompute_state(lift, hist, profile).target


def lift_week_volume(conn: sqlite3.Connection, lift_id: int, week: int,
                     is_current: bool) -> Optional[float]:
    """Actual tonnage for one lift in one program week.

    weight x ((sets-1) x plannedReps + lastSetReps). Returns None when there
    is no logged last-set reps for that week (current: week_log empty; past:
    no history row) so the caller can skip rendering.
    """
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    mode = lift["mode"]
    sets = lift["sets"] or 3

    if is_current:
        last_set = repo.get_week_logs(conn, week).get(lift_id)
        if last_set is None:
            return None
        weight = preview._working_weight(conn, lift, state, settings, schedule)
    else:
        row = next((h for h in repo.list_history(conn, lift_id) if h["week"] == week), None)
        if row is None:
            return None
        last_set = row["reps"]
        bw = repo.row_get(settings, "bodyweight", 0.0)
        pct = repo.row_get(lift, "bodyweight_pct", 0.0)
        weight = working_weight(row["weight"], bw, pct)

    if mode == "sbs":
        planned = lookup_schedule(schedule, lift["lift_kind"], week).reps
    elif mode == "linear_t3":
        planned = settings["t3_target"]
    else:  # linear_t2
        planned = state["target"] if is_current else _t2_target_as_of(conn, lift_id, week)

    return _actual_tonnage(weight, sets, planned, last_set)


def tonnage_wow(conn: sqlite3.Connection, lift_id: int):
    """This-week tonnage + week-over-week delta for one lift, as data.

    Returns ``{"kg", "pct", "is_first"}`` or ``None`` when this week's last-set
    isn't logged yet. ``pct``/``is_first``: ``is_first`` is True when there is no
    prior-week tonnage (week 1 or no past history); otherwise ``pct`` holds the
    WoW percent (positive = up). Replaces the former HTML f-string in
    routes/plan.py::_tonnage_html — the Jinja partial renders this dict."""
    week = repo.get_settings(conn)["week"]
    this = lift_week_volume(conn, lift_id, week, is_current=True)
    if this is None:
        return None
    last = (lift_week_volume(conn, lift_id, week - 1, is_current=False)
            if week > 1 else None)
    if not last:                       # None (no history) or 0 -> avoid div-by-zero
        return {"kg": this, "pct": None, "is_first": True}
    pct = (this - last) / last * 100
    return {"kg": this, "pct": pct, "is_first": False}


def live_context(conn: sqlite3.Connection, lift_id: int, reps):
    """Compose the live-fragment data: est1RM preview + tonnage WoW.

    Returns ``{"est1rm", "delta", "tonnage"}`` or ``None`` when ``reps`` is None
    (nothing logged). ``tonnage`` is :func:`tonnage_wow` (itself None when this
    week isn't logged). Lives here rather than in preview.py because volume
    already depends on preview (for ``_working_weight``); the reverse import
    would cycle. Replaces routes/plan.py::_live_html's composition."""
    if reps is None:
        return None
    p = preview.live_preview(conn, lift_id, reps)
    return {"est1rm": p["est1rm"], "delta": p["delta"], "tonnage": tonnage_wow(conn, lift_id)}
