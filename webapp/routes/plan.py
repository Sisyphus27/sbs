"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from ..db import get_db
from .. import repo
from ..services import advance, tier  # tier imported for completeness; used in lifts route


bp = Blueprint("plan", __name__)


def _by_day(conn):
    # NOTE: the engine's week_plan() looks state up by lift NAME, so it cannot
    # distinguish two rows that share a name (e.g. Face Pull on day 2 and day 4).
    # Build display rows directly, keyed by row id, mirroring week_plan's field
    # mapping. Each item carries its id so the log form targets the right row.
    from types import SimpleNamespace
    from sbs_cli.engine.progression import round_weight
    settings = repo.get_settings(conn)
    lift_rows = repo.list_lifts(conn)
    rows_by_day = {}
    for r in lift_rows:
        st = repo.get_lift_state(conn, r["id"])
        est1rm = st["est1rm"]
        if r["tier"] == "sbs":
            w = round_weight((st["tm"] or 0) * (r["intensity"] or 0.0), settings["rounding"])
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="sbs", weight=w,
                                   reps=r["reps"], sets=r["sets"], repout=r["repout"],
                                   target=None, streak=0, est1rm=est1rm)
        elif r["tier"] == "t2":
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="t2", weight=st["weight"],
                                   reps=st["target"], sets=r["sets"], repout=None,
                                   target=st["target"], streak=st["streak"], est1rm=est1rm)
        else:  # t3
            item = SimpleNamespace(id=r["id"], name=r["name"], tier="t3", weight=st["weight"],
                                   reps=settings["t3_target"], sets=r["sets"], repout=None,
                                   target=settings["t3_target"], streak=0, est1rm=est1rm)
        rows_by_day.setdefault(r["day"], []).append(item)
    by_day = [(d, rows_by_day[d]) for d in sorted(rows_by_day)
              if d <= settings["days_per_week"] and rows_by_day[d]]
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
            try:
                lid = int(key[4:])
                reps = int(val)
            except ValueError:
                flash(f"非法输入: {key} = {val}")
                return redirect(url_for("plan.view"))
            if reps < 0:
                flash(f"次数不能为负: {key}")
                return redirect(url_for("plan.view"))
            logs[lid] = reps
    from ..backup import snapshot
    from datetime import datetime, timezone
    settings = repo.get_settings(conn)
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=settings["week"], ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    new_week = advance.advance_week(conn, logs)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))
