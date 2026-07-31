from webapp import repo


def test_plan_view_empty(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Week" in rv.data


def test_plan_renders_duplicate_names_with_distinct_state(client, make_lift):
    """Same name on two days must render each day's own weight (id-keyed, not clobbered)."""
    make_lift(name="Face Pull", day=2, start=30.0)
    make_lift(name="Face Pull", day=4, start=45.0)
    html = client.get("/").get_data(as_text=True)
    assert html.count("Face Pull") == 2
    assert "30.0 kg" in html and "45.0 kg" in html   # each day keeps its own weight


def test_plan_submit_advances(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    rv = client.post("/log", data={f"log_{lid}": "13"})
    assert rv.status_code == 302
    assert repo.get_settings(db_conn)["week"] == 2


def test_plan_submit_form_has_double_click_guard(client):
    """Submit form must disable its buttons on submit (ADR 0010).

    plan.submit is non-idempotent: a double-click double-advances the week.
    The guard is client-side JS, so at the pytest level we assert the opt-in
    marker is present on the rendered form; the JS body itself is not
    unit-tested here (no browser/JS runner in the suite).
    """
    html = client.get("/").get_data(as_text=True)
    assert "data-disable-submit" in html


def test_export_week_standalone_with_progress(client, make_lift, db_conn):
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    repo.save_log(db_conn, lid, 1, 11)   # logged this week
    rv = client.get("/export/week.html")
    assert rv.status_code == 200
    assert "attachment" in rv.headers.get("Content-Disposition", "")
    assert f'week-1.html' in rv.headers.get("Content-Disposition", "")
    html = rv.get_data(as_text=True)
    assert "Week 1" in html and "Squat" in html
    # standalone / offline: no server-relative deps
    assert "hx-post" not in html and "/log/" not in html and "htmx" not in html


def test_plan_view_shows_week2_schedule_values(client, make_lift, db_conn):
    """Week-2 plan view pulls intensity/reps/repout from sbs_schedule, not lifts columns.

    Week 2 main schedule = 0.75 / 4 / 8. With tm=100, working weight is
    MROUND(100*0.75, 2.5) = 75.0; the rendered reps/repout come from the schedule
    row (4 / 8), ignoring whatever stale values sit in lifts.intensity/reps/repout.
    """
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=100.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
    repo.save_lift_state(db_conn, lid, mode="sbs", tm=100.0, weight=None,
                         target=None, streak=0, est1rm=None)
    repo.set_week(db_conn, 2)
    html = client.get("/").get_data(as_text=True)
    assert "Week 2" in html
    assert "75.0 kg" in html          # schedule-driven weight (MROUND(100*0.75,2.5))
    assert "x 4 x 5" in html          # schedule-driven reps (4) x sets (5)
    assert "rep-out 8" in html        # schedule-driven repout (8)


def test_autosave_persists_and_prefills_then_advances(client, make_lift, db_conn):
    """Daily logging: save per-field (no advance), prefill on reopen, advance consumes saved."""
    lid = make_lift(name="Squat", mode="sbs", sets=5, max=135.0, intensity=0.7,
                    reps=5, repout=10, start=None, lift_kind="main")
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
    assert repo.get_settings(db_conn)["week"] == 2
    assert repo.get_week_logs(db_conn, 1) == {}   # cleared after advance


def test_plan_view_shows_tonnage_for_logged_lift(client, make_lift, db_conn):
    """A lift with this week's last-set logged renders its tonnage inline."""
    lid = make_lift(name="Curl", start=30.0)
    repo.save_log(db_conn, lid, 1, 18)   # 30 * (2*15 + 18) = 1440
    db_conn.commit()                     # ADR 0009 batch 2: seed must persist for fresh-conn read
    html = client.get("/").get_data(as_text=True)
    assert "容量" in html and "1440kg" in html


def test_plan_view_shows_first_time_when_no_last_week(client, make_lift, db_conn):
    """Week 1 -> no last week -> tonnage shows 首次."""
    lid = make_lift(name="Curl", start=30.0)
    repo.save_log(db_conn, lid, 1, 18)
    db_conn.commit()                     # ADR 0009 batch 2: seed must persist for fresh-conn read
    html = client.get("/").get_data(as_text=True)
    assert "首次" in html


def test_plan_view_omits_tonnage_when_not_logged(client, make_lift):
    """A lift whose last-set is not yet logged shows no tonnage fragment."""
    make_lift(name="Curl", start=30.0)
    html = client.get("/").get_data(as_text=True)
    assert "容量" not in html


def test_save_log_response_includes_tonnage(client, make_lift):
    """Filling the last-set returns live est1RM + tonnage in the same fragment."""
    lid = make_lift(name="Curl", start=30.0)
    rv = client.post(f"/log/save?lid={lid}", data={f"log_{lid}": "18"})
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "≈" in body                       # est1RM preview still present
    assert "容量" in body and "1440kg" in body   # tonnage computed from the just-typed 18
    assert "首次" in body                    # week 1, no last week


def test_save_log_clear_empties_fragment(client, make_lift, db_conn):
    """Clearing the last-set returns 200 with empty body so .save-ok is wiped."""
    lid = make_lift(name="Curl", start=30.0)
    repo.save_log(db_conn, lid, 1, 18)
    db_conn.commit()                     # ADR 0009 batch 2: release write lock + persist seed
    rv = client.post(f"/log/save?lid={lid}", data={f"log_{lid}": ""})
    assert rv.status_code == 200
    assert rv.get_data(as_text=True) == ""


def test_plan_view_shows_tonnage_wow_delta_for_t2(client, make_lift, db_conn):
    """Two-week t2: past tonnage uses the replayed target; Δ% renders with arrow + color.

    Setup does NOT call advance_week (state.target stays at the initial 8), so:
    - current (week3): planned = state.target = 8, weight = 50, last-set logged 8
      -> 50 * (2*8 + 8) = 1200
    - past (week2): planned = _t2_target_as_of(2) which replays week1 (reps 5 < 8 = miss)
      -> target drops 8->6; past tonnage = 50 * (2*6 + 5) = 850
    - Δ = (1200-850)/850 = +41%
    """
    lid = make_lift(name="Rows", mode="linear_t2", start=50.0)
    repo.append_history(db_conn, lid, week=1, weight=50.0, reps=5)
    repo.append_history(db_conn, lid, week=2, weight=50.0, reps=5)
    repo.set_week(db_conn, 3)
    repo.save_log(db_conn, lid, 3, 8)
    db_conn.commit()                     # ADR 0009 batch 2: save_log no longer self-commits
    html = client.get("/").get_data(as_text=True)
    assert "1200kg" in html        # current tonnage
    assert "↗+41%" in html         # WoW delta: up arrow, +sign, 41%
    assert "首次" not in html       # both weeks present -> no 首次 marker


def test_plan_view_renders_bodyweight_added_plus_working_weight(client, make_lift, db_conn):
    """Bodyweight lift renders '+added (working)' meta format (Task 11).

    Chin-ups t2, start=0, bodyweight=75, pct=1.0 -> working_weight = 0 + 75*1.0 = 75.
    Meta line shows '+0 (75.0) kg' — added is the user's load, working_weight is the
    parenthetical. Non-bodyweight lifts keep the plain '{{ weight }} kg' format.
    """
    repo.update_settings(db_conn, bodyweight=75.0)
    make_lift(name="Chin-ups", load_model="bodyweight", mode="linear_t2",
              day=1, sort_order=1, start=0.0, bodyweight_pct=1.0)
    body = client.get("/").get_data(as_text=True)
    assert "+0" in body              # added load shown with + prefix
    assert "(75" in body             # working_weight shown in parens


def test_export_week_plate_loading_structure(client, make_lift):
    """装片清单：barbell 显示大数字 kg、sbs 方案行含 rep-out、mode tag，无容量/est1RM 状态。"""
    make_lift(name="Squat", mode="sbs", sets=5, max=100.0, start=None, lift_kind="main")
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1"' in html
    assert 'class="wt"' in html and "kg" in html      # 大数字 + 单位
    assert "rep-out" in html                            # sbs 方案行
    assert 'class="tag sbs"' in html                    # mode tag accent
    assert "容量" not in html and "≈" not in html       # live_html/容量 已砍
    assert "最佳 1RM" not in html and "streak" not in html  # est1RM 标签 + t2 streak 已砍


def test_export_week_bodyweight_shows_added_only(client, make_lift, db_conn):
    """bodyweight 动作只显示 +added kg，不显示工作重量括号。"""
    repo.update_settings(db_conn, bodyweight=75.0)
    make_lift(name="Chin-up", load_model="bodyweight", mode="linear_t2",
              start=15.0, bodyweight_pct=1.0)
    html = client.get("/export/week.html").get_data(as_text=True)
    assert "+15" in html          # 加重
    assert "(90." not in html     # 工作重量括号已砍 (15 + 75*1.0 = 90.0); dot avoids CSS rotate(90deg)


def test_export_week_day_tristate_and_default_open(client, make_lift, db_conn):
    """day 三态：全空 day1 + 部分填 day2 → day2 标 ◐ 且默认展开（最小非全填是 day1，但 day1 全空也非全填）。

    构造：day1 一个动作不填（全空）；day2 两动作填一个（部分填）。最小非全填 = day1 → day1 open。
    day2 st-part 带 ◐。"""
    make_lift(name="A", day=1, sort_order=0, start=30.0)
    lid_b1 = make_lift(name="B1", day=2, sort_order=0, start=30.0)
    make_lift(name="B2", day=2, sort_order=1, start=30.0)
    repo.save_log(db_conn, lid_b1, 1, 12)   # day2 填一个 → 部分填
    db_conn.commit()                         # ADR 0009 batch 2: seed must persist for fresh-conn read
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1" class="st-empty" open>' in html   # 最小非全填默认展开
    assert '<details data-day="2" class="st-part">' in html         # 部分填折叠
    assert "◐" in html                                               # 欠账标记


def test_export_week_card_done_mark(client, make_lift, db_conn):
    """卡片级进度：已填末组的动作名字带 ✓ + done class（绿），未填无标记。

    健身房扫一眼即可见 day 内哪些动作练过、哪些待练 — 不靠回忆。"""
    lid_done = make_lift(name="Squat", mode="sbs", sets=5, max=100.0,
                         start=None, lift_kind="main", sort_order=0)
    make_lift(name="Bench", mode="sbs", sets=4, max=80.0,
              start=None, lift_kind="main", sort_order=1)
    repo.save_log(db_conn, lid_done, 1, 10)   # Squat 已填 → 练过；Bench 未填 → 待练
    db_conn.commit()                           # ADR 0009 batch 2: seed must persist for fresh-conn read
    html = client.get("/export/week.html").get_data(as_text=True)
    assert 'class="name done">✓ Squat' in html    # 已填：✓ + done class
    assert 'class="name">Bench' in html            # 未填：无 done、无 ✓
