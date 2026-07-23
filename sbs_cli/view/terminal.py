"""Plain-text plan + status for the terminal."""
from ..program import week_plan


def render_week_text(profile, state, week: int) -> str:
    lines = [f"=== Week {week} ==="]
    for day in range(1, profile.days_per_week + 1):
        items = week_plan(profile, state, day=day)
        if not items:
            continue
        lines.append(f"\n-- Day {day} --")
        for it in items:
            est = f"  est1RM {it.est1rm:.2f}" if it.est1rm else ""
            if it.mode == "sbs":
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.reps} x {it.sets}  (repout {it.repout}){est}")
            elif it.mode == "linear_t2":
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.target} x {it.sets}  (streak {it.streak}){est}")
            else:
                lines.append(f"{it.name:18} {it.weight:>5} kg x {it.target}+ x {it.sets}{est}")
    return "\n".join(lines)


def render_show_text(profile, state) -> str:
    lines = [f"=== Week {state.week} status ==="]
    for l in profile.lifts:
        ls = state.lifts.get(l.name)
        if not ls:
            continue
        hist = len(ls.history)
        est = f"  est1RM {ls.est1rm:.2f}" if ls.est1rm else ""
        if l.mode == "sbs":
            lines.append(f"{l.name:18} TM {ls.tm:.1f}  hist {hist}{est}")
        elif l.mode == "linear_t2":
            lines.append(f"{l.name:18} {ls.weight} kg  3x{ls.target}  streak {ls.streak}  hist {hist}{est}")
        else:
            lines.append(f"{l.name:18} {ls.weight} kg  hist {hist}{est}")
    return "\n".join(lines)
