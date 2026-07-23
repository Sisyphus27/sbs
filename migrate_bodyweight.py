"""One-shot: recompute lift_state.est1rm for bodyweight lifts whose stored
value predates the working-weight seam (ADR 0004). Idempotent.

Run once after deploying the bodyweight schema + engine changes against an
existing user DB:
    conda run -n sbs python migrate_bodyweight.py
"""
from sbs_cli.data.schema import SetEntry
from sbs_cli.program import _est1rm_from_history
from webapp.db import connect, init_schema
from webapp.repo import list_lifts, list_history, save_lift_state, get_lift_state


def recompute_bodyweight_est1rm(conn) -> int:
    """Recompute est1rm for every lift with bodyweight_pct > 0. Returns count."""
    n = 0
    for r in list_lifts(conn):
        pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
        if not pct > 0:
            continue
        hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
                for h in list_history(conn, r["id"])]
        if not hist:
            continue
        from webapp.repo import get_settings
        bw = get_settings(conn)["bodyweight"]
        est = _est1rm_from_history(hist, bw, pct)
        st = get_lift_state(conn, r["id"])
        save_lift_state(conn, r["id"], mode=st["mode"], tm=st["tm"], weight=st["weight"],
                        target=st["target"], streak=st["streak"], est1rm=est)
        n += 1
    return n


if __name__ == "__main__":
    conn = connect(); init_schema(conn)
    fixed = recompute_bodyweight_est1rm(conn)
    print(f"recomputed est1rm for {fixed} bodyweight lift(s)")
