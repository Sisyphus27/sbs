"""Plan view + log submit."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from ..db import get_db
from .. import repo
from ..services import advance


bp = Blueprint("plan", __name__)


def _tonnage_html(conn, lid):
    """容量 WoW fragment, or '' if this week's last-set isn't logged yet."""
    from ..services.volume import lift_week_volume
    week = repo.get_settings(conn)["week"]
    this = lift_week_volume(conn, lid, week, is_current=True)
    if this is None:
        return ""
    last = lift_week_volume(conn, lid, week - 1, is_current=False) if week > 1 else None
    kg = f'容量 {this:.0f}kg'
    if not last:  # None (no history) or 0 -> avoid div-by-zero
        return f'{kg} <span class="first">首次</span>'
    pct = (this - last) / last * 100
    if pct >= 0:
        cls, arrow, sign = "up", "↗", "+"
    else:
        cls, arrow, sign = "down", "↘", ""
    return f'{kg} <span class="{cls}">{arrow}{sign}{pct:.0f}%</span>'


def _live_html(conn, lid, reps):
    """.save-ok content: est1RM preview + tonnage WoW. '' when reps is None.

    Single helper used by both _by_day (initial pre-render) and save_log
    (HTMX live refresh), so the est1RM HTML exists in exactly one place.
    """
    if reps is None:
        return ""
    from ..services.preview import live_preview
    p = live_preview(conn, lid, reps)
    if p["delta"] is None:
        delta_html = '<span class="first">(首次)</span>'
    else:
        cls = "up" if p["delta"] >= 0 else "down"
        sign = "+" if p["delta"] >= 0 else ""
        delta_html = f'<span class="{cls}">{sign}{p["delta"]:.2f}</span>'
    return f'≈{p["est1rm"]:.2f} {delta_html} {_tonnage_html(conn, lid)}'.strip()


def _by_day(conn):
    """Group the registry-computed plan items by training day and decorate with
    this week's logged reps + live est1RM HTML. Per-mode weight math lives in
    services.plan (single source over PROGRESSION_REGISTRY); this fn only groups
    and adds per-row log state."""
    from ..services import plan as plan_service
    week, items = plan_service.plan_items(conn)
    logged = repo.get_week_logs(conn, week)
    days_per_week = repo.get_settings(conn)["days_per_week"]
    rows_by_day = {}
    for item in items:
        item.logged = logged.get(item.id, "")
        item.is_logged = item.logged not in (None, "")  # single logged predicate (was 4× in template)
        item.live_html = _live_html(conn, item.id, item.logged if item.is_logged else None)
        rows_by_day.setdefault(item.day, []).append(item)
    by_day = [(d, rows_by_day[d]) for d in sorted(rows_by_day)
              if d <= days_per_week and rows_by_day[d]]
    return week, by_day


@bp.route("/")
def view():
    conn = get_db()
    week, by_day = _by_day(conn)
    from ..routes.reseed import _due_lifts
    due, _cyc = _due_lifts(conn)
    return render_template("plan.html", week=week, by_day=by_day,
                           due_reseeds=[r["name"] for r, _st in due])


@bp.route("/log/save", methods=["POST"])
def save_log():
    """Autosave one lift's last-set reps for the week (HTMX, on change). No advance.

    Owns its single commit (ADR 0009 batch 2): repo.save_log/clear_one_log
    execute only; this is one-logical-write-per-request."""
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
    return _live_html(conn, lid, reps)


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


def _day_states(by_day):
    """Day progress tri-state for the offline export (ADR 0007).

    Returns (days, first_open). days = [(day, state, filled, items)] where state
    is 'full' (all logged), 'part' (some logged — an owed debt, surfaced), or
    'empty' (none logged). first_open = lowest-numbered non-full day (the
    next-to-train); falls back to the last day when all are full. Computed here
    in Python (unit-testable) instead of twice in the template."""
    days = []
    first_open = None
    for day, items in by_day:
        filled = sum(1 for it in items if it.is_logged)
        total = len(items)
        state = "full" if filled == total else ("part" if filled > 0 else "empty")
        if first_open is None and state != "full":
            first_open = day
        days.append((day, state, filled, items))
    if first_open is None and days:
        first_open = days[-1][0]
    return days, first_open


@bp.route("/export/week.html")
def export_week():
    """Standalone offline HTML of this week's plan + logged progress, for phone viewing.
    Self-contained (no nav/HTMX/server-relative URLs) so it opens offline after copy to phone."""
    conn = get_db()
    week, by_day = _by_day(conn)
    days, first_open = _day_states(by_day)
    html = render_template("week_export.html", week=week, days=days, first_open=first_open)
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'})
