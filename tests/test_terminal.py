import re
from sbs_cli.data.schema import Lift, Profile
from sbs_cli.defaults import DEFAULT_SCHEDULE
from sbs_cli.program import initial_state
from sbs_cli.view.terminal import render_week_text, render_show_text

def _profile():
    # Engine is schedule-driven (Task 4): sbs lifts need lift_kind and the
    # profile must carry a schedule. The CLI path uses DEFAULT_SCHEDULE
    # (the standard 21-week SBS RTF ladder); mirror that here.
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4,
             repout=8, sets=3, lift_kind="main"),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ], schedule=DEFAULT_SCHEDULE)

def test_render_week_text_has_day_and_lifts():
    p = _profile(); s = initial_state(p)
    txt = render_week_text(p, s, week=2)
    assert "Week 2" in txt
    # week_plan reads state.week (=1 here); DEFAULT_SCHEDULE wk1 main intensity 0.70
    # -> round(100*0.70) = 70. The "Week 2" header is a display label only.
    assert "Squat" in txt and "70" in txt      # working weight
    assert "Curls" in txt and "40" in txt

def test_render_show_text_has_est1rm_and_history_count():
    p = _profile(); s = initial_state(p)
    from sbs_cli.program import advance_lift
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=10, week=1)
    txt = render_show_text(p, s)
    assert "Squat" in txt and "est" in txt.lower()
    assert re.search(r"\d+\.\d{2}", txt)          # est1RM renders to 2 decimals
