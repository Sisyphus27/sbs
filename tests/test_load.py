from sbs_cli.engine.load import working_weight


def test_ordinary_lift_pct_zero_returns_added_unchanged():
    # ordinary barbell lift: no bodyweight component
    assert working_weight(100.0, 75.0, 0.0) == 100.0


def test_full_bodyweight_zero_added():
    # chin-up, no belt: working weight = full bodyweight
    assert working_weight(0.0, 75.0, 1.0) == 75.0


def test_weighted_bodyweight_added_plus_bw():
    # chin-up +2.5 kg belt
    assert working_weight(2.5, 75.0, 1.0) == 77.5


def test_partial_bodyweight_pushup():
    # push-up moves ~64% of bodyweight
    assert working_weight(0.0, 75.0, 0.64) == 48.0
