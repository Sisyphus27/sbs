from webapp import repo
import re


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


def test_plan_renders_duplicate_names_with_distinct_state(client, app):
    """Same name on two days must render each day's own weight (id-keyed, not clobbered)."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.create_lift(conn, name="Face Pull", tier="t3", day=4, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=45.0)
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert html.count("Face Pull") == 2
    assert "30.0 kg" in html and "45.0 kg" in html   # each day keeps its own weight


def test_plan_submit_advances(client, app):
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                               start=None, lift_kind="main")
        conn.close()
    rv = client.post("/log", data={f"log_{lid}": "13"})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_settings(conn)["week"] == 2
        conn.close()


def test_export_week_standalone_with_progress(client, app):
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                               start=None, lift_kind="main")
        repo.save_log(conn, lid, 1, 11)   # logged this week
        conn.close()
    rv = client.get("/export/week.html")
    assert rv.status_code == 200
    assert "attachment" in rv.headers.get("Content-Disposition", "")
    assert f'week-1.html' in rv.headers.get("Content-Disposition", "")
    html = rv.get_data(as_text=True)
    assert "Week 1" in html and "Squat" in html
    assert "本周末组: 11" in html          # progress shown
    assert "≈" in html                    # live est1RM shown
    assert re.search(r"≈\s*\d+\.\d{2}", html)      # live est1RM renders to 2 decimals
    # standalone / offline: no server-relative deps
    assert "hx-post" not in html and "/log/" not in html and "htmx" not in html


def test_plan_view_shows_week2_schedule_values(client, app):
    """Week-2 plan view pulls intensity/reps/repout from sbs_schedule, not lifts columns.

    Week 2 main schedule = 0.75 / 4 / 8. With tm=100, working weight is
    MROUND(100*0.75, 2.5) = 75.0; the rendered reps/repout come from the schedule
    row (4 / 8), ignoring whatever stale values sit in lifts.intensity/reps/repout.
    """
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=0.7, reps=5, repout=10,
                               start=None, lift_kind="main")
        repo.save_lift_state(conn, lid, tier="sbs", tm=100.0, weight=None,
                             target=None, streak=0, est1rm=None)
        repo.set_week(conn, 2)
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert "Week 2" in html
    assert "75.0 kg" in html          # schedule-driven weight (MROUND(100*0.75,2.5))
    assert "x 4 x 5" in html          # schedule-driven reps (4) x sets (5)
    assert "rep-out 8" in html        # schedule-driven repout (8)


def test_autosave_persists_and_prefills_then_advances(client, app):
    """Daily logging: save per-field (no advance), prefill on reopen, advance consumes saved."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                               start=None, lift_kind="main")
        conn.close()
    # autosave via /log/save (HTMX on change) — no advance, returns live est1RM preview
    rv = client.post(f"/log/save?lid={lid}", data={f"log_{lid}": "11"})
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "≈" in body and "(首次)" in body   # live preview, no history yet
    # input is prefilled from week_log on next render
    assert 'value="11"' in client.get("/").get_data(as_text=True)
    # advancing with an EMPTY form still consumes the saved log
    rv = client.post("/log", data={})
    assert rv.status_code == 302
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_settings(conn)["week"] == 2
        assert repo.get_week_logs(conn, 1) == {}   # cleared after advance
        conn.close()
