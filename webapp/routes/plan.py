"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
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
    logged = repo.get_week_logs(conn, settings["week"])
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
        item.logged = logged.get(r["id"], "")
        rows_by_day.setdefault(r["day"], []).append(item)
    by_day = [(d, rows_by_day[d]) for d in sorted(rows_by_day)
              if d <= settings["days_per_week"] and rows_by_day[d]]
    return settings["week"], by_day


@bp.route("/")
def view():
    conn = get_db()
    week, by_day = _by_day(conn)
    return render_template("plan.html", week=week, by_day=by_day)


@bp.route("/log/save", methods=["POST"])
def save_log():
    """Autosave one lift's last-set reps for the week (HTMX, on change). No advance."""
    conn = get_db()
    lid = request.args.get("lid", type=int)
    if lid is None:
        return ("bad lift id", 400)
    raw = (request.form.get(f"log_{lid}") or "").strip()
    week = repo.get_settings(conn)["week"]
    if raw == "":
        repo.clear_one_log(conn, lid, week)
        return ("", 204)
    try:
        reps = int(raw)
    except ValueError:
        return ("bad reps", 400)
    if reps < 0:
        return ("negative", 400)
    repo.save_log(conn, lid, week, reps)
    from ..services.preview import live_preview
    p = live_preview(conn, lid, reps)
    if p["delta"] is None:
        delta_html = '<span class="first">(首次)</span>'
    else:
        cls = "up" if p["delta"] >= 0 else "down"
        sign = "+" if p["delta"] >= 0 else ""
        delta_html = f'<span class="{cls}">{sign}{p["delta"]:.2f}</span>'
    return f'≈{p["est1rm"]:.2f} {delta_html}'


@bp.route("/log", methods=["POST"])
def submit():
    """Advance the week: merge any unsaved form entries into week_log, then run
    the engine over all saved logs, bump week, and clear the week's log."""
    conn = get_db()
    settings = repo.get_settings(conn)
    week = settings["week"]
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
            repo.save_log(conn, lid, week, reps)
    logs = repo.get_week_logs(conn, week)
    from ..backup import snapshot
    from datetime import datetime, timezone
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=week, ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    new_week = advance.advance_week(conn, logs)
    repo.clear_week_logs(conn, week)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))


@bp.route("/export/week.html")
def export_week():
    """Standalone offline HTML of this week's plan + logged progress, for phone viewing.
    Self-contained (no nav/HTMX/server-relative URLs) so it opens offline after copy to phone."""
    conn = get_db()
    week, by_day = _by_day(conn)
    from ..services.preview import live_preview
    for day, items in by_day:
        for it in items:
            if it.logged not in ("", None):
                it.live = live_preview(conn, it.id, int(it.logged))["est1rm"]
            else:
                it.live = None
    html = render_template("week_export.html", week=week, by_day=by_day)
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'})
