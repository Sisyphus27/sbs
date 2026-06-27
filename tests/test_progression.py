from sbs_cli.engine.progression import round_weight, sbs_next, t3_next, t2_next, T2State

# --- round_weight (MROUND parity) ---
def test_round_weight_mround():
    assert round_weight(52.5, 2.5) == 52.5
    assert round_weight(44.0, 2.5) == 45.0      # MROUND(44,2.5)=45
    assert round_weight(55.0 * 0.8, 2.5) == 45.0

# --- SBS tier (TM autoregulation by rep-out delta) ---
def test_sbs_hit_keeps_tm():
    assert sbs_next(tm=100, repout=8, actual=8) == 100

def test_sbs_beat_adds_pct():
    # beat target 8 by 3 -> +1.5% -> 100*1.015 = 101.5 -> MROUND 102.5
    assert sbs_next(tm=100, repout=8, actual=11) == 102.5

def test_sbs_miss_drops_pct():
    # miss by 2 -> -5% -> 95
    assert sbs_next(tm=100, repout=8, actual=6) == 95

def test_sbs_beat_5_plus_caps_at_3pct():
    # beat by 6 -> +3% -> 103 -> MROUND(103,2.5)=102.5
    assert sbs_next(tm=100, repout=8, actual=14) == 102.5

def test_sbs_no_log_keeps_tm():
    assert sbs_next(tm=100, repout=8, actual=None) == 100

def test_sbs_miss_by_1_drops_2pct():
    # diff -1 -> -2% -> 100*0.98 = 98 -> MROUND(98,2.5)=97.5
    assert sbs_next(tm=100, repout=8, actual=7) == 97.5

# --- T3 (threshold) ---
def test_t3_hit_adds():
    assert t3_next(weight=40, actual=16) == 42.5

def test_t3_miss_repeats():
    assert t3_next(weight=40, actual=12) == 40

def test_t3_no_log_repeats():
    assert t3_next(weight=40, actual=None) == 40

# --- T2 (state machine, est1rm reset) ---
def test_t2_hit_adds_weight_keeps_tier():
    s = t2_next(T2State(target=10, streak=0, weight=50), actual=10, est1rm=100)
    assert s == T2State(target=10, streak=0, weight=52.5)

def test_t2_miss_under_threshold_accumulates():
    s = t2_next(T2State(target=10, streak=1, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=10, streak=2, weight=50)

def test_t2_three_misses_10_drops_to_8():
    s = t2_next(T2State(target=10, streak=2, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=50)

def test_t2_three_misses_8_drops_to_6():
    s = t2_next(T2State(target=8, streak=2, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=0, weight=50)

def test_t2_three_misses_6_resets_to_70pct_of_est1rm():
    s = t2_next(T2State(target=6, streak=2, weight=50), actual=4, est1rm=100)
    assert s == T2State(target=10, streak=0, weight=70)

def test_t2_reset_uses_est1rm_not_old_weight():
    # est1rm 110 -> 0.70*110 = 77 -> MROUND(77,2.5)=77.5
    s = t2_next(T2State(target=6, streak=2, weight=50), actual=4, est1rm=110)
    assert s == T2State(target=10, streak=0, weight=77.5)

def test_t2_no_log_carries_state():
    s = t2_next(T2State(target=8, streak=1, weight=50), actual=None, est1rm=100)
    assert s == T2State(target=8, streak=1, weight=50)
