"""Per-tier progression rules. Pure functions; the spec source of truth."""
import math
from dataclasses import dataclass


def round_weight(w: float, quantum: float = 2.5) -> float:
    """Mirror Excel MROUND(w, quantum): round(w/quantum) half-away-from-zero, then * quantum."""
    n = math.floor((w / quantum) + 0.5)
    return round(n * quantum, 10)


# SBS delta by (actual - repout) difference
def _sbs_delta(diff: int) -> float:
    if diff <= -2: return -0.05
    if diff == -1: return -0.02
    if diff == 0:  return 0.0
    if diff == 1:  return 0.005
    if diff == 2:  return 0.01
    if diff == 3:  return 0.015
    if diff == 4:  return 0.02
    return 0.03   # beat by 5+


def sbs_next(tm: float, repout: int, actual) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged.

    TM is kept full-precision to match the SBS RTF xlsx (which rounds only the
    working weight, not the TM). Rounding the TM here stalls upward progression
    because sub-quantum weekly deltas are discarded before they accumulate.
    The working weight is rounded to the gym increment in week_plan / the webapp.

    The trailing ``round(..., 10)`` absorbs IEEE 754 drift (e.g. ``100*1.015``
    yields ``101.49999999999999`` raw) so the stored TM equals its mathematical
    value. It is NOT quantum rounding -- the TM is never snapped to 2.5 here.
    See ADR 0001.
    """
    if actual is None:
        return tm
    return round(tm * (1 + _sbs_delta(actual - repout)), 10)


def t3_next(weight: float, actual, target: int = 15, incr: float = 2.5) -> float:
    """T3 accessories: +incr when last set >= target, else repeat.

    Pure arithmetic — the hit add is NOT snapped. The incr IS the lift's
    effective step (per-lift ?? global, resolved by the caller), which is itself
    the loadable grid for that apparatus (see ADR 0003)."""
    if actual is None:
        return weight
    if actual >= target:
        return weight + incr
    return weight


# 自重 t2 目标次数区间（bodyweight_pct > 0 时启用）：镜像上次实做，夹在此区间。
BW_TARGET_MIN = 4
BW_TARGET_MAX = 10


def clamp_bodyweight_target(actual: int) -> int:
    """自重 t2 无重量可降、不 reset/级联；目标次数镜像上次实做，夹在 4~10。"""
    return max(BW_TARGET_MIN, min(BW_TARGET_MAX, actual))


@dataclass(frozen=True)
class T2State:
    target: int     # 8 / 6 / 4
    streak: int     # consecutive misses at current target
    weight: float


def t2_next(state: T2State, actual, est1rm: float, fail: int = 3,
            incr: float = 2.5, reset_pct: float = 0.75, quantum: float = 2.5) -> T2State:
    """T2 1-strike cascade: each miss drops one rep level (8 -> 6 -> 4); after `fail`
    consecutive misses, reset to target 8 at round(min(est1rm*reset_pct, weight-incr), quantum).
    A hit adds `incr` and stays at the current level (no climb-back).

    The reset is anchored below the failing weight: est1rm comes from the best of the
    WHOLE history (an old peak), so est1rm*reset_pct can stay at/above the weight that
    just failed `fail` times — resetting to it would loop forever. min() with
    (weight - incr) guarantees the reset is strictly lighter than what just failed."""
    if actual is None:
        return state
    if actual >= state.target:                                   # HIT — pure arithmetic (ADR 0003)
        return T2State(state.target, 0, state.weight + incr)
    new_streak = state.streak + 1                                # MISS
    if new_streak >= fail:                                       # Nth consecutive miss -> reset
        anchor = max(state.weight - incr, 0.0)                   # 防负 (ADR: B1 共识)
        return T2State(8, 0, round_weight(min(est1rm * reset_pct, anchor), quantum))
    ladder = [8, 6, 4]
    idx = ladder.index(state.target) if state.target in ladder else 0
    next_target = ladder[min(idx + 1, len(ladder) - 1)]          # drop one level, floor at 4
    return T2State(next_target, new_streak, state.weight)


def schedule_week(program_week: int) -> int:
    """Cyclic 1..21 schedule-row index for an absolute program week."""
    return ((program_week - 1) % 21) + 1


def cycle_number(program_week: int) -> int:
    """Which 21-week cycle a program week falls in (1-based)."""
    return ((program_week - 1) // 21) + 1


def lookup_schedule(schedule, kind: str, program_week: int):
    """Return the ScheduleRow for (kind, schedule_week(program_week)).

    Raises KeyError if that row is not present in `schedule`.
    """
    sw = schedule_week(program_week)
    for row in schedule:
        if row.kind == kind and row.week == sw:
            return row
    raise KeyError(f"no schedule row for kind={kind!r} week={sw}")
