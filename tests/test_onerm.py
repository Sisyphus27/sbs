import math
from sbs_cli.engine.onerm import estimate_1rm, epley, brzycki, wathan

def test_epley_formula():
    assert abs(epley(100, 5) - 116.6667) < 0.01

def test_brzycki_formula():
    assert abs(brzycki(100, 5) - 112.5) < 0.01

def test_wathan_formula():
    expected = 100 * 100 / (48.8 + 53.8 * math.exp(-0.075 * 5))
    assert abs(wathan(100, 5) - expected) < 1e-9

def test_estimate_is_mean_of_three():
    w, r = 100, 5
    expected = (epley(w, r) + brzycki(w, r) + wathan(w, r)) / 3
    assert abs(estimate_1rm(w, r) - expected) < 1e-9

def test_estimate_single_rep_returns_about_weight():
    assert abs(estimate_1rm(100, 1) - 100) < 3.0

def test_estimate_higher_reps_exceeds_low_rep_at_same_weight():
    assert estimate_1rm(80, 8) > estimate_1rm(80, 3)
