import json
import re
from sbs_cli.data.schema import Lift, Profile
from sbs_cli.defaults import DEFAULT_SCHEDULE
from sbs_cli.program import initial_state
from sbs_cli.view.html import render_week_html, parse_log_json

def _profile():
    # Engine is schedule-driven (Task 4): sbs lifts need lift_kind and the
    # profile must carry a schedule. The CLI path uses DEFAULT_SCHEDULE
    # (the standard 21-week SBS RTF ladder); mirror that here.
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4,
             repout=8, sets=3, lift_kind="main"),
        Lift(name="Barbell rows", tier="t2", day=1, start=50),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ], schedule=DEFAULT_SCHEDULE)

def test_render_html_has_input_per_lift_and_export_button():
    p = _profile(); s = initial_state(p)
    html = render_week_html(p, s, week=1)
    assert 'data-lift="Squat"' in html
    assert 'data-lift="Barbell rows"' in html
    assert 'data-lift="Curls"' in html
    assert "Export results" in html and "week-1-log.json" in html
    assert "est1RM" in html or "est 1RM" in html  # shows estimate

def test_render_html_shows_weights():
    p = _profile(); s = initial_state(p)
    html = render_week_html(p, s, week=1)
    # Week-1 DEFAULT_SCHEDULE main row is (0.70, 5, 10) -> round(100*0.70) = 70
    assert "70" in html        # Squat working weight (week 1 main intensity 0.70)
    assert "50" in html        # Barbell rows start
    assert "40" in html        # Curls start

def test_parse_log_json_reads_filled_values_ignores_blanks():
    log = {"week": 1, "logs": {"Squat": 11, "Curls": 15}}   # Barbell rows blank
    parsed = parse_log_json(json.dumps(log))
    assert parsed["week"] == 1
    assert parsed["logs"] == {"Squat": 11, "Curls": 15}
    assert "Barbell rows" not in parsed["logs"]


def test_render_html_est1rm_two_decimals():
    p = _profile(); s = initial_state(p)
    from sbs_cli.program import advance_lift
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=11, week=1)
    html = render_week_html(p, s, week=1)
    assert re.search(r"est 1RM \d+\.\d{2}", html)   # est1RM renders to 2 decimals (anchored on label)
