"""Small pure validation seam for v1 draft training commands."""

import math

from sbs_cli.data.schema import is_legal_combo


class TrainingInputError(ValueError):
    pass


def validate_draft_input(*, expected_week: int, slot_id: int, set_number: int,
                         actual_added_weight: float, reps: int,
                         bodyweight_kg, warmup: bool,
                         drives_progression: bool) -> None:
    if expected_week < 1 or slot_id < 1 or set_number < 1 or reps < 1:
        raise TrainingInputError("week, slot, set number, and reps must be positive")
    if not math.isfinite(actual_added_weight) or actual_added_weight < 0:
        raise TrainingInputError("actual added weight must be nonnegative and finite")
    if bodyweight_kg is not None:
        if not math.isfinite(bodyweight_kg) or bodyweight_kg <= 0:
            raise TrainingInputError("session bodyweight must be positive and finite")
    if warmup and drives_progression:
        raise TrainingInputError("a warmup set cannot drive progression")


def validate_slot(slot, *, days_per_week: int) -> None:
    load_model = slot["load_model"]
    mode = slot["mode"]
    bodyweight_pct = slot["bodyweight_pct"]
    if not is_legal_combo(load_model, mode):
        raise TrainingInputError("illegal load model and mode combination")
    if slot["day"] < 1 or slot["day"] > days_per_week:
        raise TrainingInputError("slot day is outside the displayed program")
    if not math.isfinite(bodyweight_pct):
        raise TrainingInputError("bodyweight percentage must be finite")
    if load_model == "barbell" and bodyweight_pct != 0:
        raise TrainingInputError("barbell slots require zero bodyweight percentage")
    if load_model != "barbell" and bodyweight_pct <= 0:
        raise TrainingInputError("bodyweight slots require a positive percentage")
