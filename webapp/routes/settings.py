"""Global settings view + update."""
from flask import Blueprint, render_template, redirect, url_for, flash
from sbs_cli.defaults import DEFAULT_SETTINGS, RESETTABLE_FIELDS
from ..db import get_db
from .. import repo
from ._forms import present_fields

bp = Blueprint("settings", __name__)

_NUM = {"rounding": float, "incr": float, "t2_reset_pct": float,
        "t2_fail": int, "t3_target": int, "days_per_week": int,
        "bodyweight": float}


@bp.route("/settings")
def view():
    conn = get_db()
    return render_template("settings.html", s=repo.get_settings(conn))


@bp.route("/settings", methods=["POST"])
def update():
    conn = get_db()
    fields, bad = present_fields(_NUM)
    if bad is not None:
        flash(f"非法值: {bad}", "error")
        return redirect(url_for("settings.view"))
    repo.update_settings(conn, **fields)
    flash("Settings 已更新")
    return redirect(url_for("settings.view"))


@bp.route("/settings/<field>/reset", methods=["POST"])
def reset_field(field):
    """Restore a single non-weight setting to its default.

    Weight settings (rounding, incr) are intentionally excluded — they have no
    system default, so the route 404s for them just like for any unknown field.
    """
    if field not in RESETTABLE_FIELDS:
        return ("not resettable", 404)
    repo.update_settings(get_db(), **{field: DEFAULT_SETTINGS[field]})
    flash(f"{field} 已恢复默认 ({DEFAULT_SETTINGS[field]})")
    return redirect(url_for("settings.view"))
