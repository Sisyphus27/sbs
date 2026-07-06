import pytest
from sbs_cli.data.schema import ScheduleRow, Lift, Profile
from sbs_cli.engine.progression import schedule_week, cycle_number, lookup_schedule


def test_schedule_week_cyclic():
    assert schedule_week(1) == 1
    assert schedule_week(21) == 21
    assert schedule_week(22) == 1
    assert schedule_week(43) == 1
    assert schedule_week(42) == 21


def test_cycle_number():
    assert cycle_number(1) == 1
    assert cycle_number(21) == 1
    assert cycle_number(22) == 2
    assert cycle_number(43) == 3


def test_lookup_schedule_returns_row_for_current_schedule_week():
    sched = [ScheduleRow("main", 1, 0.70, 5, 10), ScheduleRow("main", 2, 0.75, 4, 8)]
    # program week 2 -> schedule week 2
    assert lookup_schedule(sched, "main", 2) == ScheduleRow("main", 2, 0.75, 4, 8)


def test_lookup_schedule_wraps_after_21():
    sched = [ScheduleRow("aux", 1, 0.60, 7, 14)]  # only week 1 present
    # program week 22 -> schedule week 1
    assert lookup_schedule(sched, "aux", 22).repout == 14


def test_lookup_schedule_missing_row_raises():
    sched = [ScheduleRow("main", 1, 0.70, 5, 10)]
    with pytest.raises(KeyError):
        lookup_schedule(sched, "main", 2)  # schedule week 2 absent


def test_lift_and_profile_carry_new_fields():
    l = Lift(name="Squat", tier="sbs", day=1, lift_kind="main")
    assert l.lift_kind == "main"
    p = Profile(schedule=[ScheduleRow("main", 1, 0.70, 5, 10)])
    assert len(p.schedule) == 1
