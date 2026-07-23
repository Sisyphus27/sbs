import sqlite3
from webapp.db import init_schema
from webapp.repo import create_lift, append_history, save_lift_state, get_lift_state, update_settings


def test_migrate_bodyweight_recomputes_stale_est1rm():
    import migrate_bodyweight
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Dips", load_model="bodyweight", mode="linear_t3",
                      day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    # stale est1rm as it would have been under the OLD (added-only) math:
    save_lift_state(conn, lid, mode="linear_t3", tm=None, weight=0.0, target=None,
                    streak=0, est1rm=0.0)   # added was 0 -> old est1rm 0
    append_history(conn, lid, week=1, weight=0.0, reps=5)
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    st = get_lift_state(conn, lid)
    from sbs_cli.engine.onerm import estimate_1rm
    assert st["est1rm"] == estimate_1rm(75.0, 5)   # now working-weight based
    assert st["est1rm"] > 0.0
    conn.close()


def test_migrate_bodyweight_idempotent():
    # running twice yields the same est1rm
    import migrate_bodyweight
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    lid = create_lift(conn, name="Dips", load_model="bodyweight", mode="linear_t3",
                      day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    save_lift_state(conn, lid, mode="linear_t3", tm=None, weight=0.0, target=None,
                    streak=0, est1rm=0.0)
    append_history(conn, lid, week=1, weight=0.0, reps=5)
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    once = get_lift_state(conn, lid)["est1rm"]
    migrate_bodyweight.recompute_bodyweight_est1rm(conn)
    twice = get_lift_state(conn, lid)["est1rm"]
    assert once == twice
    conn.close()
