"""Id-keyed plan assembly: one item per lift row, computed via the mode registry.

Single source for the per-lift display fields the plan view, offline export,
preview, and volume all need. The engine's ``week_plan`` keys state by lift
NAME, so it cannot distinguish two rows that share a name (Face Pull on Day 2
and Day 4). This module keys by row id instead, and delegates every per-mode
weight/rep/target derivation to ``PROGRESSION_REGISTRY[mode].plan_fields`` —
no per-mode if/else lives here (ADR 0005).
"""
import sqlite3
from types import SimpleNamespace

from sbs_cli.engine.modes import get_mode
from .. import repo
from .rows import lift_from_row, profile_from_rows, state_from_rows
from .volume import live_context


def plan_items(conn: sqlite3.Connection):
    """Return (week, items) — one SimpleNamespace per lift row, keyed by id.

    Each item carries: id, name, mode, weight (loaded), working_weight,
    is_bodyweight, reps, sets, repout, target, streak, est1rm, day.
    All weight math comes from the registry's plan_fields; this fn only maps
    rows -> dataclasses -> fields and renames added->weight for template parity.
    """
    settings = repo.get_settings(conn)
    week = settings["week"]
    lift_rows = repo.list_lifts(conn)
    schedule = repo.load_schedule(conn)
    profile = profile_from_rows(settings, [], schedule)
    items = []
    for r in lift_rows:
        st = repo.get_lift_state(conn, r["id"])
        state = state_from_rows(st, repo.list_history(conn, r["id"]))
        lift = lift_from_row(r)
        f = get_mode(r["mode"]).plan_fields(profile, lift, state, week)
        items.append(SimpleNamespace(
            id=r["id"], name=r["name"], mode=r["mode"], day=r["day"],
            weight=f["added"], working_weight=f["weight"],
            is_bodyweight=r["load_model"] in ("bodyweight", "pure_bodyweight"),
            reps=f["reps"], sets=r["sets"], repout=f["repout"],
            target=f["target"], streak=f["streak"], est1rm=st["est1rm"],
        ))
    return week, items


def assemble_by_day(conn: sqlite3.Connection):
    """Group plan items by training day and decorate with this week's logged
    reps + live (est1RM/tonnage) context. Returns ``(week, by_day)`` where
    ``by_day`` is ``[(day, [items])]`` sorted, filtered to ``days_per_week`` and
    non-empty. Each item gains ``.logged``, ``.is_logged``, ``.live`` (the latter
    is :func:`volume.live_context` data, or None when not logged)."""
    week, items = plan_items(conn)
    logged = repo.get_week_logs(conn, week)
    days_per_week = repo.get_settings(conn)["days_per_week"]
    rows_by_day = {}
    for item in items:
        item.logged = logged.get(item.id, "")
        item.is_logged = item.logged not in (None, "")
        item.live = live_context(conn, item.id, item.logged if item.is_logged else None)
        rows_by_day.setdefault(item.day, []).append(item)
    by_day = [(d, rows_by_day[d]) for d in sorted(rows_by_day)
              if d <= days_per_week and rows_by_day[d]]
    return week, by_day


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
