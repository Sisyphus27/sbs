"""Direct unit test for services/plan.py::assemble_by_day (id-keyed plan grouping).

by_day assembly was a private helper in routes/plan.py::_by_day, covered only
via HTTP. Moved to the service so the route is thin; this asserts the grouping,
day filtering, and per-item log/live decoration directly."""
from webapp import repo
from webapp.services.plan import assemble_by_day


def test_assemble_by_day_groups_and_decorates(db_conn, make_lift):
    a = make_lift(name="A", day=1, sort_order=0, start=30.0)
    make_lift(name="B", day=2, sort_order=0, start=30.0)
    repo.save_log(db_conn, a, 1, 12)
    week, by_day = assemble_by_day(db_conn)
    assert week == 1
    assert [d for d, _ in by_day] == [1, 2]
    a_item = by_day[0][1][0]
    assert a_item.name == "A" and a_item.is_logged is True
    assert a_item.live is not None                  # logged -> live context attached
    b_item = by_day[1][1][0]
    assert b_item.is_logged is False
    assert b_item.live is None                      # not logged -> no fragment


def test_assemble_by_day_skips_days_beyond_days_per_week(db_conn, make_lift):
    make_lift(name="X", day=9, sort_order=0, start=30.0)   # day 9 > days_per_week (4)
    _, by_day = assemble_by_day(db_conn)
    assert by_day == []                             # the only lift sits on a filtered day
