"""Tie engine rules to lift state; manage history + est1rm + week plan.

ADR 0005 (mode unification): per-mode behaviour lives in ``engine.modes``;
this module's ``advance_lift`` / ``week_plan`` / ``initial_state`` /
``recompute_state`` are now thin dispatchers over ``get_mode(lift.mode)``.
The original ``best_1rm`` / ``_est1rm_from_history`` bodies were ported to
``engine.onerm`` (to break the program<->modes cycle) and are re-exported
here so webapp services importing ``sbs_cli.program._est1rm_from_history``
keep working until Task 5 migrates them.
"""
from typing import Optional, List
from .data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from .engine.onerm import (best_1rm,
                           est1rm_from_history as _est1rm_from_history)
from .engine.modes import get_mode
from .engine.progression import (sbs_next, t3_next, t2_next, T2State,
                                 lookup_schedule)

# Re-export so webapp services / tests importing ``sbs_cli.program.best_1rm``
# keep working without depending on ``engine.onerm`` directly.
__all__ = ["best_1rm"]


def initial_state(profile: Profile) -> ProgramState:
    lifts = {}
    for l in profile.lifts:
        lifts[l.name] = get_mode(l.mode).initial_state(l, None)
    return ProgramState(week=1, lifts=lifts)


def advance_lift(profile: Profile, lift: Lift, state: LiftState, actual_reps, week: int) -> None:
    """Apply this week's logged last-set reps; mutate state in place.

    All per-mode logic (working weight, history/est1rm record, progression)
    lives in the registered Mode handler (ADR 0005); this fn is dispatch-only.
    """
    get_mode(lift.mode).advance(profile, lift, state, actual_reps, week)


class PlanItem:
    __slots__ = ("name", "mode", "weight", "reps", "sets", "repout", "target", "streak", "est1rm")

    def __init__(self, name, mode, weight, reps, sets, repout, target, streak, est1rm):
        self.name, self.mode, self.weight, self.reps, self.sets = name, mode, weight, reps, sets
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
        f = get_mode(l.mode).plan_fields(profile, l, ls, state.week)
        out.append(PlanItem(l.name, l.mode, f["weight"], f["reps"], l.sets,
                            f["repout"], f["target"], f["streak"], ls.est1rm))
    return out


def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a linear_t2/linear_t3 lift's state by replaying progression
    from ``lift.start`` over ``history``. History rows are immutable facts;
    only their reps drive the replay. ``est1rm`` is computed from working
    weight (added + bodyweight * pct, per ADR 0004). Not applicable to sbs
    (sbs has no start-based progression)."""
    bw, pct = profile.bodyweight, lift.bodyweight_pct
    est = _est1rm_from_history(history, bw, pct)
    # effective step: per-lift incr ?? global incr (ADR 0003).
    eff_incr = lift.incr if lift.incr is not None else profile.incr
    if lift.mode == "linear_t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target, incr=eff_incr)
        return LiftState(name=lift.name, mode="linear_t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.mode == "linear_t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1], bw, pct) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, mode="linear_t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to mode {lift.mode!r}")


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
