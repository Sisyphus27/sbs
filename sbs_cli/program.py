"""Tie engine rules to lift state; manage history + est1rm + week plan."""
from typing import Optional, List
from .data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from .engine.onerm import estimate_1rm
from .engine.load import working_weight
from .engine.progression import sbs_next, t3_next, t2_next, T2State, round_weight, lookup_schedule


def best_1rm(history: List[SetEntry], bodyweight: float = 0.0,
             bodyweight_pct: float = 0.0):
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


def _est1rm_from_history(history: List[SetEntry], bodyweight: float = 0.0,
                         bodyweight_pct: float = 0.0) -> Optional[float]:
    b = best_1rm(history, bodyweight, bodyweight_pct)
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
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history,
                                            profile.bodyweight, lift.bodyweight_pct)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, sc.repout, actual_reps)
    elif lift.progression == "none":
        pass   # pure bodyweight: record only, no auto weight progression (ADR 0004)
    else:
        # effective step: per-lift incr ?? global incr (ADR 0003). It is both the hit-add Δ
        # and the snap grid for this lift's T2 reset. sbs ignores incr entirely.
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        if lift.tier == "t3":
            state.weight = t3_next(state.weight, actual_reps,
                                   target=profile.t3_target, incr=eff_incr)
        elif lift.tier == "t2":
            est = state.est1rm if state.est1rm is not None else 0.0
            ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
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
            sc = lookup_schedule(profile.schedule, l.lift_kind, state.week)
            w = round_weight((ls.tm or 0) * sc.intensity, profile.rounding)
            out.append(PlanItem(l.name, "sbs", w, sc.reps, l.sets, sc.repout, None, 0, ls.est1rm))
        elif l.tier == "t2":
            w = working_weight(ls.weight or 0.0, profile.bodyweight, l.bodyweight_pct)
            out.append(PlanItem(l.name, "t2", w, ls.target, l.sets, None, ls.target, ls.streak, ls.est1rm))
        elif l.tier == "t3":
            w = working_weight(ls.weight or 0.0, profile.bodyweight, l.bodyweight_pct)
            out.append(PlanItem(l.name, "t3", w, profile.t3_target, l.sets, None, profile.t3_target, 0, ls.est1rm))
    return out


def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``
    over ``history``. History rows are immutable facts; only their reps drive the
    replay. ``est1rm`` is computed from working weight (added + bodyweight * pct,
    per ADR 0004). Not applicable to sbs (sbs has no start-based progression)."""
    bw, pct = profile.bodyweight, lift.bodyweight_pct
    est = _est1rm_from_history(history, bw, pct)
    # effective step: per-lift incr ?? global incr (ADR 0003).
    eff_incr = lift.incr if lift.incr is not None else profile.incr
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target, incr=eff_incr)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1], bw, pct) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")


def recompute_sbs_tm(lift: Lift, history: List[SetEntry], schedule) -> float:
    """Replay an sbs lift's TM from ``lift.max`` over its history (raw, no rounding),
    using each week's SCHEDULED repout as the rep-out target. ``schedule`` is the list
    of ScheduleRow passed from the caller (webapp loads it from sbs_schedule).
    History rows are immutable facts; only their reps + the scheduled repout drive the
    replay. See ADR 0001 (TM raw) and the schedule spec (Q6: current-schedule replay)."""
    tm = lift.max
    for h in sorted(history, key=lambda x: x.week):
        sc = lookup_schedule(schedule, lift.lift_kind, h.week)
        tm = sbs_next(tm, sc.repout, h.reps)
    return tm
