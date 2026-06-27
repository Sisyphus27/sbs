"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from ..db import get_db
from .. import repo
from ..services import advance, tier  # tier imported for completeness; used in lifts route


bp = Blueprint("plan", __name__)


def _by_day(conn):
    from sbs_cli.data.schema import Profile, LiftState
    from sbs_cli.program import week_plan
    settings = repo.get_settings(conn)
    lift_rows = repo.list_lifts(conn)
    profile = Profile(
        rounding=settings["rounding"], days_per_week=settings["days_per_week"],
        incr=settings["incr"], t2_reset_pct=settings["t2_reset_pct"],
        t2_fail=settings["t2_fail"], t3_target=settings["t3_target"],
    )
    from sbs_cli.data.schema import Lift
    lifts = [Lift(name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
                  intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
                  repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"]) for r in lift_rows]
    profile.lifts = lifts
    states = {}
    for r in lift_rows:
        st = repo.get_lift_state(conn, r["id"])
        hist = repo.list_history(conn, r["id"])
        states[r["name"]] = LiftState(
            name=r["name"], tier=st["tier"], tm=st["tm"], weight=st["weight"],
            target=st["target"], streak=st["streak"], est1rm=st["est1rm"])
    from sbs_cli.data.schema import ProgramState
    ps = ProgramState(week=settings["week"], lifts=states)
    by_day = []
    for d in range(1, settings["days_per_week"] + 1):
        items = week_plan(profile, ps, day=d)
        if items:
            by_day.append((d, items))
    return settings["week"], by_day


@bp.route("/")
def view():
    conn = get_db()
    week, by_day = _by_day(conn)
    return render_template("plan.html", week=week, by_day=by_day)


@bp.route("/log", methods=["POST"])
def submit():
    conn = get_db()
    logs = {}
    for key, val in request.form.items():
        if key.startswith("log_") and val.strip():
            name = key[4:]
            try:
                reps = int(val)
            except ValueError:
                flash(f"非法次数: {name} = {val}")
                return redirect(url_for("plan.view"))
            if reps < 0:
                flash(f"次数不能为负: {name}")
                return redirect(url_for("plan.view"))
            logs[name] = reps
    from ..backup import snapshot
    from datetime import datetime, timezone
    settings = repo.get_settings(conn)
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=settings["week"], ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    new_week = advance.advance_week(conn, logs)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))
