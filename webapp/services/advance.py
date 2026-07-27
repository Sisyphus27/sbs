"""Orchestrate the engine over a logged week: DB -> dataclass -> engine -> DB."""
import sqlite3
from sbs_cli.program import advance_lift
from .. import repo
from .rows import lift_from_row, profile_from_rows, state_from_rows


def advance_week(conn: sqlite3.Connection, logs: dict) -> int:
    """Run the engine for every lift using this week's logged last-set reps.
    `logs` maps lift_id -> last-set reps (lifts absent from logs are skipped).
    Keyed by row id (not name) so the same exercise can appear on multiple days
    as independent instances."""
    settings = repo.get_settings(conn)
    week = settings["week"]
    lift_rows = repo.list_lifts(conn)
    schedule = repo.load_schedule(conn)
    profile = profile_from_rows(settings, lift_rows, schedule)  # engine reads globals + schedule
    for row in lift_rows:
        lid = row["id"]
        actual = logs.get(lid)
        st = repo.get_lift_state(conn, lid)
        ls = state_from_rows(st, repo.list_history(conn, lid))
        lift = lift_from_row(row)
        advance_lift(profile, lift, ls, actual, week=week)
        repo.save_lift_state(conn, lid, mode=ls.mode, tm=ls.tm,
                             weight=ls.weight, target=ls.target,
                             streak=ls.streak, est1rm=ls.est1rm)
        if actual is not None and ls.history:
            last = ls.history[-1]
            repo.append_history(conn, lid, week=week, weight=last.weight, reps=last.reps)
    new_week = week + 1
    repo.set_week(conn, new_week)
    return new_week
