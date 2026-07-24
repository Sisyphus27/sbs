# 离线手机端装片清单 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `week_export.html` 从桌面计划页的缩小版重构为装片清单 — 单大数字 + 动作指令，零 JS，进度驱动 day 定位。

**Architecture:** 纯模板重写 + 内联 CSS。数据仍由 `_by_day`（`webapp/routes/plan.py:49`）供给，无 Python/路由逻辑改动（除删一处 tonnage/live_html 依赖）。day 三态（全空/部分/全填）在 Jinja 内计算。

**Tech Stack:** Flask/Jinja2, 内联 CSS（复用 ADR 0006 tokens）, pytest。

**Spec:** `docs/superpowers/specs/2026-07-24-mobile-offline-ui-design.md`（ADR 0007）

## Global Constraints

- 输出必须**单文件自包含**：无外部 CSS/JS/字体/图片引用，无 server-relative URL。离线打开可用。
- **零 JavaScript** — 折叠用原生 `<details>/<summary>`。
- 重量**完整精度**（`95.0`/`57.5`），不去尾零 — `rounding=2.5` 格点须可见。数字用 mono。
- 浅色 only。复用 tokens：`--bg:#fff;--ink:#1a1a1a;--muted:#6b6b6b;--line:#e2e2e2;--accent:#1f4e79;--up:#2e7d32;--down:#c62828;--radius:3px`。
- mode tag 仅 `sbs` accent 高亮，其余 neutral（ADR 0006）。
- 一个动作**一个大数字**：barbell→`95.0 kg`；bodyweight→`+15 kg`（砍工作重量括号）；pure_bodyweight→无大数字。
- 卡片砍掉字段：est1RM、streak、logged 状态、live_html（含 `≈`/`首次`）、容量（tonnage）、工作重量括号。
- 保留 `viewport` meta、`lang="zh"`、`@media print` 规则。
- 每任务一提交。测试命令：`conda run -n sbs python -m pytest <path> -v`（Windows，conda env `sbs`）。

---

### Task 1: 删导出页容量依赖 + 改/删两个失效测试

新设计砍容量与 live_html。`_by_day` 仍算 `item.live_html`（桌面 plan.html 用），但导出模板不再渲染它。两个旧测试断言导出含容量/`≈`/`首次`/`未填` — 直接违背装片清单，须删。

**Files:**
- Modify: `tests/test_routes_plan.py:218-248`（删两个测试）
- 不改 `plan.py`（`_by_day`/`_live_html`/`_tonnage_html` 桌面仍用，保留）

**Interfaces:**
- Consumes: 现有 `_by_day` 返回 `by_day`（list of `(day, items)`）、`week`。
- Produces: 导出测试基线 — Task 2/3 在此文件加新断言。

- [ ] **Step 1: 确认两测试现状会随新模板失败（先记录，暂不跑新模板）**

两测试当前对**旧**模板通过。Task 3 换模板后它们必失败。本任务直接删，因为它们断言的正是被砍字段。

- [ ] **Step 2: 删 `test_export_week_shows_tonnage_when_logged` 与 `test_export_week_omits_tonnage_when_not_logged`**

从 `tests/test_routes_plan.py` 删除这两个函数（行 218-248，含 docstring）。

- [ ] **Step 3: 跑该文件确认删除后其余测试仍过**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -v`
Expected: 剩余测试全 PASS（删除的两个不再出现）。

- [ ] **Step 4: Commit**

```bash
git add tests/test_routes_plan.py
git commit -m "test: drop offline tonnage/live-preview assertions (plate-loading list drops state)"
```

---

### Task 2: 重写 week_export.html — 装片清单结构 + day 三态

重写模板。day 三态在 Jinja 算；卡片两层 + mode 注脚；`<details>` 折叠；默认展开最小非全填 day。

**Files:**
- Modify: `webapp/templates/week_export.html`（整体重写）
- Test: `tests/test_routes_plan.py`（Task 3 加断言）

**Interfaces:**
- Consumes: `week`（int）、`by_day`（list of `(day:int, items:list)`）。每个 `item` 有 `.name .mode .weight .working_weight .is_bodyweight .reps .sets .repout .target .logged`。**注意 `logged` 仍由 `_by_day` 提供**（`""` 或数字字符串），用于三态判定，但不渲染。
- Produces: 模板渲染契约 — 卡片结构、`<details data-day>`、day 状态 class（`st-full`/`st-part`/`st-empty`）、`open` 属性在最小非全填 day。

**关键 Jinja 逻辑（day 三态）：**

```
对每个 (day, items)：
  total  = items|length
  filled = items | selectattr('logged', 'ne', '') | selectattr('logged', 'ne', none) | list | length
  state  = 'full' if filled==total else ('part' if filled>0 else 'empty')
默认展开 = 序号最小的 state != 'full' 的 day；全 full → 最后一个 day。
```

- [ ] **Step 1: 写完整新模板**

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Week {{ week }} 计划</title>
  <style>
    :root{--bg:#fff;--ink:#1a1a1a;--muted:#6b6b6b;--line:#e2e2e2;
      --accent:#1f4e79;--up:#2e7d32;--down:#c62828;--warn:#b26a00;--radius:3px;
      --font:system-ui,-apple-system,"Segoe UI",sans-serif;
      --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace}
    *{box-sizing:border-box}
    body{font-family:var(--font);margin:12px auto;max-width:680px;padding:0 10px;
      color:var(--ink);background:var(--bg);line-height:1.5}
    h1{font-size:1.3em;margin:0 0 2px}
    .sub{color:var(--muted);font-size:.85em;margin:0 0 14px}
    details{border:1px solid var(--line);border-radius:var(--radius);margin:0 0 10px;overflow:hidden}
    summary{display:flex;align-items:center;gap:8px;padding:12px 14px;cursor:pointer;
      font-weight:600;font-size:1.05em;list-style:none;user-select:none}
    summary::-webkit-details-marker{display:none}
    summary .caret{color:var(--muted);font-size:.8em;transition:transform .15s}
    details[open] summary .caret{transform:rotate(90deg)}
    summary .mark{margin-left:auto;font-family:var(--mono);font-size:.95em}
    .st-full>summary .mark{color:var(--up)}
    .st-part>summary .mark{color:var(--warn)}
    .st-part>summary{background:#fdf6ec}
    .cards{padding:4px 14px 12px}
    .lift{padding:12px 0;border-bottom:1px solid var(--line)}
    .lift:last-child{border-bottom:none}
    .lift .top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
    .lift .name{font-weight:600;font-size:1.05em;word-break:break-word}
    .lift .wt{font-family:var(--mono);font-weight:bold;font-size:1.6em;white-space:nowrap}
    .lift .wt .unit{font-size:.5em;font-weight:normal;color:var(--muted);margin-left:2px}
    .lift .scheme{font-size:1.05em;margin-top:3px;font-family:var(--mono)}
    .lift .tag{display:inline-block;margin-top:5px;padding:1px 7px;border:1px solid var(--line);
      border-radius:10px;font-size:.78em;color:var(--muted);font-family:var(--mono)}
    .lift .tag.sbs{border-color:var(--accent);color:var(--accent)}
    @media print{body{max-width:none}details{border:none}.cards{padding:0}}
  </style>
</head>
<body>
<h1>Week {{ week }} 计划</h1>
<p class="sub">离线装片清单。练完回家在 app 填末组次数。</p>

{# 先算每个 day 的状态，找最小非全填 day #}
{% set ns = namespace(first_open=none) %}
{% for day, items in by_day %}
  {% set total = items|length %}
  {% set filled = items|selectattr('logged','ne','')|selectattr('logged','ne',none)|list|length %}
  {% set state = 'full' if filled==total else ('part' if filled>0 else 'empty') %}
  {% if ns.first_open is none and state != 'full' %}
    {% set ns.first_open = day %}
  {% endif %}
{% endfor %}
{% if ns.first_open is none and by_day %}
  {% set ns.first_open = by_day[-1][0] %}
{% endif %}

{% for day, items in by_day %}
  {% set total = items|length %}
  {% set filled = items|selectattr('logged','ne','')|selectattr('logged','ne',none)|list|length %}
  {% set state = 'full' if filled==total else ('part' if filled>0 else 'empty') %}
  <details data-day="{{ day }}" class="st-{{ state }}"{% if day==ns.first_open %} open{% endif %}>
    <summary>
      <span class="caret">▶</span>Day {{ day }}
      <span class="meta" style="font-weight:normal;color:var(--muted);font-size:.85em">{{ filled }}/{{ total }}</span>
      <span class="mark">{% if state=='full' %}✓{% elif state=='part' %}◐{% endif %}</span>
    </summary>
    <div class="cards">
      {% for it in items %}
      <div class="lift">
        <div class="top">
          <span class="name">{{ it.name }}</span>
          {% if it.is_bodyweight and it.mode != 'none' %}
            <span class="wt">+{{ it.weight }}<span class="unit">kg</span></span>
          {% elif it.mode == 'none' %}
            {# 纯体重：无大数字 #}
          {% else %}
            <span class="wt">{{ it.weight }}<span class="unit">kg</span></span>
          {% endif %}
        </div>
        <div class="scheme">
          {%- if it.mode=='sbs' -%}
            {{ it.reps }} × {{ it.sets }} · rep-out {{ it.repout }}
          {%- elif it.mode=='linear_t2' -%}
            {{ it.target }} × {{ it.sets }}
          {%- elif it.mode=='linear_t3' -%}
            {{ it.target }} × {{ it.sets }}
          {%- else -%}
            {% if it.reps is not none %}~{{ it.reps }} × {{ it.sets }}{% else %}{{ it.sets }} 组{% endif %}
          {%- endif -%}
        </div>
        <span class="tag {{ 'sbs' if it.mode=='sbs' }}">{{ it.mode }}</span>
      </div>
      {% endfor %}
    </div>
  </details>
{% endfor %}
</body>
</html>
```

**说明（实现者须守）：**
- bodyweight（`is_bodyweight` 且 `mode != 'none'`）→ `+{weight} kg`。不显示 `working_weight`。
- pure_bodyweight（`mode == 'none'`）→ 无大数字，方案行用上次次数 `~reps × sets`（`reps` 为 None 时 `{sets} 组`）。
- t2/t3 方案行同形 `{target} × {sets}`，砍 streak。
- `{{ filled }}/{{ total }}` 给进度计数。

- [ ] **Step 2: 手动渲染验证（起 app 或用测试 client）**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -x -q -k "not tonnage"`
Expected: 无模板语法错（500）。模板错会致 export 路由渲染失败。

- [ ] **Step 3: Commit**

```bash
git add webapp/templates/week_export.html
git commit -m "feat(ui): rebuild offline week export as plate-loading list (zero JS, day tri-state)"
```

---

### Task 3: 加新结构路由测试

为 Task 2 的新结构加回归测试。断言装片清单契约。

**Files:**
- Modify: `tests/test_routes_plan.py`（文件尾追加）

**Interfaces:**
- Consumes: Task 2 模板契约 — `<details data-day>`、`st-part`/`st-full`、卡片 `.wt`、mode tag、无容量/`≈`/`首次`。
- Produces: 无（终态测试）。

- [ ] **Step 1: 写失败测试（新模板应通过；先确认断言贴合模板）**

追加到 `tests/test_routes_plan.py`：

```python
def test_export_week_plate_loading_structure(client, app):
    """装片清单：barbell 显示大数字 kg、sbs 方案行含 rep-out、mode tag，无容量/est1RM 状态。"""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                         day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                         reps=None, repout=None, start=None, lift_kind="main")
        conn.close()
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1"' in html
    assert 'class="wt"' in html and "kg" in html      # 大数字 + 单位
    assert "rep-out" in html                            # sbs 方案行
    assert 'class="tag sbs"' in html                    # mode tag accent
    assert "容量" not in html and "≈" not in html       # 状态字段已砍
    assert "est 1RM" not in html and "streak" not in html


def test_export_week_bodyweight_shows_added_only(client, app):
    """bodyweight 动作只显示 +added kg，不显示工作重量括号。"""
    with app.app_context():
        from webapp.db import connect
        from webapp import repo as _repo
        conn = connect(app.config["DB_PATH"])
        _repo.update_settings(conn, bodyweight=75.0)
        repo.create_lift(conn, name="Chin-up", load_model="bodyweight", mode="linear_t2",
                         day=1, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=15.0, bodyweight_pct=1.0)
        conn.close()
    html = client.get("/export/week.html").get_data(as_text=True)
    assert "+15" in html          # 加重
    assert "(90" not in html      # 工作重量括号已砍 (15 + 75*1.0 = 90)


def test_export_week_day_tristate_and_default_open(client, app):
    """day 三态：全空 day1 + 部分填 day2 → day2 标 ◐ 且默认展开（最小非全填是 day1，但 day1 全空也非全填）。

    构造：day1 一个动作不填（全空）；day2 两动作填一个（部分填）。最小非全填 = day1 → day1 open。
    day2 st-part 带 ◐。"""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="A", load_model="barbell", mode="linear_t3",
                         day=1, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=30.0)
        lid_b1 = repo.create_lift(conn, name="B1", load_model="barbell", mode="linear_t3",
                         day=2, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=30.0)
        repo.create_lift(conn, name="B2", load_model="barbell", mode="linear_t3",
                         day=2, sort_order=1, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=30.0)
        repo.save_log(conn, lid_b1, 1, 12)   # day2 填一个 → 部分填
        conn.close()
    html = client.get("/export/week.html").get_data(as_text=True)
    assert '<details data-day="1" class="st-empty" open>' in html   # 最小非全填默认展开
    assert '<details data-day="2" class="st-part">' in html         # 部分填折叠
    assert "◐" in html                                               # 欠账标记
```

- [ ] **Step 2: 跑新测试确认通过**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -v -k export_week`
Expected: 3 个新测试 PASS。

- [ ] **Step 3: 跑全测试文件确认无回归**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py -v`
Expected: 全 PASS。

- [ ] **Step 4: Commit**

```bash
git add tests/test_routes_plan.py
git commit -m "test: plate-loading offline export — structure, bodyweight added-only, day tri-state"
```

---

### Task 4: 全测试套件 + 手动导出验证

**Files:**
- 无新增。验证用。

- [ ] **Step 1: 跑全测试套件**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS（无其它文件依赖被砍的导出断言）。

- [ ] **Step 2: 手动导出开窄窗/手机验证**

起 app（`conda run -n sbs python -m webapp` 或项目 `run_sbs.bat`），桌面 `/` 点"导出本周计划"，下载 `week-N.html`。
- 窄窗（<680px）或手机打开：验证大数字可读、卡片层级、`<details>` 折叠/展开、◐/✓ 标记、默认展开正确 day。
- 打印预览（`@media print`）不破版。

- [ ] **Step 3: Commit（如需微调 CSS）**

```bash
git add webapp/templates/week_export.html
git commit -m "fix(ui): offline export polish from device check"
```
（无改动则跳过）

---

## Self-Review 记录

**Spec 覆盖：**
- 单大数字（barbell/bodyweight/纯体重三分支）→ Task 2 ✓
- 动作指令方案行（sbs rep-out / t2 / t3 / none ~上次）→ Task 2 ✓
- mode tag 注脚（sbs accent）→ Task 2 ✓
- day 三态 + ◐/✓ + 默认展开最小非全填 → Task 2 + Task 3 ✓
- 零 JS / 单文件自包含 / 浅色 / tokens → Task 2 ✓
- 砍 est1RM/streak/logged/live_html/容量/工作重量括号 → Task 1 + Task 2 ✓
- 删失效容量测试 → Task 1 ✓
- 手动设备验证 → Task 4 ✓

**Placeholder 扫描：** 无 TBD/TODO。模板完整给出，测试代码完整。

**Type 一致性：** `item.weight/reps/sets/repout/target/logged/is_bodyweight/mode` 与 `_by_day`（`plan.py:71-104`）字段一致。`logged` 为 `""` 或数字串，三态判定用 `ne ''` + `ne none` 兼容。
