"""Plan view + log submit."""
from types import SimpleNamespace

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from .. import repo
from ..db import get_db
from ..services.training import (
    StaleTrainingWeekError,
    TrainingInputError,
    finalize_week,
    preview_progression,
    review_week_settlement,
    save_draft_set,
    training_history,
    training_plan,
)
from ._forms import skipped_slot_ids


bp = Blueprint("plan", __name__)


def _v1_current_facts(history, expected_week):
    return {
        (row["slot_id"], row["set_number"]): row
        for row in history
        if row["program_week"] == expected_week
    }


def _comparison_metric(current, previous, *, percent):
    if current is None:
        return None
    if previous in (None, 0):
        return SimpleNamespace(value=current, delta=None, is_first=True)
    delta = ((current - previous) / previous * 100
             if percent else current - previous)
    return SimpleNamespace(value=current, delta=delta, is_first=False)


def _draft_set_fields(fact, slot, set_number):
    return {
        "actual_added_weight": (
            fact["actual_added_weight"]
            if fact is not None and fact["actual_added_weight"] is not None
            else slot["planned_added_weight"]
        ),
        "warmup": bool(fact["warmup"]) if fact is not None else False,
        "drives_progression": (
            bool(fact["drives_progression"])
            if fact is not None
            else set_number == slot["planned_sets"]
        ),
        "e1rm_qualified": (
            bool(fact["e1rm_qualified"])
            if fact is not None
            else False
        ),
    }


def _v1_comparisons(history, expected_week):
    summaries = {}
    for row in history:
        if row["program_week"] not in (expected_week - 1, expected_week):
            continue
        key = (row["program_week"], row["slot_id"])
        summary = summaries.setdefault(
            key, {"volume": row["recorded_volume"], "e1rm": None, "has_driver": False}
        )
        summary["volume"] = row["recorded_volume"]
        if row["drives_progression"] and not row["warmup"]:
            summary["has_driver"] = True
            if row["mode"] is not None:
                summary["e1rm"] = row["display_e1rm"]

    comparisons = {}
    current_slots = {
        slot_id for week, slot_id in summaries if week == expected_week
    }
    for slot_id in current_slots:
        current = summaries[(expected_week, slot_id)]
        previous = summaries.get((expected_week - 1, slot_id), {})
        volume = _comparison_metric(
            current["volume"], previous.get("volume"), percent=True
        )
        e1rm = (
            _comparison_metric(
                current["e1rm"], previous.get("e1rm"), percent=False
            )
            if current["has_driver"]
            else None
        )
        if volume is not None or e1rm is not None:
            comparisons[slot_id] = SimpleNamespace(volume=volume, e1rm=e1rm)
    return comparisons


def _candidate_preview(conn, *, expected_week, slot_id, set_number,
                       actual_added_weight, reps, warmup,
                       drives_progression, e1rm_qualified):
    try:
        preview = preview_progression(
            conn,
            expected_week=expected_week,
            slot_id=slot_id,
            set_number=set_number,
            actual_added_weight=actual_added_weight,
            reps=reps,
            warmup=warmup,
            drives_progression=drives_progression,
            e1rm_qualified=e1rm_qualified,
        )
    except StaleTrainingWeekError:
        return None, ("stale week", 409)
    except TrainingInputError as error:
        return None, (str(error), 400)
    except Exception:
        current_app.logger.exception("progression preview failed")
        return None, ("preview failed", 500)
    preview["comparison"] = _v1_comparisons(
        preview.pop("performance_rows"), expected_week
    ).get(slot_id)
    return preview, None


def _v1_plan_by_day(conn):
    plan = training_plan(conn)
    expected_week = plan["expected_week"]
    days_per_week = repo.get_settings(conn)["days_per_week"]
    history = training_history(conn)
    facts = _v1_current_facts(history, expected_week)
    rows_by_day = {}
    for slot in plan["slots"]:
        if not 1 <= slot["day"] <= days_per_week:
            continue
        set_entries = []
        for set_number in range(1, slot["planned_sets"] + 1):
            fact = facts.get((slot["slot_id"], set_number))
            set_entries.append(
                SimpleNamespace(
                    number=set_number,
                    reps=None if fact is None else fact["reps"],
                    actual_added_weight=(
                        None if fact is None else fact["actual_added_weight"]
                    ),
                    actual_working_weight=(
                        None if fact is None else fact["actual_working_weight"]
                    ),
                    is_last=set_number == slot["planned_sets"],
                    confirmed=(
                        fact is not None
                        and fact["actual_added_weight"] is not None
                        and fact["mode"] == slot["mode"]
                    ),
                    warmup=bool(fact["warmup"]) if fact is not None else False,
                    drives_progression=(
                        bool(fact["drives_progression"])
                        if fact is not None else False
                    ),
                )
            )
        final_entry = set_entries[-1]
        progression_driver = next((
            entry for entry in set_entries
            if entry.confirmed and not entry.warmup and entry.drives_progression
        ), None)
        actual_added_weight = (
            final_entry.actual_added_weight
            if final_entry.actual_added_weight is not None
            else slot["planned_added_weight"]
        )
        if slot["load_model"] == "pure_bodyweight":
            actual_added_weight = 0
        if final_entry.reps is None:
            working_weight_kind = "Planned"
            current_working_weight = slot["planned_working_weight"]
        else:
            working_weight_kind = "Actual"
            current_working_weight = final_entry.actual_working_weight
        item = SimpleNamespace(
            id=slot["slot_id"],
            name=slot["name"],
            mode=slot["mode"],
            load_model=slot["load_model"],
            day=slot["day"],
            weight=slot["planned_added_weight"],
            working_weight=slot["planned_working_weight"],
            actual_added_weight=actual_added_weight,
            current_working_weight=current_working_weight,
            working_weight_kind=working_weight_kind,
            is_bodyweight=slot["load_model"] in ("bodyweight", "pure_bodyweight"),
            reps=slot["planned_reps"],
            sets=slot["planned_sets"],
            repout=slot["planned_repout"],
            target=slot["planned_target"],
            streak=slot["state_streak"],
            set_entries=set_entries,
            is_logged=final_entry.reps is not None,
            is_settlement_ready=progression_driver is not None,
            is_zero=(
                progression_driver is not None
                and progression_driver.reps == 0
            ),
        )
        rows_by_day.setdefault(item.day, []).append(item)
    return expected_week, [
        (day, rows_by_day[day]) for day in sorted(rows_by_day)
    ]


@bp.route("/")
def view():
    from ..services.reseed import due_lifts
    conn = get_db()
    week, by_day = _v1_plan_by_day(conn)
    items = [item for _day, day_items in by_day for item in day_items]
    handled_count = sum(item.is_settlement_ready for item in items)
    due, _cyc = due_lifts(conn)
    return render_template("plan.html", week=week, by_day=by_day,
                           due_reseeds=[r["name"] for r, _st in due],
                           handled_count=handled_count,
                           total_count=len(items))


@bp.route("/log/save", methods=["POST"])
def save_log():
    """Autosave one displayed work set through the v1 training command."""
    conn = get_db()
    lid = request.args.get("lid", type=int)
    set_number = request.args.get("set_number", type=int)
    if lid is None or set_number is None:
        return ("bad slot or set number", 400)
    try:
        expected_week = int(request.form["expected_week"])
        reps = int(
            request.form.get(
                f"set_{lid}_{set_number}", request.form.get("reps")
            )
        )
    except (KeyError, TypeError, ValueError):
        if "expected_week" not in request.form:
            return ("bad expected week", 400)
        return ("bad reps", 400)
    plan = training_plan(conn)
    slot = next(
        (item for item in plan["slots"] if item["slot_id"] == lid), None
    )
    if slot is None:
        return ("unknown training slot", 400)
    if set_number < 1 or set_number > slot["planned_sets"]:
        return ("bad set number", 400)
    fact = _v1_current_facts(
        training_history(conn), expected_week
    ).get((lid, set_number))
    fields = _draft_set_fields(fact, slot, set_number)
    actual_added_weight = request.form.get(
        f"actual_added_weight_{lid}", request.form.get("actual_added_weight")
    )
    if (
        actual_added_weight is not None
        and (fact is None or set_number == slot["planned_sets"])
    ):
        try:
            fields["actual_added_weight"] = float(actual_added_weight)
        except (TypeError, ValueError):
            return ("bad actual added weight", 400)
        if (
            slot["load_model"] == "pure_bodyweight"
            and fields["actual_added_weight"] != 0
        ):
            return ("pure bodyweight added weight must be zero", 400)
    preview, preview_error = _candidate_preview(
        conn,
        expected_week=expected_week,
        slot_id=lid,
        set_number=set_number,
        actual_added_weight=fields["actual_added_weight"],
        reps=reps,
        warmup=fields["warmup"],
        drives_progression=fields["drives_progression"],
        e1rm_qualified=fields["e1rm_qualified"],
    )
    if preview_error is not None:
        return preview_error
    try:
        save_draft_set(
            conn,
            expected_week=expected_week,
            slot_id=lid,
            set_number=set_number,
            reps=reps,
            **fields,
        )
    except StaleTrainingWeekError:
        return ("stale week", 409)
    except TrainingInputError as error:
        return (str(error), 400)
    _, by_day = _v1_plan_by_day(conn)
    item = next(
        item for _day, items in by_day for item in items if item.id == lid
    )
    return render_template(
        "_plan_save_result.html",
        it=item,
        set_number=set_number,
        preview=preview,
    )


@bp.route("/log/preview", methods=["POST"])
def preview_log():
    """Preview one candidate driver without writing the source database."""
    conn = get_db()
    lid = request.args.get("lid", type=int)
    if lid is None:
        return ("bad slot", 400)
    try:
        expected_week = int(request.form["expected_week"])
    except (KeyError, TypeError, ValueError):
        return ("bad expected week", 400)
    plan = training_plan(conn)
    if plan["expected_week"] != expected_week:
        return ("stale week", 409)
    slot = next(
        (item for item in plan["slots"] if item["slot_id"] == lid), None
    )
    if slot is None:
        return ("unknown training slot", 400)
    if request.form.get("intent") == "skip":
        return render_template(
            "_focus_inspector.html",
            preview={
                "name": slot["name"],
                "mode": slot["mode"],
                "skipped": True,
                "comparison": None,
            },
        )
    set_number = slot["planned_sets"]
    reps_input = request.form.get(
        f"set_{lid}_{set_number}", request.form.get("reps")
    )
    weight_input = request.form.get(
        f"actual_added_weight_{lid}", request.form.get("actual_added_weight")
    )
    if request.form.get("intent") == "focus" and (
        reps_input is None or not reps_input.strip()
        or weight_input is None or not weight_input.strip()
    ):
        return render_template(
            "_focus_inspector.html",
            preview={
                "name": slot["name"],
                "mode": slot["mode"],
                "awaiting_input": True,
                "comparison": None,
            },
        )
    try:
        reps = int(reps_input)
        actual_added_weight = float(weight_input)
    except (TypeError, ValueError):
        return ("bad preview input", 400)
    if slot["load_model"] == "pure_bodyweight" and actual_added_weight != 0:
        return ("pure bodyweight added weight must be zero", 400)
    fact = _v1_current_facts(
        training_history(conn), expected_week
    ).get((lid, set_number))
    fields = _draft_set_fields(fact, slot, set_number)
    preview, preview_error = _candidate_preview(
        conn,
        expected_week=expected_week,
        slot_id=lid,
        set_number=set_number,
        actual_added_weight=actual_added_weight,
        reps=reps,
        warmup=fields["warmup"],
        drives_progression=fields["drives_progression"],
        e1rm_qualified=fields["e1rm_qualified"],
    )
    if preview_error is not None:
        return preview_error
    return render_template("_focus_inspector.html", preview=preview)


@bp.route("/log", methods=["POST"])
def submit():
    """Finalize the autosaved v1 sets and atomically advance the rendered week."""
    conn = get_db()
    try:
        expected_week = int(request.form["expected_week"])
    except (KeyError, TypeError, ValueError):
        return ("bad expected week", 400)
    try:
        skipped_ids = skipped_slot_ids()
    except TrainingInputError as error:
        return (str(error), 400)
    plan = training_plan(conn)
    if plan["expected_week"] != expected_week:
        return ("stale week", 409)
    try:
        review_week_settlement(
            conn,
            expected_week=expected_week,
            skipped_slot_ids=skipped_ids,
        )
    except StaleTrainingWeekError:
        return ("stale week", 409)
    except TrainingInputError as error:
        return (str(error), 400)
    from ..backup import snapshot
    from datetime import datetime, timezone
    def snapshot_before_advance():
        snapshot(
            current_app.config["DB_PATH"],
            dest_dir=current_app.config["BACKUP_DIR"],
            week=expected_week,
            ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),
        )

    try:
        new_week = finalize_week(
            conn,
            expected_week=expected_week,
            skipped_slot_ids=skipped_ids,
            before_advance=snapshot_before_advance,
        )
    except StaleTrainingWeekError:
        return ("stale week", 409)
    except TrainingInputError as error:
        return (str(error), 400)
    flash(f"已推进到 week {new_week}")
    return redirect(url_for("plan.view"))


@bp.route("/log/review", methods=["POST"])
def review_settlement():
    conn = get_db()
    try:
        expected_week = int(request.form["expected_week"])
    except (KeyError, TypeError, ValueError):
        return ("bad expected week", 400)
    try:
        skipped_ids = skipped_slot_ids()
        review = review_week_settlement(
            conn,
            expected_week=expected_week,
            skipped_slot_ids=skipped_ids,
        )
    except StaleTrainingWeekError:
        return ("stale week", 409)
    except TrainingInputError as error:
        return (str(error), 400)
    return render_template("settlement_review.html", review=review)


@bp.route("/export/week.html")
def export_week():
    """Render a self-contained offline plan with this week's saved progress."""
    from ..services.plan import day_states
    conn = get_db()
    week, by_day = _v1_plan_by_day(conn)
    days, first_open = day_states(by_day)
    html = render_template(
        "week_export.html", week=week, days=days, first_open=first_open
    )
    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'},
    )
