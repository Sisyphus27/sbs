"""Orchestrate the engine over a logged week: DB -> dataclass -> engine -> DB."""
import sqlite3
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState
from sbs_cli.program import advance_lift, _est1rm_from_history
from .. import repo


def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
    )


def _profile_from_rows(settings, lift_rows) -> Profile:
    return Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
        lifts=[_lift_from_row(r) for r in lift_rows],
    )


def _state_from_rows(st_row, hist_rows) -> LiftState:
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"]) for h in hist_rows]
    return LiftState(
        name="", tier=st_row["tier"], tm=st_row["tm"], weight=st_row["weight"],
        target=st_row["target"], streak=st_row["streak"], est1rm=st_row["est1rm"],
        history=history,
    )


def advance_week(conn: sqlite3.Connection, logs: dict) -> int:
    """Run the engine for every lift using this week's logged last-set reps.
    `logs` maps lift_id -> last-set reps (lifts absent from logs are skipped).
    Keyed by row id (not name) so the same exercise can appear on multiple days
    as independent instances."""
    settings = repo.get_settings(conn)
    week = settings["week"]
    lift_rows = repo.list_lifts(conn)
    profile = _profile_from_rows(settings, lift_rows)  # engine reads only globals from it
    for row in lift_rows:
        lid = row["id"]
        actual = logs.get(lid)
        st = repo.get_lift_state(conn, lid)
        ls = _state_from_rows(st, repo.list_history(conn, lid))
        lift = _lift_from_row(row)
        advance_lift(profile, lift, ls, actual, week=week)
        repo.save_lift_state(conn, lid, tier=ls.tier, tm=ls.tm,
                             weight=ls.weight, target=ls.target,
                             streak=ls.streak, est1rm=ls.est1rm)
        if actual is not None and ls.history:
            last = ls.history[-1]
            repo.append_history(conn, lid, week=week, weight=last.weight, reps=last.reps)
    new_week = week + 1
    repo.set_week(conn, new_week)
    return new_week
