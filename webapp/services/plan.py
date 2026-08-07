"""Pure presentation helpers shared with the offline plan export."""


def day_states(by_day):
    """Day progress tri-state for the offline export (ADR 0007).

    Returns (days, first_open). days = [(day, state, filled, items)] where state
    is 'full' (all logged), 'part' (some logged — an owed debt, surfaced), or
    'empty' (none logged). first_open = lowest-numbered non-full day (the
    next-to-train); falls back to the last day when all are full. Pure Python,
    no I/O — unit-testable without a request context."""
    days = []
    first_open = None
    for day, items in by_day:
        filled = sum(1 for it in items if it.is_logged)
        total = len(items)
        state = "full" if filled == total else ("part" if filled > 0 else "empty")
        if first_open is None and state != "full":
            first_open = day
        days.append((day, state, filled, items))
    if first_open is None and days:
        first_open = days[-1][0]
    return days, first_open
