"""Commands and projections for the v1 per-set training facts."""

import math
import sqlite3
from datetime import datetime, timezone

from sbs_cli.data.schema import Lift, LiftState, Profile, ScheduleRow, SetEntry
from sbs_cli.engine.modes import get_mode
from sbs_cli.engine.onerm import estimate_1rm
from sbs_cli.engine.progression import (
    T2State,
    lookup_schedule,
    schedule_week,
    t2_next,
)

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


def _project_training_fact(row, *, canonical_eligible: bool) -> dict:
    weight = actual_working_weight(
        load_model=row["load_model"],
        actual_added_weight=row["actual_added_weight"],
        session_bodyweight=row["bodyweight_kg"],
        bodyweight_pct=row["bodyweight_pct"],
    )
    canonical, display = _e1rm_values(
        weight, row["reps"], canonical_eligible
    )
    item = dict(row)
    item.update(
        actual_working_weight=weight,
        canonical_e1rm=canonical,
        display_e1rm=display,
    )
    return item


def training_history(conn: sqlite3.Connection) -> list[dict]:
    """Return stable per-set projections and recorded work-set volume."""
    projected = []
    volumes = {}
    unavailable = set()
    for row in repo.list_training_facts(conn):
        item = _project_training_fact(
            row, canonical_eligible=bool(row["e1rm_qualified"])
        )
        key = (row["session_id"], row["slot_id"])
        volumes.setdefault(key, 0.0)
        if not row["warmup"]:
            if item["actual_working_weight"] is None:
                unavailable.add(key)
            else:
                volumes[key] += item["actual_working_weight"] * row["reps"]
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
        item = {
            "slot_id": slot["id"],
            "name": slot["name"],
            "load_model": slot["load_model"],
            "mode": slot["mode"],
            "day": slot["day"],
            "planned_sets": planned["planned_sets"],
            "planned_reps": planned["planned_reps"],
            "planned_repout": planned["planned_repout"],
            "planned_target": planned["planned_target"],
            "planned_added_weight": planned["planned_added_weight"],
            "planned_working_weight": planned["planned_working_weight"],
            "state_streak": planned["state_streak"],
            "state_est1rm": planned["state_est1rm"],
        }
        if slot["mode"] == "sbs":
            item["historical_peak_e1rm"] = state["est1rm"]
        slots.append(item)
    return {"expected_week": expected_week, "slots": slots}


def save_draft_set(conn: sqlite3.Connection, *, expected_week: int, slot_id: int,
                   set_number: int, actual_added_weight: float, reps: int,
                   warmup: bool = False, drives_progression: bool = False,
                   e1rm_qualified: bool = False,
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
                e1rm_qualified=e1rm_qualified,
            )
    except Exception:
        conn.rollback()
        raise


class _DriverHistory(list):
    """Present the projected driver load to unchanged Mode handlers."""

    def __init__(self, entries, actual_added_weight):
        super().__init__(entries)
        self._actual_added_weight = actual_added_weight

    def append(self, entry):
        if self._actual_added_weight is not None:
            super().append(
                SetEntry(
                    week=entry.week,
                    weight=self._actual_added_weight,
                    reps=entry.reps,
                )
            )


def _progression_models(row, expected_week: int, canonical_e1rm,
                        projection_available: bool):
    mode = row["mode"]
    if mode is None:
        raise TrainingInputError("progression driver snapshot is unconfirmed")
    if row["current_slot_mode"] != mode or row["current_state_mode"] != mode:
        raise TrainingInputError("training mode changed after draft save")
    required = {
        "sbs": ("state_tm", "rounding", "planned_intensity", "planned_reps",
                "planned_repout"),
        "linear_t2": ("state_weight", "state_target", "state_streak", "increment",
                      "t2_reset_pct", "t2_fail"),
        "linear_t3": ("state_weight", "increment", "t3_target"),
        "none": ("state_weight",),
    }
    if mode not in required or any(row[name] is None for name in required[mode]):
        raise TrainingInputError("progression driver snapshot is incomplete")

    bodyweight_pct = row["bodyweight_pct"]
    if bodyweight_pct is None:
        bodyweight_pct = 0.0 if row["load_model"] == "barbell" else 1.0
    session_bodyweight = row["bodyweight_kg"] or 0.0
    prior_e1rm = row["state_est1rm"]
    history = []
    if prior_e1rm is not None and (
        canonical_e1rm is None or prior_e1rm > canonical_e1rm
    ):
        history.append(
            SetEntry(
                week=max(expected_week - 1, 1),
                weight=prior_e1rm - session_bodyweight * bodyweight_pct,
                reps=1,
            )
        )

    schedule = []
    if mode == "sbs":
        schedule = [
            ScheduleRow(
                kind=row["lift_kind"],
                week=schedule_week(expected_week),
                intensity=row["planned_intensity"],
                reps=row["planned_reps"],
                repout=row["planned_repout"],
            )
        ]
    profile = Profile(
        rounding=row["rounding"] or 2.5,
        incr=row["increment"] or 2.5,
        t2_reset_pct=row["t2_reset_pct"] or 0.75,
        t2_fail=row["t2_fail"] or 3,
        t3_target=row["t3_target"] or 15,
        bodyweight=session_bodyweight,
        schedule=schedule,
    )
    lift = Lift(
        name=row["name"],
        day=row["day"],
        load_model=row["load_model"],
        mode=mode,
        sets=row["planned_sets"] or 1,
        reps=row["planned_reps"] or 0,
        repout=row["planned_repout"] or 0,
        start=row["actual_added_weight"],
        lift_kind=row["lift_kind"],
        incr=row["increment"],
        bodyweight_pct=bodyweight_pct,
    )
    state = LiftState(
        name=row["name"],
        mode=mode,
        tm=row["state_tm"],
        weight=row["state_weight"],
        target=row["state_target"],
        streak=row["state_streak"] or 0,
        est1rm=prior_e1rm,
        history=_DriverHistory(
            history,
            row["actual_added_weight"] if projection_available else None,
        ),
    )
    return profile, lift, state, prior_e1rm


def _observation_peaks(conn: sqlite3.Connection, expected_week: int):
    sbs_peaks = {}
    t2_peaks = {}
    for row in repo.list_training_facts(conn):
        if (
            row["program_week"] != expected_week
            or row["finalized_at"] is not None
            or not row["e1rm_qualified"]
        ):
            continue
        if row["mode"] == "sbs":
            peaks = sbs_peaks
        elif row["mode"] == "linear_t2" and row["load_model"] == "barbell":
            peaks = t2_peaks
        else:
            continue
        projected = _project_training_fact(
            row, canonical_eligible=True
        )
        canonical_e1rm = projected["canonical_e1rm"]
        if canonical_e1rm is not None:
            peaks[row["slot_id"]] = max(
                peaks.get(row["slot_id"], canonical_e1rm), canonical_e1rm
            )
    return sbs_peaks, t2_peaks


def finalize_week(conn: sqlite3.Connection, *, expected_week: int) -> int:
    """Atomically progress explicit drivers, finalize sessions, and advance week."""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            if not repo.lock_week_if_current(conn, expected_week):
                raise StaleTrainingWeekError("stale week")
            sbs_observation_peaks, t2_observation_peaks = _observation_peaks(
                conn, expected_week
            )
            for row in repo.list_progression_drivers(
                conn, program_week=expected_week
            ):
                if row["actual_added_weight"] is None or not math.isfinite(
                    row["actual_added_weight"]
                ):
                    raise TrainingInputError(
                        "progression driver actual weight is unconfirmed"
                    )
                is_sbs = row["mode"] == "sbs"
                is_loadable_t2 = (
                    row["mode"] == "linear_t2"
                    and row["load_model"] == "barbell"
                )
                projected_driver = _project_training_fact(
                    row,
                    canonical_eligible=(
                        bool(row["e1rm_qualified"])
                        if is_sbs or is_loadable_t2 else True
                    ),
                )
                working_weight = projected_driver["actual_working_weight"]
                canonical_e1rm = projected_driver["canonical_e1rm"]
                models = _progression_models(
                    row,
                    expected_week,
                    None if is_sbs else canonical_e1rm,
                    projection_available=(
                        working_weight is not None
                        and not is_sbs
                        and not is_loadable_t2
                    ),
                )
                profile, lift, state, prior_e1rm = models
                if is_loadable_t2:
                    current_peak_e1rm = t2_observation_peaks.get(row["slot_id"])
                    peak_values = tuple(
                        value for value in (prior_e1rm, current_peak_e1rm)
                        if value is not None
                    )
                    cycle_peak_e1rm = max(peak_values) if peak_values else None
                    effective_step = (
                        lift.incr if lift.incr is not None else profile.incr
                    )
                    next_state = t2_next(
                        T2State(
                            state.target,
                            {8: 0, 6: 1, 4: 2}[state.target],
                            state.weight,
                        ),
                        row["reps"],
                        cycle_peak_e1rm,
                        fail=3,
                        incr=effective_step,
                        reset_pct=profile.t2_reset_pct,
                        quantum=effective_step,
                    )
                    state.target = next_state.target
                    state.streak = next_state.streak
                    state.weight = next_state.weight
                    state.est1rm = cycle_peak_e1rm
                    if row["state_target"] == 4 and row["reps"] < 4:
                        state.est1rm = None
                else:
                    get_mode(state.mode).advance(
                        profile, lift, state, row["reps"], expected_week
                    )
                    aggregate_e1rm = None if is_sbs else canonical_e1rm
                    state.est1rm = prior_e1rm
                    if aggregate_e1rm is not None:
                        state.est1rm = max(
                            value for value in (prior_e1rm, aggregate_e1rm)
                            if value is not None
                        )
                repo.save_training_state(
                    conn,
                    row["slot_id"],
                    mode=state.mode,
                    tm=state.tm,
                    weight=state.weight,
                    target=state.target,
                    streak=state.streak,
                    est1rm=state.est1rm,
                )
            for slot_id, peak_e1rm in sbs_observation_peaks.items():
                repo.save_sbs_historical_peak(conn, slot_id, peak_e1rm)
            repo.finalize_training_sessions(
                conn, program_week=expected_week, finalized_at=timestamp
            )
            if not repo.increment_week_if_current(conn, expected_week):
                raise StaleTrainingWeekError("stale week")
    except Exception:
        conn.rollback()
        raise
    return expected_week + 1
