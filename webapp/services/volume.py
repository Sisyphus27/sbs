"""Per-lift actual tonnage (training volume) for a given program week.

Reads the same DB the plan view reads; computes weight x total reps where
every set but the last is taken at its planned rep count and the last set
uses the logged reps (the 末组 entry). Read-only; writes nothing.
See docs/superpowers/specs/2026-07-15-per-lift-volume-comparison-design.md
"""


def _actual_tonnage(weight: float, sets: int, planned_reps: int, last_set_reps: int) -> float:
    """weight x total reps: (sets-1) sets at planned_reps + last set at last_set_reps."""
    sets = sets or 3
    return weight * ((sets - 1) * planned_reps + last_set_reps)
