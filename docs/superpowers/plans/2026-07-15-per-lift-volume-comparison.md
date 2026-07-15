# Per-lift 周容量对比(实际吨位 WoW)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本周计划页(`/`)每个动作行内联显示该动作「本周实际吨位 vs 上周」对比(`1234kg ↗+15%`),填末组即时更新。

**Architecture:** 新增 DB-reading service `webapp/services/volume.py`(镜像 `preview.live_preview`)算每动作每周实际吨位;route 层 `_live_html` helper 把 est1RM 预览 + 吨位片段拼进现有 `.save-ok` HTMX 目标区,初始加载预渲染 + 填末组即时刷新。t2 上周 target 复用 `recompute_state` 传过滤 history,零引擎改动。

**Tech Stack:** Python 3 / Flask / Jinja2 / htmx / SQLite / pytest。spec:`docs/superpowers/specs/2026-07-15-per-lift-volume-comparison-design.md`。

## Global Constraints

- 所有 Python 跑在 conda env `sbs`:`conda run -n sbs pytest ...` / `conda run -n sbs python ...`
- TDD:先写失败测试 → 跑红 → 最小实现 → 跑绿 → commit。每个 step 独立。
- 频繁 commit,conventional commit 格式(`feat:`/`test:`/`refactor:`)。**禁止 `git add -A`**,只 add 本任务文件。
- 用户可见串中文(`容量`/`首次`)。
- **零改动**:`sbs_cli/*` 引擎、`webapp/repo.py`、`webapp/db.py` schema、迁移脚本。
- 复用现有 helper:`preview._working_weight`、`advance._lift_from_row`/`_profile_from_rows`、`program.recompute_state`。
- 吨位公式:`weight × ((sets-1) × plannedReps + lastSetReps)`;末组=输入框填入值。
- schedule 默认值(main wk1: intensity 0.70 / reps 5 / repout 10;t3_target=15)。

---

## File Structure

| 文件 | 责任 | 任务 |
|------|------|------|
| `webapp/services/volume.py`(新)| 单动作单周实际吨位计算:纯公式 + t2 replay + DB 编排 | T1-T3 |
| `tests/test_volume_service.py`(新)| volume service 单元测试 | T1-T3 |
| `webapp/routes/plan.py` | `_tonnage_html`/`_live_html` helper + `_by_day` 预渲染 + `save_log` 重构返回 `_live_html` | T4 |
| `webapp/templates/plan.html` | `.save-ok` 预填 `it.live_html` | T4 |
| `tests/test_routes_plan.py` | 路由层:初始渲染 + save_log 响应含吨位 | T4 |

**不改**:`base.html`(片段在 `.save-ok` 内,复用现有 `.save-ok .up/.down/.first` 配色)、引擎、repo、schema。

---

### Task 1: `_actual_tonnage` 纯函数

**Files:**
- Create: `webapp/services/volume.py`
- Test: `tests/test_volume_service.py`

**Interfaces:**
- Produces: `_actual_tonnage(weight: float, sets: int, planned_reps: int, last_set_reps: int) -> float` —— 纯公式 `weight × ((sets-1) × planned + last)`,`sets` 为 0/None 时按 3。

- [ ] **Step 1: Write the failing test**

Create `tests/test_volume_service.py`:

```python
from webapp.services.volume import _actual_tonnage


def test_actual_tonnage_basic():
    # 100kg, 3 sets, planned 8, last set 10 -> 100 * (2*8 + 10) = 2600
    assert _actual_tonnage(100.0, 3, 8, 10) == 2600.0


def test_actual_tonnage_single_set():
    # sets=1 -> (1-1)*planned + last = last only -> 100 * 10 = 1000
    assert _actual_tonnage(100.0, 1, 8, 10) == 1000.0


def test_actual_tonnage_zero_or_none_sets_falls_back_to_3():
    assert _actual_tonnage(100.0, 0, 8, 10) == 2600.0
    assert _actual_tonnage(100.0, None, 8, 10) == 2600.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webapp.services.volume'`

- [ ] **Step 3: Write minimal implementation**

Create `webapp/services/volume.py`:

```python
"""Per-lift actual tonnage (training volume) for a given program week.

Reads the same DB the plan view reads; computes weight x total reps where
every set but the last is taken at its planned rep count and the last set
uses the logged reps (the 末组 entry). Read-only; writes nothing.
See docs/superpowers/specs/2026-07-15-per-lift-volume-comparison-design.md
"""


def _actual_tonnage(weight: float, sets: int, planned_reps: int, last_set_reps: int) -> float:
    """weight x total reps: (sets-1) sets at planned_reps + last set at last_set_reps."""
    sets = sets or 3
    return weight * ((sets - 1) * planned_reps + last_set_reps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add webapp/services/volume.py tests/test_volume_service.py
git commit -m "feat(volume): _actual_tonnage pure formula"
```

---

### Task 2: `_t2_target_as_of` replay helper

**Files:**
- Modify: `webapp/services/volume.py`
- Test: `tests/test_volume_service.py`

**Interfaces:**
- Consumes: `repo.get_lift` / `repo.get_settings` / `repo.load_schedule` / `repo.list_history`,`advance._lift_from_row` / `advance._profile_from_rows`,`program.recompute_state`,`sbs_cli.data.schema.SetEntry`
- Produces: `_t2_target_as_of(conn, lift_id, target_week) -> int` —— 进入 `target_week` 前的 t2 target(replay `week < target_week` 的 history);无历史返回初始 8。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_volume_service.py`:

```python
from webapp import db, repo
from webapp.services.volume import _t2_target_as_of


def _t2(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=50.0)
    return conn, lid


def test_t2_target_as_of_initial_when_no_prior_history(tmp_path):
    # target_week=1 -> replay weeks<1 = [] -> initial target 8
    conn, lid = _t2(tmp_path)
    assert _t2_target_as_of(conn, lid, 1) == 8
    conn.close()


def test_t2_target_as_of_replays_miss_drop(tmp_path):
    # week1 logged 5 reps (< target 8) -> miss -> target drops 8->6.
    # target_week=2 -> replay weeks<2 = [week1] -> target entering week2 = 6.
    conn, lid = _t2(tmp_path)
    repo.append_history(conn, lid, week=1, weight=50.0, reps=5)
    assert _t2_target_as_of(conn, lid, 2) == 6
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_volume_service.py::test_t2_target_as_of_initial_when_no_prior_history tests/test_volume_service.py::test_t2_target_as_of_replays_miss_drop -v`
Expected: FAIL — `ImportError: cannot import name '_t2_target_as_of'`

- [ ] **Step 3: Write minimal implementation**

Add to `webapp/services/volume.py` (after `_actual_tonnage`):

```python
import sqlite3

from sbs_cli.data.schema import SetEntry
from sbs_cli.program import recompute_state
from .. import repo
from . import advance as advance_service


def _t2_target_as_of(conn: sqlite3.Connection, lift_id: int, target_week: int) -> int:
    """t2 target ENTERING target_week = replay history rows with week < target_week.

    Reuses program.recompute_state by feeding it the history filtered to
    week < target_week; it returns the lift state as of that cutoff, whose
    .target is the target used during target_week. Mirrors
    webapp/services/recompute.py::recompute_on_start_change (lifts=[] is safe;
    recompute_state does not iterate profile.lifts). Returns initial 8 when
    there is no prior history.
    """
    lift_row = repo.get_lift(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lift_id) if h["week"] < target_week]
    if not hist:
        return 8  # initial t2 target (see repo._init_lift_state / advance_lift)
    lift = advance_service._lift_from_row(lift_row)
    profile = advance_service._profile_from_rows(settings, [], schedule)
    return recompute_state(lift, hist, profile).target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add webapp/services/volume.py tests/test_volume_service.py
git commit -m "feat(volume): _t2_target_as_of via filtered-history replay"
```

---

### Task 3: `lift_week_volume` DB service

**Files:**
- Modify: `webapp/services/volume.py`
- Test: `tests/test_volume_service.py`

**Interfaces:**
- Consumes: `_actual_tonnage`,`_t2_target_as_of`,`preview._working_weight`,`repo.*`,`lookup_schedule`
- Produces: `lift_week_volume(conn, lift_id, week, is_current) -> float | None` —— 单动作单周实际吨位;本周 `week_log` 无记录或过去周无 history 行 → `None`(跳过)。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_volume_service.py`:

```python
from webapp.services.volume import lift_week_volume


def _sbs(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=100.0, intensity=0.7, reps=5, repout=10,
                           start=None, lift_kind="main")
    repo.save_lift_state(conn, lid, tier="sbs", tm=100.0, weight=None,
                         target=None, streak=0, est1rm=None)
    return conn, lid


def test_volume_current_sbs(tmp_path):
    # tm=100, week1 main: intensity 0.70 -> weight=70, planned reps=5, sets=5.
    # logged last=10 -> 70 * (4*5 + 10) = 70 * 30 = 2100
    conn, lid = _sbs(tmp_path)
    repo.save_log(conn, lid, 1, 10)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 2100.0
    conn.close()


def test_volume_current_not_logged_returns_none(tmp_path):
    conn, lid = _sbs(tmp_path)
    assert lift_week_volume(conn, lid, 1, is_current=True) is None
    conn.close()


def test_volume_past_week_from_history(tmp_path):
    # last week (week1): history weight 70, reps 10, planned 5, sets 5 -> 2100
    conn, lid = _sbs(tmp_path)
    repo.set_week(conn, 2)
    repo.append_history(conn, lid, week=1, weight=70.0, reps=10)
    assert lift_week_volume(conn, lid, 1, is_current=False) == 2100.0
    conn.close()


def test_volume_past_week_missing_returns_none(tmp_path):
    conn, lid = _sbs(tmp_path)
    assert lift_week_volume(conn, lid, 1, is_current=False) is None
    conn.close()


def test_volume_current_t3(tmp_path):
    # t3 start=30, sets=3, t3_target=15, logged last=18 -> 30 * (2*15 + 18) = 30*48 = 1440
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
    repo.save_log(conn, lid, 1, 18)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 1440.0
    conn.close()


def test_volume_current_t2(tmp_path):
    # t2 start=50, target=8 (initial), sets=3, logged last=8 -> 50 * (2*8 + 8) = 50*24 = 1200
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=50.0)
    repo.save_log(conn, lid, 1, 8)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 1200.0
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'lift_week_volume'`

- [ ] **Step 3: Write minimal implementation**

Add to `webapp/services/volume.py` (after `_t2_target_as_of`):

```python
from typing import Optional

from sbs_cli.engine.progression import lookup_schedule
from . import preview


def lift_week_volume(conn: sqlite3.Connection, lift_id: int, week: int,
                     is_current: bool) -> Optional[float]:
    """Actual tonnage for one lift in one program week.

    weight x ((sets-1) x plannedReps + lastSetReps). Returns None when there
    is no logged last-set reps for that week (current: week_log empty; past:
    no history row) so the caller can skip rendering.
    """
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    settings = repo.get_settings(conn)
    schedule = repo.load_schedule(conn)
    tier = lift["tier"]
    sets = lift["sets"] or 3

    if is_current:
        last_set = repo.get_week_logs(conn, week).get(lift_id)
        if last_set is None:
            return None
        weight = preview._working_weight(lift, state, settings, schedule)
    else:
        row = next((h for h in repo.list_history(conn, lift_id) if h["week"] == week), None)
        if row is None:
            return None
        last_set = row["reps"]
        weight = row["weight"]

    if tier == "sbs":
        planned = lookup_schedule(schedule, lift["lift_kind"], week).reps
    elif tier == "t3":
        planned = settings["t3_target"]
    else:  # t2
        planned = state["target"] if is_current else _t2_target_as_of(conn, lift_id, week)

    return _actual_tonnage(weight, sets, planned, last_set)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_volume_service.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add webapp/services/volume.py tests/test_volume_service.py
git commit -m "feat(volume): lift_week_volume DB service (sbs/t2/t3, current/past)"
```

---

### Task 4: 接入 plan UI(初始渲染 + 填末组即时更新)

**Files:**
- Modify: `webapp/routes/plan.py`
- Modify: `webapp/templates/plan.html`
- Test: `tests/test_routes_plan.py`

**Interfaces:**
- Consumes: `lift_week_volume`(T3),`preview.live_preview`
- Produces: plan.py 模块级 `_tonnage_html(conn, lid) -> str` 与 `_live_html(conn, lid, reps) -> str`;`_by_day` 每 item 挂 `item.live_html`;plan.html `.save-ok` 渲染 `{{ it.live_html|safe }}`;`save_log` 返回 `_live_html`(取代原 est1RM-only 串),清空路径返回 `("", 200)`。

> 设计说明:`_live_html` 同时被 `_by_day`(初始预渲染)和 `save_log`(HTMX 即时刷新)调用——**单一 helper,零重复**。它合并 est1RM 预览 + 吨位片段,因为两者都活在同一个 `.save-ok` HTMX 目标区,且都依赖刚填入的末组次数。

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_routes_plan.py`:

```python
def test_plan_view_shows_tonnage_for_logged_lift(client, app):
    """A lift with this week's last-set logged renders its tonnage inline."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.save_log(conn, lid, 1, 18)   # 30 * (2*15 + 18) = 1440
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert "容量" in html and "1440kg" in html


def test_plan_view_shows_first_time_when_no_last_week(client, app):
    """Week 1 -> no last week -> tonnage shows 首次."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.save_log(conn, lid, 1, 18)
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert "首次" in html


def test_plan_view_omits_tonnage_when_not_logged(client, app):
    """A lift whose last-set is not yet logged shows no tonnage fragment."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        conn.close()
    html = client.get("/").get_data(as_text=True)
    assert "容量" not in html


def test_save_log_response_includes_tonnage(client, app):
    """Filling the last-set returns live est1RM + tonnage in the same fragment."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        conn.close()
    rv = client.post(f"/log/save?lid={lid}", data={f"log_{lid}": "18"})
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "≈" in body                       # est1RM preview still present
    assert "容量" in body and "1440kg" in body   # tonnage computed from the just-typed 18
    assert "首次" in body                    # week 1, no last week


def test_save_log_clear_empties_fragment(client, app):
    """Clearing the last-set returns 200 with empty body so .save-ok is wiped."""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.save_log(conn, lid, 1, 18)
        conn.close()
    rv = client.post(f"/log/save?lid={lid}", data={f"log_{lid}": ""})
    assert rv.status_code == 200
    assert rv.get_data(as_text=True) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n sbs pytest tests/test_routes_plan.py -v`
Expected: FAIL — `assert '容量' in ...`(初始渲染缺失)+ save_log 响应缺 `容量`

- [ ] **Step 3: Add the helper functions to plan.py**

In `webapp/routes/plan.py`, add two module-level helpers (after the imports, before `_by_day`):

```python
def _tonnage_html(conn, lid):
    """容量 WoW fragment, or '' if this week's last-set isn't logged yet."""
    from ..services.volume import lift_week_volume
    week = repo.get_settings(conn)["week"]
    this = lift_week_volume(conn, lid, week, is_current=True)
    if this is None:
        return ""
    last = lift_week_volume(conn, lid, week - 1, is_current=False) if week > 1 else None
    kg = f'容量 {this:.0f}kg'
    if not last:  # None (no history) or 0 -> avoid div-by-zero
        return f'{kg} <span class="first">首次</span>'
    pct = (this - last) / last * 100
    if pct >= 0:
        cls, arrow, sign = "up", "↗", "+"
    else:
        cls, arrow, sign = "down", "↘", ""
    return f'{kg} <span class="{cls}">{arrow}{sign}{pct:.0f}%</span>'


def _live_html(conn, lid, reps):
    """.save-ok content: est1RM preview + tonnage WoW. '' when reps is None.

    Single helper used by both _by_day (initial pre-render) and save_log
    (HTMX live refresh), so the est1RM HTML exists in exactly one place.
    """
    if reps is None:
        return ""
    from ..services.preview import live_preview
    p = live_preview(conn, lid, reps)
    if p["delta"] is None:
        delta_html = '<span class="first">(首次)</span>'
    else:
        cls = "up" if p["delta"] >= 0 else "down"
        sign = "+" if p["delta"] >= 0 else ""
        delta_html = f'<span class="{cls}">{sign}{p["delta"]:.2f}</span>'
    return f'≈{p["est1rm"]:.2f} {delta_html} {_tonnage_html(conn, lid)}'.strip()
```

- [ ] **Step 4: Pre-render `live_html` in `_by_day`**

In `webapp/routes/plan.py::_by_day`, the item-building loop currently ends with:

```python
        item.logged = logged.get(r["id"], "")
        rows_by_day.setdefault(r["day"], []).append(item)
```

Change to compute `live_html` from the logged reps:

```python
        item.logged = logged.get(r["id"], "")
        reps = item.logged if item.logged not in (None, "") else None
        item.live_html = _live_html(conn, item.id, reps)
        rows_by_day.setdefault(r["day"], []).append(item)
```

- [ ] **Step 5: Refactor `save_log` to use `_live_html`**

In `webapp/routes/plan.py::save_log`, replace the est1RM-building tail:

```python
    repo.save_log(conn, lid, week, reps)
    from ..services.preview import live_preview
    p = live_preview(conn, lid, reps)
    if p["delta"] is None:
        delta_html = '<span class="first">(首次)</span>'
    else:
        cls = "up" if p["delta"] >= 0 else "down"
        sign = "+" if p["delta"] >= 0 else ""
        delta_html = f'<span class="{cls}">{sign}{p["delta"]:.2f}</span>'
    return f'≈{p["est1rm"]:.2f} {delta_html}'
```

with:

```python
    repo.save_log(conn, lid, week, reps)
    return _live_html(conn, lid, reps)
```

And change the empty-input branch from `return ("", 204)` to `return ("", 200)` so htmx swaps `.save-ok` to empty. The branch currently reads:

```python
    if raw == "":
        repo.clear_one_log(conn, lid, week)
        return ("", 204)
```

change to:

```python
    if raw == "":
        repo.clear_one_log(conn, lid, week)
        return ("", 200)
```

- [ ] **Step 6: Render the fragment in plan.html**

In `webapp/templates/plan.html`, change the empty `.save-ok` span:

```html
          <span class="save-ok"></span>
```

to pre-fill from the server:

```html
          <span class="save-ok">{{ it.live_html|safe }}</span>
```

- [ ] **Step 7: Run test to verify it passes**

Run: `conda run -n sbs pytest tests/test_routes_plan.py -v`
Expected: PASS (all, incl. the 5 new). 现有 `test_autosave_persists_and_prefills_then_advances` 仍绿——`_live_html` 复刻原 est1RM HTML,响应仍含 `≈` 与 `(首次)`。

- [ ] **Step 8: Run full suite to confirm no regression**

Run: `conda run -n sbs pytest -q`
Expected: PASS (no failures).

- [ ] **Step 9: Commit**

```bash
git add webapp/routes/plan.py webapp/templates/plan.html tests/test_routes_plan.py
git commit -m "feat(plan): per-lift tonnage WoW inline + live update on save_log"
```

---

## Self-Review

**1. Spec coverage:**
- Q1 per lift-row → `lift_week_volume` keyed by `lift_id`, route 按 item id 循环 ✓
- Q2 green/red → `_tonnage_html` 用 `.up`/`.down`/`.first` ✓
- Q3 live update → T4 `save_log` 返回 `_live_html` + `_by_day` 初始预渲染(同一 helper,零重复)✓
- Q4 last-set = logged reps → 公式消费 `last_set`(来自 week_log/history),无 AMRAP 分类 ✓
- 公式 `weight×((sets-1)×planned+last)` → `_actual_tonnage` ✓
- t2 上周 target replay → `_t2_target_as_of` ✓
- 跳过未填 / 首次 → `lift_week_volume` None / `_tonnage_html` 首次 ✓
- 零引擎/repo/schema 改动 → 仅 volume.py(新)+ plan.py + plan.html ✓
- Risks(tier 切换/减载红/非末组近似)→ inherent,spec 记,无 task 需要 ✓

**2. Placeholder scan:** 无 TBD/TODO/占位行。所有 step 含完整代码。

**3. Type consistency:** `_actual_tonnage`/`_t2_target_as_of`/`lift_week_volume` 签名跨 T1-T3 一致;`_tonnage_html`/`_live_html` 在 T4 定义并同 task 内被 `_by_day` 与 `save_log` 消费,签名 `(conn, lid[, reps])` 一致;`item.live_html` 在 `_by_day` 设、plan.html 读,键名一致。

**Spec 偏差记录:** spec D9 原要求 `.up/.down/.first` 提到根级——因 grilling 决策 3 把片段放进 HTMX 目标区 `.save-ok` 内,现有 `.save-ok .up/.down/.first` 配色已覆盖,故 **不需要改 base.html**。D9 偏差记于此;若后续回写 spec,改 D9 为「无 CSS 改动」。
