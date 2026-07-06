"""21-week schedule editor (main + aux) + reset-to-default."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from sbs_cli.defaults import DEFAULT_SCHEDULE

bp = Blueprint("schedule", __name__)

_KINDS = ("main", "aux")


@bp.route("/schedule")
def view():
    conn = get_db()
    rows = repo.get_schedule(conn)
    by_kind = {k: {} for k in _KINDS}
    for r in rows:
        by_kind[r["kind"]][r["week"]] = r
    return render_template("schedule.html", by_kind=by_kind, kinds=_KINDS,
                           weeks=range(1, 22))


def _parse_form():
    """Collect {kind: {week: (intensity, reps, repout)}} from form fields <kind>_<week>_<field>."""
    out = {k: {} for k in _KINDS}
    for key, val in request.form.items():
        parts = key.split("_")
        if len(parts) != 3:
            continue
        kind, week_s, field = parts
        if kind not in _KINDS or field not in ("intensity", "reps", "repout"):
            continue
        out[kind].setdefault(int(week_s), {})[field] = val
    return out


@bp.route("/schedule", methods=["POST"])
def save():
    conn = get_db()
    parsed = _parse_form()
    # Backfill unedited weeks from existing DB rows so partial submits work.
    existing = {(r["kind"], r["week"]): r for r in repo.get_schedule(conn)}
    new_rows = []
    for kind in _KINDS:
        for week in range(1, 22):
            f = parsed[kind].get(week, {})
            ex = existing.get((kind, week))
            try:
                intensity = float(f.get("intensity", ex["intensity"] if ex else 0))
                reps = int(f.get("reps", ex["reps"] if ex else 0))
                repout = int(f.get("repout", ex["repout"] if ex else 0))
            except ValueError:
                flash(f"非法值: {kind} week {week}")
                return ("bad value", 400)
            if not (0 < intensity < 1) or reps <= 0 or repout <= 0:
                flash(f"范围错误: {kind} week {week} (强度须 0~1, 次数/repout 须 >0)")
                return ("out of range", 400)
            new_rows.append((kind, week, intensity, reps, repout))
    repo.replace_schedule(conn, new_rows)
    flash("进度表已更新")
    return redirect(url_for("schedule.view"))


@bp.route("/schedule/reset", methods=["POST"])
def reset():
    conn = get_db()
    repo.reset_schedule(conn)
    flash("进度表已恢复默认")
    return redirect(url_for("schedule.view"))
