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


def sbs_next(tm: float, repout: int, actual, quantum: float = 2.5) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged."""
    if actual is None:
        return tm
    return round_weight(tm * (1 + _sbs_delta(actual - repout)), quantum)


def t3_next(weight: float, actual, target: int = 15, incr: float = 2.5,
            quantum: float = 2.5) -> float:
    """T3 accessories: +incr when last set >= target, else repeat."""
    if actual is None:
        return weight
    if actual >= target:
        return round_weight(weight + incr, quantum)
    return weight


@dataclass(frozen=True)
class T2State:
    target: int     # 10 / 8 / 6
    streak: int     # consecutive misses at current target
    weight: float


def t2_next(state: T2State, actual, est1rm: float, fail: int = 3,
            incr: float = 2.5, reset_pct: float = 0.70, quantum: float = 2.5) -> T2State:
    """GZCLP T2 back: 10->8->6 tier cascade; full reset = reset_pct * est1rm, back to 10."""
    if actual is None:
        return state
    if actual >= state.target:                                   # hit
        return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
    if state.streak + 1 >= fail:                                 # Nth consecutive miss -> tier change
        if state.target == 10:
            return T2State(8, 0, state.weight)
        if state.target == 8:
            return T2State(6, 0, state.weight)
        return T2State(10, 0, round_weight(est1rm * reset_pct, quantum))   # reset at 6
    return T2State(state.target, state.streak + 1, state.weight) # miss, under threshold
