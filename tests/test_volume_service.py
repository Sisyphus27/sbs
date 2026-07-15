from webapp.services.volume import _actual_tonnage


def test_actual_tonnage_basic():
    # 100kg, 3 sets, planned 8, last set 10 -> 100 * (2*8 + 10) = 2600
    assert _actual_tonnage(100.0, 3, 8, 10) == 2600.0


def test_actual_tonnage_single_set():
    # sets=1 -> (1-1)*planned + last = last only -> 100 * 10 = 1000
    assert _actual_tonnage(100.0, 1, 8, 10) == 1000.0


def test_actual_tonnage_zero_or_none_sets_falls_back_to_3():
    assert _actual_tonnage(100.0, 0, 8, 10) == 2600.0
    assert _actual_tonnage(100.0, None, 8, 10) == 2600.0
