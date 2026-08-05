"""Commands and projections for the v1 per-set training facts."""

import math
import sqlite3

from sbs_cli.engine.modes import get_mode
from sbs_cli.engine.onerm import estimate_1rm
from sbs_cli.engine.progression import lookup_schedule

from .. import repo
from .rows import lift_from_row, profile_from_rows, state_from_rows
from .training_validation import (
    TrainingInputError,
    validate_draft_input,
    validate_slot,
)


class StaleTrainingWeekError(TrainingInputError):
    pass


UNCHANGED = object()


def actual_working_weight(*, load_model: str, actual_added_weight,
                          session_bodyweight, bodyweight_pct):
    """Project actual load using only the immutable training facts."""
    if actual_added_weight is None or not math.isfinite(actual_added_weight):
        return None
    if load_model == "barbell":
        return actual_added_weight
    if session_bodyweight is None or bodyweight_pct is None:
        return None
    if not math.isfinite(session_bodyweight) or not math.isfinite(bodyweight_pct):
        return None
    return actual_added_weight + session_bodyweight * bodyweight_pct


def _e1rm_values(weight, reps: int, canonical_eligible: bool):
    if weight is None or reps < 1 or reps > 20:
        return None, None
    display = weight if reps == 1 else estimate_1rm(weight, reps)
    canonical = display if canonical_eligible and reps <= 10 else None
    return canonical, display


def training_history(conn: sqlite3.Connection) -> list[dict]:
    """Return stable per-set projections and recorded work-set volume."""
    projected = []
    volumes = {}
    unavailable = set()
    for row in repo.list_training_facts(conn):
        weight = actual_working_weight(
            load_model=row["load_model"],
            actual_added_weight=row["actual_added_weight"],
            session_bodyweight=row["bodyweight_kg"],
            bodyweight_pct=row["bodyweight_pct"],
        )
        canonical, display = _e1rm_values(
            weight,
            row["reps"],
            bool(row["drives_progression"] and not row["warmup"]),
        )
        key = (row["session_id"], row["slot_id"])
        volumes.setdefault(key, 0.0)
        if not row["warmup"]:
            if weight is None:
                unavailable.add(key)
            else:
                volumes[key] += weight * row["reps"]
        item = dict(row)
        item.update(
            actual_working_weight=weight,
            canonical_e1rm=canonical,
            display_e1rm=display,
        )
        projected.append((key, item))
    return [
        {**item, "recorded_volume": None if key in unavailable else volumes[key]}
        for key, item in projected
    ]


def _prescription_snapshot(conn, slot, state, settings, expected_week):
    schedule = repo.load_schedule(conn)
    lift = lift_from_row(slot)
    profile = profile_from_rows(settings, [], schedule)
    state_model = state_from_rows(state, [])
    planned = get_mode(slot["mode"]).plan_fields(
        profile, lift, state_model, expected_week
    )
    mode = slot["mode"]
    intensity = (
        lookup_schedule(schedule, slot["lift_kind"], expected_week).intensity
        if mode == "sbs"
        else None
    )
    snapshot = {
        "mode": slot["mode"],
        "planned_sets": slot["sets"],
        "planned_reps": planned["reps"],
        "planned_repout": planned["repout"],
        "planned_target": planned["target"],
        "planned_intensity": intensity,
        "planned_added_weight": planned["added"],
        "planned_working_weight": planned["weight"],
        "bodyweight_pct": slot["bodyweight_pct"],
        "state_tm": None,
        "state_weight": None,
        "state_target": None,
        "state_streak": None,
        "state_est1rm": None,
        "rounding": None,
        "increment": None,
        "t2_reset_pct": None,
        "t2_fail": None,
        "t3_target": None,
    }
    if mode == "sbs":
        snapshot.update(state_tm=state["tm"], rounding=settings["rounding"])
    elif mode == "linear_t2":
        snapshot.update(
            state_weight=state["weight"],
            state_target=state["target"],
            state_streak=state["streak"],
            state_est1rm=state["est1rm"],
            increment=slot["incr"] if slot["incr"] is not None else settings["incr"],
            t2_reset_pct=settings["t2_reset_pct"],
            t2_fail=settings["t2_fail"],
        )
    elif mode == "linear_t3":
        snapshot.update(
            state_weight=state["weight"],
            increment=slot["incr"] if slot["incr"] is not None else settings["incr"],
            t3_target=settings["t3_target"],
        )
    else:
        snapshot["state_weight"] = state["weight"]
    return snapshot


def training_plan(conn: sqlite3.Connection) -> dict:
    """Render the current v1 prescription without creating training facts."""
    settings = repo.get_settings(conn)
    expected_week = settings["week"]
    slots = []
    for slot in repo.list_training_slots(conn):
        state = repo.get_training_state(conn, slot["id"])
        if state is None:
            continue
        planned = _prescription_snapshot(
            conn, slot, state, settings, expected_week
        )
        slots.append(
            {
                "slot_id": slot["id"],
                "name": slot["name"],
                "load_model": slot["load_model"],
                "day": slot["day"],
                "planned_sets": planned["planned_sets"],
                "planned_reps": planned["planned_reps"],
                "planned_added_weight": planned["planned_added_weight"],
                "planned_working_weight": planned["planned_working_weight"],
            }
        )
    return {"expected_week": expected_week, "slots": slots}


def save_draft_set(conn: sqlite3.Connection, *, expected_week: int, slot_id: int,
                   set_number: int, actual_added_weight: float, reps: int,
                   warmup: bool = False, drives_progression: bool = False,
                   training_date=UNCHANGED, bodyweight_kg=UNCHANGED) -> None:
    """Save one stable draft set; this command owns the transaction."""
    validate_draft_input(
        expected_week=expected_week,
        slot_id=slot_id,
        set_number=set_number,
        actual_added_weight=actual_added_weight,
        reps=reps,
        bodyweight_kg=None if bodyweight_kg is UNCHANGED else bodyweight_kg,
        warmup=warmup,
        drives_progression=drives_progression,
    )

    try:
        with conn:
            if not repo.lock_week_if_current(conn, expected_week):
                raise StaleTrainingWeekError("stale week")
            slot = repo.get_training_slot(conn, slot_id)
            state = repo.get_training_state(conn, slot_id)
            if slot is None or state is None:
                raise TrainingInputError("unknown training slot")
            settings = repo.get_settings(conn)
            validate_slot(slot, days_per_week=settings["days_per_week"])
            session = repo.get_training_session(
                conn, program_week=expected_week, day=slot["day"]
            )
            if session is not None and session["finalized_at"] is not None:
                raise TrainingInputError("session is finalized")
            if session is None:
                session_id = repo.create_training_session(
                    conn,
                    program_week=expected_week,
                    day=slot["day"],
                    training_date=None if training_date is UNCHANGED else training_date,
                    bodyweight_kg=None if bodyweight_kg is UNCHANGED else bodyweight_kg,
                )
            else:
                session_id = session["id"]
                changes = {}
                if training_date is not UNCHANGED:
                    changes["training_date"] = training_date
                if bodyweight_kg is not UNCHANGED:
                    changes["bodyweight_kg"] = bodyweight_kg
                repo.update_training_session(conn, session_id, **changes)
            snapshot = _prescription_snapshot(
                conn, slot, state, settings, expected_week
            )
            repo.create_prescription_snapshot(
                conn,
                {"session_id": session_id, "slot_id": slot_id, **snapshot},
            )
            if drives_progression:
                repo.clear_progression_driver(
                    conn, session_id=session_id, slot_id=slot_id
                )
            repo.upsert_training_set(
                conn,
                session_id=session_id,
                slot_id=slot_id,
                set_number=set_number,
                actual_added_weight=actual_added_weight,
                reps=reps,
                warmup=warmup,
                drives_progression=drives_progression,
            )
    except Exception:
        conn.rollback()
        raise
