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


def _parse_incr(raw: str):
    """Parse the incr form field. Returns (value, error).

    value: None (empty -> NULL / inherit global), a positive float, or None-with-error.
    error: None on success, a flash message string on validation failure."""
    raw = (raw or "").strip()
    if raw == "":
        return None, None
    try:
        v = float(raw)
    except ValueError:
        return None, "incr 必须是数字"
    if v <= 0:
        return None, "incr 必须大于 0"
    return v, None


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
    # incr 仅 t2/t3 生效；sbs 强制 None（D5）。空=None=继承全局；>0 数值；≤0/非数字 拒绝（D7）。
    incr, err = (None, None) if tier == "sbs" else _parse_incr(request.form.get("incr"))
    if err is not None:
        flash(err)
        return render_template("_lift_row.html", lift=None, error="bad incr"), 400
    try:
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float),
            lift_kind=_f("lift_kind") if tier == "sbs" else None, incr=incr,
            bodyweight_pct=_f("bodyweight_pct", 0.0, float) or 0.0,
            progression=request.form.get("progression", "weight"))
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
                      ("repout", int), ("start", float), ("lift_kind", str),
                      ("bodyweight_pct", float), ("progression", str)):
        if col in request.form and request.form[col].strip() != "":
            fields[col] = cast(request.form[col])
    # incr：表单出现即处理。空串 -> NULL（清除覆盖回全局）；非空 -> 必须 >0 数字（D7）。
    # 校验在 update 之前，非法时保留原值并返回 400。
    if "incr" in request.form:
        incr, err = _parse_incr(request.form["incr"])
        if err is not None:
            flash(err)
            return render_template("_lift_row.html", lift=repo.get_lift(conn, lid),
                                   error="bad incr"), 400
        fields["incr"] = incr  # None 表示清除（update_lift 经 _LIFT_COLS 支持 incr=None）
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
