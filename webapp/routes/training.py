"""Thin Web adapters for saving and viewing v1 training facts."""

from datetime import date

from flask import Blueprint, jsonify, request

from ..db import get_db
from ..services.training import (
    StaleTrainingWeekError,
    TrainingInputError,
    UNCHANGED,
    save_draft_set,
    training_history,
    training_plan,
)


bp = Blueprint("training", __name__, url_prefix="/training")


def _integer(name):
    try:
        return int(request.form[name])
    except (KeyError, TypeError, ValueError) as error:
        raise TrainingInputError(f"bad {name}") from error


def _number(name):
    try:
        return float(request.form[name])
    except (KeyError, TypeError, ValueError) as error:
        raise TrainingInputError(f"bad {name}") from error


def _boolean(name):
    value = _integer(name)
    if value not in (0, 1):
        raise TrainingInputError(f"bad {name}")
    return bool(value)


def _optional_number(name):
    if name not in request.form:
        return UNCHANGED
    raw = request.form[name].strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as error:
        raise TrainingInputError(f"bad {name}") from error


def _optional_date(name):
    if name not in request.form:
        return UNCHANGED
    raw = request.form[name].strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as error:
        raise TrainingInputError(f"bad {name}") from error


def _save(*, warmup: bool, drives_progression: bool):
    try:
        save_draft_set(
            get_db(),
            expected_week=_integer("expected_week"),
            slot_id=_integer("slot_id"),
            set_number=_integer("set_number"),
            actual_added_weight=_number("actual_added_weight"),
            reps=_integer("reps"),
            warmup=warmup,
            drives_progression=drives_progression,
            training_date=_optional_date("training_date"),
            bodyweight_kg=_optional_number("bodyweight_kg"),
        )
    except StaleTrainingWeekError:
        return ("stale week", 409)
    except TrainingInputError as error:
        return (str(error), 400)
    return ("", 200)


@bp.post("/sets/quick")
def save_quick_set():
    return _save(warmup=False, drives_progression=True)


@bp.post("/sets/full")
def save_full_set():
    try:
        warmup = _boolean("warmup")
        drives_progression = _boolean("drives_progression")
    except TrainingInputError as error:
        return (str(error), 400)
    return _save(warmup=warmup, drives_progression=drives_progression)


@bp.get("/history")
def history():
    return jsonify(training_history(get_db()))


@bp.get("/plan")
def plan():
    return jsonify(training_plan(get_db()))
