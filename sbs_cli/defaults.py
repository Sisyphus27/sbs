"""Single source for reset-to-default settings + the standard SBS RTF 21-week ladders.

Ladders extracted from the `Setup` sheet of `SBS RTF filled GZCLP.xlsx`. Weeks 7/14/21
are deload weeks. Each tuple is (week, intensity, reps, repout).
"""
from .data.schema import ScheduleRow

# Excluded: rounding, incr (weight settings).
DEFAULT_SETTINGS = {
    "days_per_week": 4,
    "t2_reset_pct": 0.75,
    "t2_fail": 3,
    "t3_target": 15,
}
RESETTABLE_FIELDS = ("days_per_week", "t2_reset_pct", "t2_fail", "t3_target")

MAIN_LADDER = [
    (1, 0.70, 5, 10), (2, 0.75, 4, 8), (3, 0.80, 3, 6), (4, 0.725, 5, 9), (5, 0.775, 4, 7),
    (6, 0.825, 3, 5), (7, 0.60, 7, 14), (8, 0.75, 4, 8), (9, 0.80, 3, 6), (10, 0.85, 2, 4),
    (11, 0.775, 4, 7), (12, 0.825, 3, 5), (13, 0.875, 2, 3), (14, 0.60, 7, 14),
    (15, 0.80, 3, 6), (16, 0.85, 2, 4), (17, 0.90, 1, 2), (18, 0.85, 2, 4),
    (19, 0.90, 1, 2), (20, 0.95, 1, 1), (21, 0.60, 7, 14),
]

AUX_LADDER = [
    (1, 0.60, 7, 14), (2, 0.65, 6, 12), (3, 0.70, 5, 10), (4, 0.625, 7, 13),
    (5, 0.675, 6, 11), (6, 0.725, 5, 9), (7, 0.50, 8, 18), (8, 0.65, 6, 12),
    (9, 0.70, 5, 10), (10, 0.75, 4, 8), (11, 0.675, 6, 11), (12, 0.725, 5, 9),
    (13, 0.775, 4, 7), (14, 0.50, 8, 18), (15, 0.70, 5, 10), (16, 0.75, 4, 8),
    (17, 0.80, 3, 6), (18, 0.75, 4, 8), (19, 0.80, 3, 6), (20, 0.85, 2, 4),
    (21, 0.50, 8, 18),
]


def _rows(kind, ladder):
    return [ScheduleRow(kind=kind, week=w, intensity=i, reps=r, repout=ro)
            for (w, i, r, ro) in ladder]


DEFAULT_SCHEDULE = _rows("main", MAIN_LADDER) + _rows("aux", AUX_LADDER)
