"""In-memory data model."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


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
    tier: str           # "sbs" | "t2" | "t3"
    day: int
    # sbs tier
    max: Optional[float] = None
    intensity: float = 0.0
    reps: int = 0
    repout: int = 0
    sets: int = 3
    # t2 / t3
    start: Optional[float] = None
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None for t2/t3
    incr: Optional[float] = None      # t2/t3 per-lift progression step; None = inherit global incr
    # bodyweight lift modeling (ADR 0004). bodyweight_pct == 0.0 -> ordinary lift
    # (working weight == added, unchanged). >0 -> fraction of bodyweight moved
    # (1.0 pull-up/dip, ~0.64 push-up). progression "none" skips auto-progression
    # (pure-bodyweight lifts like crunches progressed by hand).
    bodyweight_pct: float = 0.0
    progression: str = "weight"


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
    tier: str
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
