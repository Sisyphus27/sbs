from sbs_cli.defaults import (DEFAULT_SETTINGS, MAIN_LADDER, AUX_LADDER,
                              DEFAULT_SCHEDULE, RESETTABLE_FIELDS)


def test_default_settings_exclude_weight_params():
    assert DEFAULT_SETTINGS == {"days_per_week": 4, "t2_reset_pct": 0.75,
                                 "t2_fail": 3, "t3_target": 15}
    assert "rounding" not in DEFAULT_SETTINGS
    assert "incr" not in DEFAULT_SETTINGS


def test_resettable_fields_match():
    assert RESETTABLE_FIELDS == ("days_per_week", "t2_reset_pct", "t2_fail", "t3_target")


def test_ladders_have_21_weeks():
    assert len(MAIN_LADDER) == 21
    assert len(AUX_LADDER) == 21
    assert [w for w, *_ in MAIN_LADDER] == list(range(1, 22))
    assert [w for w, *_ in AUX_LADDER] == list(range(1, 22))


def test_main_week1_and_deloads():
    # (week, intensity, reps, repout)
    assert MAIN_LADDER[0] == (1, 0.70, 5, 10)
    assert MAIN_LADDER[1] == (2, 0.75, 4, 8)
    assert MAIN_LADDER[6] == (7, 0.60, 7, 14)   # deload
    assert MAIN_LADDER[20] == (21, 0.60, 7, 14)  # deload


def test_aux_week1_and_deloads():
    assert AUX_LADDER[0] == (1, 0.60, 7, 14)
    assert AUX_LADDER[1] == (2, 0.65, 6, 12)
    assert AUX_LADDER[6] == (7, 0.50, 8, 18)    # deload


def test_default_schedule_is_42_rows():
    assert len(DEFAULT_SCHEDULE) == 42
    kinds = {r.kind for r in DEFAULT_SCHEDULE}
    assert kinds == {"main", "aux"}
