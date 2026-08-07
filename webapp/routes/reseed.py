"""Cycle-boundary TM reseed: per-lift, skippable (ADR 0002)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from ..services.reseed import due_lifts, reseed_cycle

bp = Blueprint("reseed", __name__)


def _current_reseed_cycle(conn):
    week = repo.get_settings(conn)["week"]
    return reseed_cycle(week)


@bp.route("/reseed")
def view():
    conn = get_db()
    due, cyc = due_lifts(conn)
    return render_template("reseed.html", due=due, cycle=cyc)


@bp.route("/reseed/<int:lid>", methods=["POST"])
def apply(lid):
    conn = get_db()
    raw = (request.form.get("max") or "").strip()
    try:
        new_max = float(raw)
    except ValueError:
        flash("Training Max 必须是数字", "error")
        return redirect(url_for("reseed.view"))
    cyc = _current_reseed_cycle(conn)
    if cyc is None:
        flash("当前不在 Reseed 周期点", "error")
        return redirect(url_for("reseed.view"))
    try:
        with conn:
            repo.set_training_reseed(conn, lid, new_max=new_max, cycle=cyc)
    except ValueError:
        flash("只有 sbs Lift 可以应用 Reseed", "error")
        return redirect(url_for("reseed.view"))
    flash("Reseed 已应用，Training Max 已更新")
    return redirect(url_for("reseed.view"))


@bp.route("/reseed/<int:lid>/skip", methods=["POST"])
def skip(lid):
    conn = get_db()
    cyc = _current_reseed_cycle(conn)
    if cyc is None:
        flash("当前不在 Reseed 周期点", "error")
        return redirect(url_for("reseed.view"))
    try:
        with conn:
            repo.set_training_reseed(conn, lid, cycle=cyc)
    except ValueError:
        flash("只有 sbs Lift 可以应用 Reseed", "error")
        return redirect(url_for("reseed.view"))
    flash("已跳过本次 Reseed（Training Max 保持当前值）")
    return redirect(url_for("reseed.view"))
