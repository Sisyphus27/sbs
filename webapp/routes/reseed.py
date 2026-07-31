"""Cycle-boundary TM reseed: per-lift, skippable (ADR 0002)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from ..services.reseed import due_lifts
from sbs_cli.engine.progression import cycle_number

bp = Blueprint("reseed", __name__)


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
        flash("max 必须是数字", "error")
        return redirect(url_for("reseed.view"))
    cyc = cycle_number(repo.get_settings(conn)["week"])
    repo.set_reseed(conn, lid, new_max=new_max, cycle=cyc)
    flash("已重测并重置 TM")
    return redirect(url_for("reseed.view"))


@bp.route("/reseed/<int:lid>/skip", methods=["POST"])
def skip(lid):
    conn = get_db()
    cyc = cycle_number(repo.get_settings(conn)["week"])
    repo.set_reseed(conn, lid, cycle=cyc)
    flash("已跳过 (TM 保持当前值)")
    return redirect(url_for("reseed.view"))
