"""Direct unit tests for services.plan.day_states — the day progress tri-state,
now computable without a request context or template render (ADR 0007)."""
from types import SimpleNamespace
from webapp.services.plan import day_states as _day_states


def _item(is_logged):
    return SimpleNamespace(is_logged=is_logged)


def test_empty_day_state():
    days, first_open = _day_states([(1, [_item(False), _item(False)])])
    assert days[0][1] == "empty" and days[0][2] == 0
    assert first_open == 1  # empty day is the next-to-train


def test_part_day_is_owed_debt():
    days, _ = _day_states([(2, [_item(True), _item(False)])])
    assert days[0][1] == "part" and days[0][2] == 1


def test_full_day_collapses_and_yields_open_to_next():
    days, first_open = _day_states([
        (1, [_item(True), _item(True)]),   # full
        (2, [_item(True), _item(False)]),  # part -> lowest non-full
        (3, [_item(False)]),               # empty
    ])
    assert [d[1] for d in days] == ["full", "part", "empty"]
    assert first_open == 2  # owed partial day surfaces before the empty one


def test_all_full_falls_back_to_last_day():
    days, first_open = _day_states([
        (1, [_item(True)]),
        (2, [_item(True)]),
    ])
    assert all(d[1] == "full" for d in days)
    assert first_open == 2  # nothing owed -> stay on the last day


def test_empty_input():
    days, first_open = _day_states([])
    assert days == [] and first_open is None
