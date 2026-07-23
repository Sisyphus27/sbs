"""In-memory data model."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# --- Training-mode unification (ADR 0005) ---
# load_model: how resistance is expressed; mode: how progression is driven.
# LEGAL_COMBOS binds them 1:1 for pure_bodyweight (must pair with "none") and
# otherwise allows only legal (load_model, mode) pairings.
LOAD_MODELS = ("barbell", "bodyweight", "pure_bodyweight")
MODES = ("sbs", "linear_t2", "linear_t3", "none")

# Legal (load_model, mode) combos (ADR 0005). none<->pure_bodyweight bound 1:1;
# barbell/bodyweight must follow some progression; sbs is barbell-only.
LEGAL_COMBOS = frozenset({
    ("barbell", "sbs"), ("barbell", "linear_t2"), ("barbell", "linear_t3"),
    ("bodyweight", "linear_t2"), ("bodyweight", "linear_t3"),
    ("pure_bodyweight", "none"),
})


def is_legal_combo(load_model: str, mode: str) -> bool:
    return (load_model, mode) in LEGAL_COMBOS


@dataclass(frozen=True)
class ScheduleRow:
    kind: str            # "main" | "aux"
    week: int            # 1..21
    intensity: float
    reps: int
    repout: int


@dataclass
class Lift:
    """A lift definition in profile.yaml (static)."""
    name: str
    day: int
    load_model: str = "barbell"   # "barbell" | "bodyweight" | "pure_bodyweight"
    mode: str = "none"            # "sbs" | "linear_t2" | "linear_t3" | "none"
    max: Optional[float] = None
    intensity: float = 0.0
    reps: int = 0
    repout: int = 0
    sets: int = 3
    start: Optional[float] = None
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None otherwise
    incr: Optional[float] = None      # linear_t2/t3 per-lift step; None = inherit global
    # Load parameter (ADR 0004), NOT a mode marker. 0.0 barbell; >0 bodyweight
    # fraction (1.0 pull-up/dip, ~0.64 push-up). Hand-entered, default 1.0 for pure.
    bodyweight_pct: float = 0.0


@dataclass
class Profile:
    rounding: float = 2.5
    days_per_week: int = 4
    incr: float = 2.5
    t2_reset_pct: float = 0.75
    t2_fail: int = 3
    t3_target: int = 15
    bodyweight: float = 0.0   # user bodyweight (kg), global; feeds working_weight()
    lifts: List[Lift] = field(default_factory=list)
    schedule: List[ScheduleRow] = field(default_factory=list)

    def lift(self, name: str) -> Lift:
        for l in self.lifts:
            if l.name == name:
                return l
        raise KeyError(name)


@dataclass
class SetEntry:
    week: int
    weight: float
    reps: int


@dataclass
class LiftState:
    """Per-lift dynamic state in state.yaml."""
    name: str
    mode: str
    # sbs
    tm: Optional[float] = None
    # t2 / t3
    weight: Optional[float] = None
    target: Optional[int] = None     # t2 only (10/8/6)
    streak: int = 0                  # t2 only
    # computed
    est1rm: Optional[float] = None
    history: List[SetEntry] = field(default_factory=list)


@dataclass
class ProgramState:
    week: int = 1
    lifts: Dict[str, LiftState] = field(default_factory=dict)
