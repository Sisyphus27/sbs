"""Global settings view + update."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo

bp = Blueprint("settings", __name__)

_NUM = {"rounding": float, "incr": float, "t2_reset_pct": float,
        "t2_fail": int, "t3_target": int, "days_per_week": int}


@bp.route("/settings")
def view():
    conn = get_db()
    return render_template("settings.html", s=repo.get_settings(conn))


@bp.route("/settings", methods=["POST"])
def update():
    conn = get_db()
    fields = {}
    for col, cast in _NUM.items():
        if col in request.form and request.form[col].strip():
            try:
                fields[col] = cast(request.form[col])
            except ValueError:
                flash(f"非法值: {col}")
                return redirect(url_for("settings.view"))
    repo.update_settings(conn, **fields)
    flash("参数已更新")
    return redirect(url_for("settings.view"))
