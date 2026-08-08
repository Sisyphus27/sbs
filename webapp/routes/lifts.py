"""Lift CRUD: list, create, edit (rename/params/day), delete."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..db import get_db
from .. import repo
from ._forms import present_fields, LIFT_FIELD_CASTS

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
        return None, "Progression step 必须是数字"
    if v <= 0:
        return None, "Progression step 必须大于 0"
    return v, None


@bp.route("/lifts")
def view():
    conn = get_db()
    lifts = repo.list_training_slots(conn)
    settings = repo.get_settings(conn)
    return render_template("lifts.html", lifts=lifts, settings=settings)


@bp.route("/lifts/<int:lid>/row")
def row(lid):
    conn = get_db()
    return render_template("_lift_row.html", lift=repo.get_training_slot(conn, lid))


@bp.route("/lifts/<int:lid>/edit")
def row_edit(lid):
    conn = get_db()
    return render_template(
        "_lift_edit.html", lift=repo.get_training_slot(conn, lid)
    )


@bp.route("/lifts/new", methods=["POST"])
def new():
    conn = get_db()
    name = request.form.get("name", "").strip()
    load_model = request.form.get("load_model", "barbell")
    mode = request.form.get("mode", "")
    from sbs_cli.data.schema import is_legal_combo, LOAD_MODELS
    if load_model not in LOAD_MODELS:
        flash("Load Model 非法", "error")
        return render_template("_lift_row.html", lift=None, error="bad load_model"), 400
    if not is_legal_combo(load_model, mode):
        flash("Load Model 与 Progression Mode 组合非法", "error")
        return render_template("_lift_row.html", lift=None, error="bad combo"), 400
    if not name:
        flash("Lift 名称不能为空", "error")
        return render_template("_lift_row.html", lift=None, error="name required"), 400
    # incr 仅 linear_t2/t3 生效；sbs/none 强制 None（ADR 0005）。
    # 空=None=继承全局；>0 数值；≤0/非数字 拒绝（D7）。
    incr, err = (None, None) if mode in ("sbs", "none") else _parse_incr(request.form.get("incr"))
    if err is not None:
        flash(err, "error")
        return render_template("_lift_row.html", lift=None, error="bad incr"), 400
    # pct 按载荷模型: barbell=0；pure_bodyweight 手填默认 1.0；bodyweight 手填。
    if load_model == "barbell":
        pct = 0.0
    elif load_model == "pure_bodyweight":
        pct = _f("bodyweight_pct", 1.0, float) or 1.0
    else:
        pct = _f("bodyweight_pct", 0.0, float) or 0.0
    try:
        if load_model == "pure_bodyweight":
            lid = repo.create_pure_bodyweight_training_slot(
                conn,
                name=name,
                day=_f("day", 1, int),
                sort_order=999,
                sets=_f("sets", 3, int),
                bodyweight_pct=pct,
            )
            lift = repo.get_training_slot(conn, lid)
        else:
            lid = repo.create_lift(
                conn, name=name, load_model=load_model, mode=mode,
                day=_f("day", 1, int), sort_order=999,
                sets=_f("sets", 3, int), max=_f("max", cast=float),
                intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
                repout=_f("repout", cast=int), start=_f("start", cast=float),
                lift_kind=_f("lift_kind") if mode == "sbs" else None,
                incr=incr, bodyweight_pct=pct)
            lift = repo.get_lift(conn, lid)
    except Exception as e:
        flash(f"创建 Lift 失败: {e}", "error")
        return render_template("_lift_row.html", lift=None, error=str(e)), 400
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/edit", methods=["POST"])
def edit(lid):
    conn = get_db()
    current = repo.get_training_slot(conn, lid)
    if current is None:
        return ("not found", 404)
    # load_model 不可切（ADR 0005）— 不收 load_model 字段。
    # mode 只能走下方独立 preview/apply 路径，普通编辑不解析该字段。
    fields, bad = present_fields(LIFT_FIELD_CASTS)
    if bad is not None:
        flash(f"非法值: {bad}", "error")
        return render_template("_lift_edit.html", lift=current,
                               error=f"非法值: {bad}"), 400
    # incr：表单出现即处理。空串 -> NULL（清除覆盖回全局）；非空 -> 必须 >0 数字（D7）。
    # sbs/none 强制 NULL（与 new() 一致，ADR 0005）。
    # 校验在 update 之前，非法时保留原值并返回 400。
    if "incr" in request.form:
        if current["mode"] in ("sbs", "none"):
            fields["incr"] = None
        else:
            incr, err = _parse_incr(request.form["incr"])
            if err is not None:
                flash(err, "error")
                return render_template(
                    "_lift_edit.html", lift=current, error=err
                ), 400
            fields["incr"] = incr  # None 表示清除并继承全局步进。
    with conn:
        repo.update_training_slot(conn, lid, **fields)
    lift = repo.get_training_slot(conn, lid)
    return render_template("_lift_row.html", lift=lift)


@bp.route("/lifts/<int:lid>/delete", methods=["POST"])
def delete(lid):
    conn = get_db()
    repo.delete_lift(conn, lid)
    return ("", 200)


from ..services import mode as mode_service


@bp.route("/lifts/<int:lid>/mode")
def mode_preview(lid):
    conn = get_db()
    new_mode = request.args.get("mode", "sbs")
    try:
        preview = mode_service.derive_slot_state(
            conn, lid, new_mode, repo.get_settings(conn)
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("lifts.view"))
    lift = repo.get_training_slot(conn, lid)
    return render_template("mode_preview.html", lift=lift, preview=preview)


@bp.route("/lifts/<int:lid>/mode", methods=["POST"])
def mode_apply(lid):
    conn = get_db()
    new_mode = request.form.get("mode", "sbs")
    try:
        preview = mode_service.derive_slot_state(
            conn, lid, new_mode, repo.get_settings(conn)
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("lifts.view"))
    # user may override derived start values
    try:
        if "weight" in request.form and request.form["weight"].strip():
            preview["weight"] = float(request.form["weight"])
        if "tm" in request.form and request.form["tm"].strip():
            preview["tm"] = float(request.form["tm"])
    except ValueError:
        flash("Working Weight / Added weight / Training Max 必须是数字", "error")
        return redirect(url_for("lifts.view"))
    with conn:
        mode_service.apply_slot_switch(conn, lid, preview)
    return redirect(url_for("lifts.view"))
