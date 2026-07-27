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
