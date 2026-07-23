from sbs_cli.importer import import_profile
from sbs_cli.data.schema import Profile

SRC = r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx"


def test_import_pulls_sbs_maxes():
    p = import_profile(SRC, sheet="4x")
    assert isinstance(p, Profile)
    squat = p.lift("Squat")
    assert squat.mode == "sbs" and squat.load_model == "barbell" and squat.max == 135
    bench = p.lift("Bench Press")
    assert bench.max == 120


def test_import_pulls_back_rows_as_t2():
    p = import_profile(SRC, sheet="4x")
    bb = p.lift("Barbell rows")
    assert bb.mode == "linear_t2" and bb.load_model == "barbell" and bb.start == 85


def test_import_pulls_accessories_as_t3():
    p = import_profile(SRC, sheet="4x")
    le = p.lift("Leg Extension")
    assert le.mode == "linear_t3" and le.load_model == "barbell" and le.start == 40


def test_import_days_per_week_matches_sheet():
    p = import_profile(SRC, sheet="4x")
    assert p.days_per_week == 4


def test_import_does_not_misclassify_next_day_back_row_as_t3():
    p = import_profile(SRC, sheet="4x")
    t3_names = [l.name for l in p.lifts if l.mode == "linear_t3"]
    # DB rows and Pull-downs are BACK lifts (t2), must NOT appear as t3 accessories
    assert "DB rows" not in t3_names
    assert "Pull-downs" not in t3_names
    # Day1 accessories are exactly Leg Extension / Leg Curl / Farmer's Walk
    day1_t3 = [l.name for l in p.lifts if l.mode == "linear_t3" and l.day == 1]
    assert day1_t3 == ["Leg Extension", "Leg Curl", "Farmer's Walk"]


def test_import_back_rows_are_t2_with_correct_day():
    p = import_profile(SRC, sheet="4x")
    t2 = {l.name: l.day for l in p.lifts if l.mode == "linear_t2"}
    assert t2.get("Barbell rows") == 1
    assert t2.get("DB rows") == 2
    assert t2.get("Pull-downs") == 3
    # Chin-ups is "BW" (non-numeric) -> correctly skipped, not in t2
    assert "Chin-ups" not in t2
