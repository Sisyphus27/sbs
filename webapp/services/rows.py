"""Row → engine-dataclass converters (sqlite3.Row → Lift / Profile / LiftState).

Single home for the translation every service needs. Previously these lived as
underscore-``_private`` helpers inside ``advance.py`` and were poked at by
volume / recompute / mode (mode even used a function-local import to dodge the
resulting cycle). Now public and neutral: any service imports from here.
"""
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState
from .. import repo


def lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], day=r["day"],
        load_model=r["load_model"], mode=r["mode"],
        max=r["max"], intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"],
        incr=repo.row_get(r, "incr"),
        bodyweight_pct=repo.row_get(r, "bodyweight_pct", 0.0),
    )


def profile_from_rows(settings, lift_rows, schedule) -> Profile:
    return Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
        bodyweight=repo.row_get(settings, "bodyweight", 0.0),
        lifts=[lift_from_row(r) for r in lift_rows],
        schedule=schedule,
    )


def state_from_rows(st_row, hist_rows) -> LiftState:
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"]) for h in hist_rows]
    return LiftState(
        name="", mode=st_row["mode"], tm=st_row["tm"], weight=st_row["weight"],
        target=st_row["target"], streak=st_row["streak"], est1rm=st_row["est1rm"],
        history=history,
    )
