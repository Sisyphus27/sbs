"""Lift CRUD: list, create, edit (rename/params/day), delete."""
from flask import Blueprint, render_template, request, flash
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
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/delete", methods=["POST"])
def delete(lid):
    conn = get_db()
    repo.delete_lift(conn, lid)
    return ("", 200)
