"""Estimated 1RM = mean of Epley, Brzycki, Wathan (top-3 authoritative formulas).

Also hosts ``best_1rm`` and ``est1rm_from_history``: history -> best (weight,
reps) -> est1rm. These were ported verbatim from ``sbs_cli.program`` to break
the program<->modes circular import (ADR 0005): ``engine.modes`` imports them
from here without ever touching ``program``, so ``program`` is free to import
``engine.modes.get_mode`` in Task 3. The original copies in ``program`` are
retained for now; Task 3 migrates callers and removes them.
"""
import math
from statistics import mean
from typing import List, Optional, Tuple

from .load import working_weight


def epley(weight: float, reps: float) -> float:
    return weight * (1 + reps / 30)


def brzycki(weight: float, reps: float) -> float:
    return weight * 36 / (37 - reps)


def wathan(weight: float, reps: float) -> float:
    return weight * 100 / (48.8 + 53.8 * math.exp(-0.075 * reps))


def estimate_1rm(weight: float, reps: float) -> float:
    """Mean of the three formulas. Most accurate at reps <= 10."""
    return mean((epley(weight, reps), brzycki(weight, reps), wathan(weight, reps)))


# history is List[SetEntry] but importing schema from here would re-introduce a
# cycle (schema <- program <- engine); SetEntry is structural here.
def best_1rm(history: List, bodyweight: float = 0.0,
             bodyweight_pct: float = 0.0) -> Optional[Tuple[float, int]]:
    """Return (working_weight, reps) of the history entry with the highest
    estimate_1rm, or None. ``weight`` from each entry is treated as ADDED
    weight and converted to working weight via the seam (ADR 0004)."""
    best = None
    best_e = -1.0
    for h in history:
        w = working_weight(h.weight, bodyweight, bodyweight_pct)
        e = estimate_1rm(w, h.reps)
        if e > best_e:
            best_e, best = e, (w, h.reps)
    return best


def est1rm_from_history(history: List, bodyweight: float = 0.0,
                        bodyweight_pct: float = 0.0) -> Optional[float]:
    """Best-of-history est1rm, or None when history is empty."""
    b = best_1rm(history, bodyweight, bodyweight_pct)
    return estimate_1rm(b[0], b[1]) if b else None
