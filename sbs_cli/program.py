"""Tie engine rules to lift state; manage history + est1rm + week plan."""
from typing import Optional, List
from .data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from .engine.onerm import estimate_1rm
from .engine.progression import sbs_next, t3_next, t2_next, T2State, round_weight


def best_1rm(history: List[SetEntry]):
    """Return (weight, reps) of the history entry with the highest estimate_1rm, or None."""
    best = None
    best_e = -1.0
    for h in history:
        e = estimate_1rm(h.weight, h.reps)
        if e > best_e:
            best_e, best = e, (h.weight, h.reps)
    return best


def _est1rm_from_history(history: List[SetEntry]) -> Optional[float]:
    b = best_1rm(history)
    return estimate_1rm(b[0], b[1]) if b else None


def initial_state(profile: Profile) -> ProgramState:
    lifts = {}
    for l in profile.lifts:
        if l.tier == "sbs":
            lifts[l.name] = LiftState(name=l.name, tier="sbs", tm=l.max)
        elif l.tier == "t2":
            lifts[l.name] = LiftState(name=l.name, tier="t2", weight=l.start, target=8, streak=0)
        elif l.tier == "t3":
            lifts[l.name] = LiftState(name=l.name, tier="t3", weight=l.start)
    return ProgramState(week=1, lifts=lifts)


def advance_lift(profile: Profile, lift: Lift, state: LiftState, actual_reps, week: int) -> None:
    """Apply this week's logged last-set reps; mutate state in place. All knobs from profile."""
    # working weight this week (before progression)
    if lift.tier == "sbs":
        w = round_weight((state.tm or 0) * lift.intensity, profile.rounding)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, lift.repout, actual_reps)
    elif lift.tier == "t3":
        state.weight = t3_next(state.weight, actual_reps,
                               target=profile.t3_target, incr=profile.incr, quantum=profile.rounding)
    elif lift.tier == "t2":
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                     fail=profile.t2_fail, incr=profile.incr,
                     reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight


class PlanItem:
    __slots__ = ("name", "tier", "weight", "reps", "sets", "repout", "target", "streak", "est1rm")

    def __init__(self, name, tier, weight, reps, sets, repout, target, streak, est1rm):
        self.name, self.tier, self.weight, self.reps, self.sets = name, tier, weight, reps, sets
        self.repout, self.target, self.streak, self.est1rm = repout, target, streak, est1rm


def week_plan(profile: Profile, state: ProgramState, day: Optional[int] = None) -> List[PlanItem]:
    """Build the display plan for a given day (or all lifts if day=None)."""
    out = []
    for l in profile.lifts:
        if day is not None and l.day != day:
            continue
        ls = state.lifts.get(l.name)
        if ls is None:
            continue
        if l.tier == "sbs":
            w = round_weight((ls.tm or 0) * l.intensity, profile.rounding)
            out.append(PlanItem(l.name, "sbs", w, l.reps, l.sets, l.repout, None, 0, ls.est1rm))
        elif l.tier == "t2":
            out.append(PlanItem(l.name, "t2", ls.weight, ls.target, l.sets, None, ls.target, ls.streak, ls.est1rm))
        elif l.tier == "t3":
            out.append(PlanItem(l.name, "t3", ls.weight, profile.t3_target, l.sets, None, profile.t3_target, 0, ls.est1rm))
    return out


def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``
    over ``history``. History rows are immutable facts; only their reps drive the
    replay. ``est1rm`` is computed from the real history weights (unchanged by the
    new start). Not applicable to sbs (sbs has no start-based progression)."""
    est = _est1rm_from_history(history)
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target,
                             incr=profile.incr, quantum=profile.rounding)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1]) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=profile.incr,
                         reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")
