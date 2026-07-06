"""Cycle-boundary TM reseed: per-lift, skippable (ADR 0002)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from sbs_cli.engine.progression import schedule_week, cycle_number

bp = Blueprint("reseed", __name__)


def _due_lifts(conn):
    """sbs lifts due for reseed at the current program week.

    A lift is due iff we're at a cycle boundary beyond cycle 1
    (``schedule_week == 1 AND week > 1``) and the lift's
    ``reseeded_cycle`` stamp hasn't caught up to the current cycle.
    Returns ``(due_list, cycle)`` where ``due_list`` is a list of
    ``(lift_row, state_row)`` tuples.
    """
    week = repo.get_settings(conn)["week"]
    if schedule_week(week) != 1 or week == 1:
        return [], cycle_number(week)
    cyc = cycle_number(week)
    out = []
    for r in repo.list_lifts(conn):
        if r["tier"] != "sbs":
            continue
        st = repo.get_lift_state(conn, r["id"])
        if (st["reseeded_cycle"] or 0) < cyc:
            out.append((r, st))
    return out, cyc


@bp.route("/reseed")
def view():
    conn = get_db()
    due, cyc = _due_lifts(conn)
    return render_template("reseed.html", due=due, cycle=cyc)


@bp.route("/reseed/<int:lid>", methods=["POST"])
def apply(lid):
    conn = get_db()
    raw = (request.form.get("max") or "").strip()
    try:
        new_max = float(raw)
    except ValueError:
        flash("max 必须是数字")
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
