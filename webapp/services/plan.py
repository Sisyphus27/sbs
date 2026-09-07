"""Pure presentation helpers shared with the offline plan export."""


def day_states(by_day):
    """Day progress tri-state for the offline export (ADR 0007).

    Returns (days, first_open). days = [(day, state, filled, items)] where state
    is 'full' (all logged or skipped), 'part' (some handled), or
    'empty' (none handled). filled counts logged lifts only.
    first_open = lowest-numbered non-full day, or None when nothing is owed. Pure Python,
    no I/O — unit-testable without a request context."""
    days = []
    first_open = None
    for day, items in by_day:
        filled = sum(it.is_logged and not it.is_skipped for it in items)
        skipped = sum(it.is_skipped for it in items)
        total = len(items)
        handled = filled + skipped
        state = "full" if handled == total else ("part" if handled > 0 else "empty")
        if first_open is None and state != "full":
            first_open = day
        days.append((day, state, filled, items))
    return days, first_open
