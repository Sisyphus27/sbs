"""Shared form-parsing helpers for the route layer.

Two repeated shapes lived across the route files: cast-or-reject numeric fields
(``try/int(raw)/except ValueError -> flash`` ×5) and the lift create/edit field
schema (two hand-synced column->cast tables). Single-source them here.
"""
from flask import request


def present_fields(casts):
    """Walk a {col: cast} table over the submitted form; return (fields, bad_col).

    Only non-empty submitted fields are included (empty string = not provided,
    so a partial edit leaves other columns alone). On the first cast failure
    returns (None, col) so the caller can flash which field was bad."""
    fields = {}
    for col, cast in casts.items():
        if col not in request.form:
            continue
        raw = request.form[col]
        if raw.strip() == "":
            continue
        try:
            fields[col] = cast(raw)
        except (ValueError, TypeError):
            return None, col
    return fields, None


# --- Lift create/edit field schema (ADR 0005) ---
# Single source: new() and edit() previously each maintained a copy and both
# had to grow bodyweight_pct / incr / lift_kind in lockstep. load_model is
# create-only (immutable per ADR 0005); incr is handled separately because
# sbs/none force it to NULL rather than parsing the form value.
LIFT_FIELD_CASTS = {
    "name": str, "mode": str, "day": int, "sets": int,
    "max": float, "intensity": float, "reps": int, "repout": int,
    "start": float, "lift_kind": str, "bodyweight_pct": float,
}
