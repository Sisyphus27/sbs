import re
from sbs_cli.data.schema import Lift, Profile
from sbs_cli.program import initial_state
from sbs_cli.view.terminal import render_week_text, render_show_text

def _profile():
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])

def test_render_week_text_has_day_and_lifts():
    p = _profile(); s = initial_state(p)
    txt = render_week_text(p, s, week=2)
    assert "Week 2" in txt
    assert "Squat" in txt and "75" in txt      # working weight
    assert "Curls" in txt and "40" in txt

def test_render_show_text_has_est1rm_and_history_count():
    p = _profile(); s = initial_state(p)
    from sbs_cli.program import advance_lift
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=10, week=1)
    txt = render_show_text(p, s)
    assert "Squat" in txt and "est" in txt.lower()
    assert re.search(r"\d+\.\d{2}", txt)          # est1RM renders to 2 decimals
