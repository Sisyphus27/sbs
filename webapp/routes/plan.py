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
    """Autosave one lift's last-set reps for the week (HTMX, on change). No advance.

    Owns its single commit (ADR 0009 batch 2): repo.save_log/clear_one_log
    execute only; this is one-logical-write-per-request."""
    from ..services.volume import live_context
    conn = get_db()
    lid = request.args.get("lid", type=int)
    if lid is None:
        return ("bad lift id", 400)
    raw = (request.form.get(f"log_{lid}") or "").strip()
    week = repo.get_settings(conn)["week"]
    if raw == "":
        repo.clear_one_log(conn, lid, week)
        conn.commit()
        return ("", 200)
    try:
        reps = int(raw)
    except ValueError:
        return ("bad reps", 400)
    if reps < 0:
        return ("negative", 400)
    repo.save_log(conn, lid, week, reps)
    conn.commit()
    return render_template("_live_fragment.html", live=live_context(conn, lid, reps))


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
                flash(f"非法输入: {key} = {val}", "error")
                return redirect(url_for("plan.view"))
            if reps < 0:
                flash(f"次数不能为负: {key}", "error")
                return redirect(url_for("plan.view"))
            repo.save_log(conn, lid, week, reps)
    logs = repo.get_week_logs(conn, week)
    from ..backup import snapshot
    from datetime import datetime, timezone
    snapshot(current_app.config["DB_PATH"], dest_dir=current_app.config["BACKUP_DIR"],
             week=week, ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    new_week = advance.advance_week(conn, logs)
    repo.clear_week_logs(conn, week)
    conn.commit()                  # ADR 0009 batch 2: clear_week_logs no longer self-commits
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
