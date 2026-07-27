"""Progression-mode registry: single dispatch point for per-mode behaviour.

Each mode implements four operations: initial_state / advance / plan_fields /
derive_on_switch. All load computation routes through the working_weight seam
(ADR 0004); progression through the pure functions in engine.progression.
Adding a mode = one handler class + one PROGRESSION_REGISTRY line. See ADR 0005.

Circular-import note (ADR 0005): modes.py imports est1rm_from_history from
. onerm — NOT from ..program. program.py will (in Task 3) import
.get_mode from this module, so importing program here would cycle. The
est1rm_from_history in engine/onerm.py is a verbatim port of the one in
program.py; program.py retains its private copy until Task 3 migrates callers.
"""
from ..data.schema import LiftState, SetEntry
from .onerm import est1rm_from_history
from .progression import (sbs_next, t2_next, t3_next, T2State,
                          round_weight, lookup_schedule)
from .load import working_weight


class Mode:
    """Base progression-mode handler. Subclasses override the four ops."""
    name = ""

    def initial_state(self, lift, settings) -> LiftState:
        raise NotImplementedError

    def advance(self, profile, lift, state, actual, week) -> None:
        raise NotImplementedError

    def plan_fields(self, profile, lift, state, week) -> dict:
        """Return {weight, added, reps, repout, target, streak} for plan display.

        ``weight`` is the WORKING weight (bodyweight term included, ADR 0004);
        ``added`` is the LOADED weight on the bar/belt (the big number, ADR 0007).
        For barbell sbs they are equal; for bodyweight t2/t3 they differ."""
        raise NotImplementedError

    def derive_on_switch(self, lift, history, settings, est1rm) -> dict:
        """Return the new-mode starting state dict (tm/weight/target/streak)."""
        raise NotImplementedError

    # shared helper: append history + recompute est1rm (used by every advance)
    def _record(self, profile, lift, state, actual, week, w) -> None:
        if actual is not None:
            state.history.append(SetEntry(week=week, weight=w, reps=actual))
            state.est1rm = est1rm_from_history(state.history,
                                               profile.bodyweight,
                                               lift.bodyweight_pct)


class SbsMode(Mode):
    name = "sbs"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="sbs", tm=lift.max)

    def advance(self, profile, lift, state, actual, week):
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
        self._record(profile, lift, state, actual, week, w)
        state.tm = sbs_next(state.tm, sc.repout, actual)

    def plan_fields(self, profile, lift, state, week):
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
        return {"weight": w, "added": w, "reps": sc.reps, "repout": sc.repout,
                "target": None, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        tm = est1rm if est1rm is not None else (lift.max or 0.0)  # ADR 0001
        return {"mode": "sbs", "tm": tm, "weight": None, "target": None, "streak": 0}


class LinearT2Mode(Mode):
    name = "linear_t2"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="linear_t2", weight=lift.start,
                         target=8, streak=0)

    def advance(self, profile, lift, state, actual, week):
        w = state.weight
        self._record(profile, lift, state, actual, week, w)
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual, est,
                     fail=profile.t2_fail, incr=eff_incr,
                     reset_pct=profile.t2_reset_pct, quantum=eff_incr)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        return {"weight": w, "added": state.weight or 0.0, "reps": state.target,
                "repout": None, "target": state.target, "streak": state.streak}

    def derive_on_switch(self, lift, history, settings, est1rm):
        eff_incr = lift.incr if lift.incr is not None else settings["incr"]
        w = round_weight(est1rm * settings["t2_reset_pct"], eff_incr) \
            if est1rm is not None else (lift.start or 0.0)
        return {"mode": "linear_t2", "tm": None, "weight": w, "target": 8, "streak": 0}


class LinearT3Mode(Mode):
    name = "linear_t3"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="linear_t3", weight=lift.start)

    def advance(self, profile, lift, state, actual, week):
        w = state.weight
        self._record(profile, lift, state, actual, week, w)
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        state.weight = t3_next(state.weight, actual,
                               target=profile.t3_target, incr=eff_incr)

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        return {"weight": w, "added": state.weight or 0.0, "reps": profile.t3_target,
                "repout": None, "target": profile.t3_target, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        eff_incr = lift.incr if lift.incr is not None else settings["incr"]
        w = round_weight(est1rm * 0.6, eff_incr) \
            if est1rm is not None else (lift.start or 0.0)
        return {"mode": "linear_t3", "tm": None, "weight": w, "target": None, "streak": 0}


class RecordOnlyMode(Mode):
    """Pure-bodyweight record-only mode: no automatic progression (ADR 0005)."""
    name = "none"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="none", weight=lift.start)

    def advance(self, profile, lift, state, actual, week):
        # added weight stays 0 for pure bodyweight; only record + est1rm.
        w = state.weight or 0.0
        self._record(profile, lift, state, actual, week, w)
        # no weight/target mutation — record only

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        last = state.history[-1].reps if state.history else None
        return {"weight": w, "added": state.weight or 0.0, "reps": last,
                "repout": None, "target": None, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        return {"mode": "none", "tm": None, "weight": lift.start or 0.0,
                "target": None, "streak": 0}


PROGRESSION_REGISTRY = {m.name: m for m in
                        (SbsMode(), LinearT2Mode(), LinearT3Mode(), RecordOnlyMode())}


def get_mode(name: str) -> Mode:
    return PROGRESSION_REGISTRY[name]
