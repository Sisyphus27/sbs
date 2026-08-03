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
    # beat target 8 by 3 -> +1.5% -> 100*1.015 = 101.5 (raw, TM never rounded)
    assert sbs_next(tm=100, repout=8, actual=11) == 101.5

def test_sbs_miss_drops_pct():
    # miss by 2 -> -5% -> 95
    assert sbs_next(tm=100, repout=8, actual=6) == 95

def test_sbs_beat_5_plus_caps_at_3pct():
    # beat by 6 -> +3% -> 100*1.03 = 103.0 (raw)
    assert sbs_next(tm=100, repout=8, actual=14) == 103.0

def test_sbs_no_log_keeps_tm():
    assert sbs_next(tm=100, repout=8, actual=None) == 100

def test_sbs_miss_by_1_drops_2pct():
    # diff -1 -> -2% -> 100*0.98 = 98.0 (raw)
    assert sbs_next(tm=100, repout=8, actual=7) == 98.0

# --- T3 (threshold) ---
def test_t3_hit_adds():
    assert t3_next(weight=40, actual=16) == 42.5

def test_t3_miss_repeats():
    assert t3_next(weight=40, actual=12) == 40

def test_t3_no_log_repeats():
    assert t3_next(weight=40, actual=None) == 40

# --- T2 (1-strike cascade: 8 -> 6 -> 4, reset after `fail` misses @75% est1rm) ---
def test_t2_hit_adds_weight_stays_at_target():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=8, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=52.5)


def test_t2_miss_at_8_drops_to_6_same_weight():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=1, weight=50)


def test_t2_miss_at_6_drops_to_4_same_weight():
    s = t2_next(T2State(target=6, streak=1, weight=50), actual=5, est1rm=100)
    assert s == T2State(target=4, streak=2, weight=50)


def test_t2_third_miss_resets_anchored_below_failing_weight():
    # streak 2 -> +1 = 3 >= fail(3) -> reset. est1rm=100 来自旧巅峰，>> 失败重量 50。
    # B1: min(100*0.75, 50-2.5) = min(75, 47.5) = 47.5（锚定保证必低于失败重量，破死循环）
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=47.5)


def test_t2_reset_uses_est1rm_pct_when_below_anchor():
    # est1rm*0.75 < weight-incr 时，用 est1rm 分支（min 取小）。est1rm=40 -> 30；anchor=50-2.5=47.5
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=40)
    assert s == T2State(target=8, streak=0, weight=30.0)


def test_t2_reset_anchor_floored_at_zero():
    # weight < incr 时 anchor 防负：max(2.5-5, 0)=0；min(est1rm*0.75, 0)=0
    s = t2_next(T2State(target=4, streak=2, weight=2.5), actual=3, est1rm=100, incr=5)
    assert s == T2State(target=8, streak=0, weight=0.0)


def test_t2_fail_2_resets_after_two_misses():
    # fail=2: miss @8 -> streak1 (<2) drop to 6; miss @6 -> streak2 (>=2) reset
    # est1rm=100 >> weight=50 -> B1 锚定: min(75, 50-2.5)=47.5
    s1 = t2_next(T2State(target=8, streak=0, weight=50), actual=6, est1rm=100, fail=2)
    assert s1 == T2State(target=6, streak=1, weight=50)
    s2 = t2_next(s1, actual=5, est1rm=100, fail=2)
    assert s2 == T2State(target=8, streak=0, weight=47.5)


def test_t2_hit_at_6_does_not_climb_back_to_8():
    s = t2_next(T2State(target=6, streak=1, weight=50), actual=6, est1rm=100)
    assert s == T2State(target=6, streak=0, weight=52.5)


def test_t2_miss_at_4_under_fail_floor_keeps_target():
    # at bottom (4), streak not yet at fail -> stay 4, streak increments
    s = t2_next(T2State(target=4, streak=1, weight=50), actual=3, est1rm=100, fail=4)
    assert s == T2State(target=4, streak=2, weight=50)


def test_t2_no_log_unchanged():
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=None, est1rm=100)
    assert s == T2State(target=8, streak=0, weight=50)


# --- T3 命中精确累加（去 rounding snap；D2）---
def test_t3_hit_adds_incr_without_snapping():
    # incr=3（非 rounding 倍数）：新实现精确 50+3=53；旧实现 round_weight(53, 2.5)=52.5
    assert t3_next(weight=50, actual=16, incr=3) == 53


def test_t3_hit_default_incr_backcompat():
    # 默认 incr=2.5：50+2.5=52.5，与本变更前完全一致
    assert t3_next(weight=50, actual=16) == 52.5


def test_t3_next_signature_has_no_quantum():
    # t3_next 不再接受 quantum 参数（调用方不应再传）
    import inspect
    assert "quantum" not in inspect.signature(t3_next).parameters


# --- T2 命中精确累加（HIT 去 rounding snap；D2）---
def test_t2_hit_adds_incr_without_snapping():
    # incr=3：HIT 时 50+3=53；旧实现 round_weight(53, 2.5)=52.5
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=8, est1rm=100, incr=3)
    assert s == T2State(target=8, streak=0, weight=53)


def test_t2_reset_snaps_to_provided_quantum():
    # reset 分支保留 round_weight(min(est1rm*reset_pct, weight-incr), quantum)：characterization，
    # 锁定 reset 仍由调用方传入的 quantum 决定（Task 3 把 quantum 从 rounding 改为 eff_incr）。
    # B1: min(90*0.75, 50-5) = min(67.5, 45) = 45；round_weight(45, 5)=45（锚定生效，5kg 网格）
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=90,
                incr=5, reset_pct=0.75, quantum=5)
    assert s == T2State(target=8, streak=0, weight=45.0)
