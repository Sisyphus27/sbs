"""Lift CRUD: list, create, edit (rename/params/day), delete."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo

bp = Blueprint("lifts", __name__)


def _f(name, default=None, cast=str):
    v = request.form.get(name, default)
    if v in (None, ""):
        return None
    return cast(v)


@bp.route("/lifts")
def view():
    conn = get_db()
    lifts = repo.list_lifts(conn)
    settings = repo.get_settings(conn)
    return render_template("lifts.html", lifts=lifts, settings=settings)


@bp.route("/lifts/new", methods=["POST"])
def new():
    conn = get_db()
    name = request.form.get("name", "").strip()
    tier = request.form.get("tier", "sbs")
    if tier not in ("sbs", "t2", "t3"):
        flash("tier 必须是 sbs / t2 / t3")
        return render_template("_lift_row.html", lift=None, error="bad tier"), 400
    if not name:
        flash("动作名不能为空")
        return render_template("_lift_row.html", lift=None, error="name required"), 400
    try:
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float))
    except Exception as e:
        flash(f"创建失败: {e}")
        return render_template("_lift_row.html", lift=None, error=str(e)), 400
    lift = repo.get_lift(conn, lid)
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/edit", methods=["POST"])
def edit(lid):
    conn = get_db()
    fields = {}
    for col, cast in (("name", str), ("tier", str), ("day", int), ("sets", int),
                      ("max", float), ("intensity", float), ("reps", int),
                      ("repout", int), ("start", float)):
        if col in request.form and request.form[col].strip() != "":
            fields[col] = cast(request.form[col])
    repo.update_lift(conn, lid, **fields)
    lift = repo.get_lift(conn, lid)
    # start is the progression basis for t2/t3: replay from the new start over
    # history to resync the working weight. Idempotent (no-op effect if start
    # unchanged). sbs has no start-based progression -> skipped.
    if lift["tier"] in ("t2", "t3") and "start" in fields:
        from ..services import recompute as recompute_service
        recompute_service.recompute_on_start_change(conn, lid, lift["start"])
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/delete", methods=["POST"])
def delete(lid):
    conn = get_db()
    repo.delete_lift(conn, lid)
    return ("", 200)


from ..services import tier as tier_service


@bp.route("/lifts/<int:lid>/tier")
def tier_preview(lid):
    conn = get_db()
    new_tier = request.args.get("tier", "sbs")
    preview = tier_service.derive_state(conn, lid, new_tier, repo.get_settings(conn))
    lift = repo.get_lift(conn, lid)
    return render_template("tier_preview.html", lift=lift, preview=preview)


@bp.route("/lifts/<int:lid>/tier", methods=["POST"])
def tier_apply(lid):
    conn = get_db()
    new_tier = request.form.get("tier", "sbs")
    preview = tier_service.derive_state(conn, lid, new_tier, repo.get_settings(conn))
    # user may override derived start values
    try:
        if "weight" in request.form and request.form["weight"].strip():
            preview["weight"] = float(request.form["weight"])
        if "tm" in request.form and request.form["tm"].strip():
            preview["tm"] = float(request.form["tm"])
    except ValueError:
        flash("重量 / TM 必须是数字")
        return redirect(url_for("lifts.view"))
    tier_service.apply_switch(conn, lid, preview)
    return redirect(url_for("lifts.view"))
