"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from ..db import get_db
from .. import repo
from ..services import advance


bp = Blueprint("plan", __name__)


@bp.route("/")
def view():
    from ..services.plan import assemble_by_day
    from ..services.reseed import due_lifts
    conn = get_db()
    week, by_day = assemble_by_day(conn)
    due, _cyc = due_lifts(conn)
    return render_template("plan.html", week=week, by_day=by_day,
                           due_reseeds=[r["name"] for r, _st in due])


@bp.route("/log/save", methods=["POST"])
def save_log():
    """Autosave one lift's last-set reps for the rendered program week.

    Owns its single commit (ADR 0009 batch 2): repo.save_log/clear_one_log
    execute only; the expected-week lock prevents stale-tab writes."""
    from ..services.volume import live_context
    conn = get_db()
    lid = request.args.get("lid", type=int)
    if lid is None:
        return ("bad lift id", 400)
    try:
        expected_week = int(request.form["expected_week"])
    except (KeyError, ValueError):
        return ("bad expected week", 400)
    raw = (request.form.get(f"log_{lid}") or "").strip()
    try:
        reps = int(raw)
    except ValueError:
        if raw != "":
            return ("bad reps", 400)
        reps = None
    if reps is not None and reps < 0:
        return ("negative", 400)
    with conn:
        if not repo.lock_week_if_current(conn, expected_week):
            return ("stale week", 409)
        if reps is None:
            repo.clear_one_log(conn, lid, expected_week)
            return ("", 200)
        repo.save_log(conn, lid, expected_week, reps)
        return render_template("_live_fragment.html", live=live_context(conn, lid, reps))


@bp.route("/log", methods=["POST"])
def submit():
    """Atomically claim and advance the rendered program week, then clear its logs."""
    conn = get_db()
    settings = repo.get_settings(conn)
    week = settings["week"]
    try:
        expected_week = int(request.form["expected_week"])
    except (KeyError, ValueError):
        return ("bad expected week", 400)
    if expected_week != week:
        return ("stale week", 409)
    pending_logs = {}
    for key, val in request.form.items():
        if key.startswith("log_") and val.strip():
            try:
                lid = int(key[4:])
                reps = int(val)
            except ValueError:
                flash(f"非法输入: {key} = {val}", "error")
                return redirect(url_for("plan.view"))
            if reps < 0:
                flash(f"次数不能为负: {key}", "error")
                return redirect(url_for("plan.view"))
            pending_logs[lid] = reps
    from ..backup import snapshot
    from datetime import datetime, timezone
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=week, ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    try:
        with conn:
            new_week = advance.advance_week(
                conn, pending_logs, expected_week=expected_week
            )
            repo.clear_week_logs(conn, week)
    except advance.StaleWeekError:
        return ("stale week", 409)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))


@bp.route("/export/week.html")
def export_week():
    """Standalone offline HTML of this week's plan + logged progress, for phone viewing.
    Self-contained (no nav/HTMX/server-relative URLs) so it opens offline after copy to phone."""
    from ..services.plan import assemble_by_day, day_states
    conn = get_db()
    week, by_day = assemble_by_day(conn)
    days, first_open = day_states(by_day)
    html = render_template("week_export.html", week=week, days=days, first_open=first_open)
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'})
