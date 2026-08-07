import math
from sbs_cli.data.schema import SetEntry
from sbs_cli.engine.onerm import (
    best_1rm,
    brzycki,
    epley,
    estimate_1rm,
    est1rm_from_history,
    wathan,
)

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


def test_zero_rep_attempt_is_unavailable_for_e1rm():
    history = [SetEntry(week=1, weight=100, reps=0)]

    assert best_1rm(history) is None
    assert est1rm_from_history(history) is None
