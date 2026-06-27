"""YAML load/save for Profile and ProgramState."""
import yaml
from .schema import Lift, Profile, SetEntry, LiftState, ProgramState


# ---------- Profile ----------
def profile_to_dict(p: Profile) -> dict:
    return {
        "rounding": p.rounding, "days_per_week": p.days_per_week, "incr": p.incr,
        "t2_reset_pct": p.t2_reset_pct, "t2_fail": p.t2_fail, "t3_target": p.t3_target,
        "lifts": [
            {k: v for k, v in {
                "name": l.name, "tier": l.tier, "day": l.day, "max": l.max,
                "intensity": l.intensity, "reps": l.reps, "repout": l.repout,
                "sets": l.sets, "start": l.start,
            }.items() if v is not None and v != 0}
            for l in p.lifts
        ],
    }

def profile_from_dict(d: dict) -> Profile:
    lifts = [Lift(
        name=x["name"], tier=x["tier"], day=x["day"],
        max=x.get("max"), intensity=x.get("intensity", 0.0), reps=x.get("reps", 0),
        repout=x.get("repout", 0), sets=x.get("sets", 3), start=x.get("start"),
    ) for x in d.get("lifts", [])]
    return Profile(
        rounding=d.get("rounding", 2.5), days_per_week=d.get("days_per_week", 4),
        incr=d.get("incr", 2.5), t2_reset_pct=d.get("t2_reset_pct", 0.70),
        t2_fail=d.get("t2_fail", 3), t3_target=d.get("t3_target", 15), lifts=lifts,
    )

def save_profile(p: Profile, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile_to_dict(p), f, sort_keys=False, allow_unicode=True)

def load_profile(path: str) -> Profile:
    with open(path, "r", encoding="utf-8") as f:
        return profile_from_dict(yaml.safe_load(f))


# ---------- State ----------
def state_to_dict(s: ProgramState) -> dict:
    out_lifts = {}
    for name, ls in s.lifts.items():
        out_lifts[name] = {
            "tier": ls.tier,
            "tm": ls.tm, "weight": ls.weight, "target": ls.target, "streak": ls.streak,
            "est1rm": ls.est1rm,
            "history": [{"week": h.week, "weight": h.weight, "reps": h.reps} for h in ls.history],
        }
    return {"week": s.week, "lifts": out_lifts}

def state_from_dict(d: dict) -> ProgramState:
    lifts = {}
    for name, x in d.get("lifts", {}).items():
        lifts[name] = LiftState(
            name=name, tier=x["tier"], tm=x.get("tm"), weight=x.get("weight"),
            target=x.get("target"), streak=x.get("streak", 0), est1rm=x.get("est1rm"),
            history=[SetEntry(h["week"], h["weight"], h["reps"]) for h in x.get("history", [])],
        )
    return ProgramState(week=d.get("week", 1), lifts=lifts)

def save_state(s: ProgramState, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(state_to_dict(s), f, sort_keys=False, allow_unicode=True)

def load_state(path: str) -> ProgramState:
    with open(path, "r", encoding="utf-8") as f:
        return state_from_dict(yaml.safe_load(f))
