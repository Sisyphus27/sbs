# webapp UI 重做 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重做 webapp 呈现层 — 极简工具风 + 左侧 sidebar + 动作页展开行编辑， 不动后端业务逻辑。

**Architecture:** 抽全部样式到 `webapp/static/app.css` (CSS 变量 token + 组件类); `base.html` 改左侧 sidebar 布局 (3 组导航 + blueprint 高亮 + flash 分级); 动作管理页改只读行 + HTMX 展开编辑; 其余页套统一组件。后端仅加 2 个只读 GET partial 端点 + 1 个 context processor + flash 错误类别。

**Tech Stack:** Flask (Jinja), HTMX, SQLite, pytest。零前端构建。

## Global Constraints

- **只动呈现层** — `routes/*.py` 只加 `GET /lifts/<id>/row`、`GET /lifts/<id>/edit`、context processor、flash 类别参数； `repo.py`/`services/`/`sbs_cli/` 一律不改 (ADR 0006)。
- 模板变量名保持现状 — 现有 `tests/test_routes_*.py` 必须持续全绿。
- 视觉 token 精确值： `--accent:#1f4e79`, `--up:#2e7d32`, `--down:#c62828`, `--ink:#1a1a1a`, `--muted:#6b6b6b`, `--line:#e2e2e2`, `--bg:#ffffff`, `--danger:#c62828`, `--radius:3px`。
- 字体： 正文 `system-ui,-apple-system,"Segoe UI",sans-serif` 15px/1.5; 数字 `ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace`。
- Accent 专属： 主按钮 / sidebar 当前页 / 链接 / input focus。不用于危险按钮 (红)、涨跌 (绿/红)、徽章。
- mode 徽章只 sbs 用 accent 描边； 其余中性。load_model 纯灰注记。无彩虹色。
- 确认原则： 不可逆+一键 (lift 删除、schedule 重置) 加 confirm; 需输入/可再来 (reseed) 不加。
- 中文主标签 + 英文参数名小字副注。
- sidebar 3 组： 训练 (本周计划/进度表) / 动作 (动作/重测) / 配置 (全局参数)。高亮用 `request.blueprint`。
- 合法组合表后端注入 JSON (同源 `is_legal_combo`), 前端不硬编码副本。
- 运行命令全用 `conda run -n sbs` (见 memory: conda env sbs)。
- YAGNI: 无前端框架/构建、无深色模式、无汉堡/手势、无 modal、无 spinner、无 schedule 批量编辑、不自托管字体。

---

### Task 1: 设计系统 `app.css`

**Files:**
- Create: `webapp/static/app.css`

**Interfaces:**
- Consumes: 无 (纯 CSS 起点)。
- Produces: CSS 变量 token + 组件类 `.btn` `.btn-primary` `.btn-danger` `.btn-ghost` `.card` `.field` `.tag` `.tag-accent` `.tag-muted` `.table` `.flash` `.flash-error` `.sidebar` `.active` `.num` `.meta` `.row-actions`。后续所有任务依赖这些类名。

无 pytest (纯 CSS)。验证 = 文件存在 + 后续任务渲染引用。

- [ ] **Step 1: 写 app.css**

```css
/* SBS webapp design system — 极简工具风 (ADR 0006). Single accent, monochrome base. */
:root{
  --bg:#ffffff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2e2e2;
  --accent:#1f4e79;
  --up:#2e7d32; --down:#c62828; --danger:#c62828;
  --space:8px; --radius:3px;
  --font:system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;font-family:var(--font);font-size:15px;line-height:1.5;color:var(--ink);background:var(--bg)}
h1{font-size:1.4em;margin:0 0 .5em}
h2{font-size:1.2em;margin:1.4em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:1.05em;margin:1em 0 .4em}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* numbers in columns align monospace; prose numbers stay sans */
.num,input[type=number]{font-family:var(--mono)}
.meta{color:var(--muted);font-size:.92em}

/* buttons */
.btn,button{display:inline-block;font:inherit;padding:6px 14px;border:1px solid var(--line);
  border-radius:var(--radius);background:#fff;color:var(--ink);cursor:pointer;margin:0}
.btn:hover,button:hover{border-color:var(--muted)}
.btn-primary,button.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-danger,button.btn-danger{background:#fff;border-color:var(--danger);color:var(--danger)}
.btn-ghost,button.btn-ghost{border:none;background:none;color:var(--muted);padding:6px 8px}
.btn-ghost:hover{color:var(--ink)}
button:focus-visible,.btn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

/* card + field grid */
.card{border:1px solid var(--line);border-radius:var(--radius);padding:16px;margin:0 0 16px;background:#fff}
.field{display:flex;flex-direction:column;gap:2px;margin-bottom:10px}
.field label{font-size:.85em;color:var(--muted)}
.field .sub{font-size:.78em;color:var(--muted)}
.field input,.field select{padding:5px 8px;border:1px solid var(--line);border-radius:var(--radius);font:inherit;width:100%;max-width:220px}
.field input:focus,.field select:focus{outline:none;border-color:var(--accent)}
.field-row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}

/* tags */
.tag{display:inline-block;padding:1px 7px;border:1px solid var(--line);border-radius:10px;
  font-size:.8em;color:var(--muted);font-family:var(--mono)}
.tag-accent{border-color:var(--accent);color:var(--accent)}
.tag-muted{border:none;background:#f2f2f2;color:var(--muted)}

/* table */
.table{border-collapse:collapse;width:100%}
.table th,.table td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left}
.table th{font-size:.85em;color:var(--muted);font-weight:normal}
.table input{width:72px}

/* flash */
.flash{border:1px solid var(--line);border-left:3px solid var(--muted);border-radius:var(--radius);
  padding:8px 12px;margin:0 0 12px;color:var(--ink)}
.flash-error{border-left-color:var(--danger);color:var(--danger)}

/* layout */
body{display:flex;min-height:100vh}
.sidebar{width:180px;flex:0 0 180px;border-right:1px solid var(--line);padding:20px 14px;position:sticky;top:0;height:100vh}
.sidebar .brand{font-weight:bold;font-size:1.1em;margin-bottom:18px}
.sidebar .group{margin-bottom:16px}
.sidebar .group-name{font-size:.78em;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}
.sidebar a{display:block;padding:4px 8px;border-radius:var(--radius);color:var(--ink)}
.sidebar a.active{background:#eef3f8;color:var(--accent);font-weight:600}
.sidebar a .badge{float:right;background:var(--accent);color:#fff;border-radius:9px;font-size:.75em;padding:0 6px}
.main{flex:1;min-width:0;padding:24px 32px}
.content{max-width:1100px}

@media (max-width:900px){
  body{flex-direction:column}
  .sidebar{width:100%;flex:none;height:auto;border-right:none;border-bottom:1px solid var(--line);
    position:static;display:flex;flex-wrap:wrap;gap:4px;align-items:center}
  .sidebar .brand{margin:0 12px 0 0}
  .sidebar .group{margin:0;display:flex;gap:2px;align-items:center}
  .sidebar .group-name{display:none}
  .main{padding:16px}
}
```

- [ ] **Step 2: Commit**

```bash
git add webapp/static/app.css
git commit -m "feat(ui): add app.css design-token stylesheet"
```

---

### Task 2: `base.html` sidebar 骨架 + flash 分级

**Files:**
- Modify: `webapp/templates/base.html`
- Modify: `webapp/routes/settings.py:30,33` (flash 加 `"error"` 类别 — 仅校验失败处)

**Interfaces:**
- Consumes: Task 1 的 `.sidebar` `.active` `.flash` `.flash-error` `.badge` `.main` `.content`。
- Produces: 全局布局 — `{% block title %}`, `{% block content %}`, sidebar 用 `request.blueprint` 判 active; `get_flashed_messages(with_categories=true)`。所有页面模板继承此骨架。flash 类别约定： 成功=无类别 (灰), 错误=`"error"` (红)。

- [ ] **Step 1: 改 settings.py flash 类别**

校验失败处加 `"error"`。`update()` 第 29 行:

```python
                flash(f"非法值: {col}", "error")
                return redirect(url_for("settings.view"))
```

`update()` 第 32 行成功保持无类别:

```python
    repo.update_settings(conn, **fields)
    flash("参数已更新")
    return redirect(url_for("settings.view"))
```

- [ ] **Step 2: 改 lifts.py flash 类别**

`webapp/routes/lifts.py` 所有校验失败 flash 加 `"error"`。逐处改 (行 50,52,56,61,80 的 `new()`; 行 104,110 的 `edit()`; 行 142,155,164 的 mode 相关)。模式: `flash("...", "error")`。成功 flash (无) 不动。例:

```python
        flash("load_model 非法", "error")
```

`mode_preview`/`mode_apply` 中 `flash(str(e))` → `flash(str(e), "error")`; `flash("重量 / TM 必须是数字")` → `flash("重量 / TM 必须是数字", "error")`。

- [ ] **Step 3: 改 plan.py + reseed.py + schedule.py flash 类别**

`plan.py` `save_log`/`submit` 校验失败: `flash(f"非法输入: {key} = {val}", "error")`, `flash(f"次数不能为负: {key}", "error")`。成功 `flash(f"已推进到 week {new_week}")` 不动。
`reseed.py`: `flash("max 必须是数字", "error")`; 成功不动。
`schedule.py` `save()`: `flash(f"非法值: {kind} week {week}", "error")`, `flash(f"范围错误: ...", "error")`; 成功不动。

- [ ] **Step 4: 重写 base.html**

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}SBS{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
  <script src="{{ url_for('static', filename='htmx.min.js') }}"></script>
</head>
<body>
  <nav class="sidebar">
    <div class="brand">SBS</div>
    <div class="group">
      <div class="group-name">训练</div>
      <a href="{{ url_for('plan.view') }}" class="{{ 'active' if request.blueprint=='plan' }}">本周计划</a>
      <a href="{{ url_for('schedule.view') }}" class="{{ 'active' if request.blueprint=='schedule' }}">进度表</a>
    </div>
    <div class="group">
      <div class="group-name">动作</div>
      <a href="{{ url_for('lifts.view') }}" class="{{ 'active' if request.blueprint=='lifts' }}">动作</a>
      <a href="{{ url_for('reseed.view') }}" class="{{ 'active' if request.blueprint=='reseed' }}">重测
        {%- if reseed_count %}<span class="badge">{{ reseed_count }}</span>{% endif -%}
      </a>
    </div>
    <div class="group">
      <div class="group-name">配置</div>
      <a href="{{ url_for('settings.view') }}" class="{{ 'active' if request.blueprint=='settings' }}">全局参数</a>
    </div>
  </nav>
  <div class="main">
    <div class="content">
      {% with msgs = get_flashed_messages(with_categories=true) %}
        {% for cat, m in msgs %}<div class="flash{{ ' flash-error' if cat=='error' }}">{{ m }}</div>{% endfor %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
  </div>
</body>
</html>
```

注： `reseed_count` 由 Task 3 context processor 注入； 此刻未定义时 Jinja `if reseed_count` 为 falsy (undefined→false), 不报错。

- [ ] **Step 5: 跑全测试验证无回归**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS (模板变量名未变; base.html 改动不影响断言的 `b"Squat"` 等内容字节)。

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/base.html webapp/routes/settings.py webapp/routes/lifts.py webapp/routes/plan.py webapp/routes/reseed.py webapp/routes/schedule.py
git commit -m "feat(ui): sidebar layout in base.html + flash error categories"
```

---

### Task 3: context processor 注入 reseed_count + legal_map

**Files:**
- Modify: `webapp/app.py`
- Test: `tests/test_context.py` (create)

**Interfaces:**
- Consumes: `_due_lifts` from `webapp/routes/reseed.py:10`; `LEGAL_COMBOS`,`LOAD_MODELS`,`MODES` from `sbs_cli/data/schema.py:10-19`。
- Produces: 模板全局 `reseed_count: int` (base.html sidebar 徽章用); 模板全局 `legal_map: dict[str, list[str]]` (lifts.html 级联用, `{load_model: [mode,...]}`)。

- [ ] **Step 1: 写失败测试**

Create `tests/test_context.py`:

```python
def test_reseed_count_in_template_context(client, app):
    rv = client.get("/")
    assert rv.status_code == 200
    # context processor always provides reseed_count (0 when none due)


def test_legal_map_injected_on_lifts_page(client, app):
    rv = client.get("/lifts")
    assert rv.status_code == 200
    # legal_map serialized into page for the cascade (barbell maps to its 3 modes)
    assert b"barbell" in rv.data
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_context.py -v`
Expected: FAIL — `/` 可能 200 但此测试文件导入尚依赖未写的 processor; 实际首个失败在 legal_map 未注入时 `b"barbell"` 缺失 (lifts.html 尚未渲染它)。若 `/` 报错则因 processor 缺失 — 正常 RED。

- [ ] **Step 3: 改 app.py 加 context processor**

`create_app` 内, blueprint 注册后 (`app.teardown_appcontext(close_db)` 前) 加:

```python
    from .routes.reseed import _due_lifts
    from sbs_cli.data.schema import LEGAL_COMBOS, LOAD_MODELS, MODES

    @app.context_processor
    def inject_globals():
        from .db import get_db
        conn = get_db()
        try:
            due, _ = _due_lifts(conn)
            reseed_count = len(due)
        except Exception:
            reseed_count = 0
        legal_map = {lm: [m for m in MODES if (lm, m) in LEGAL_COMBOS]
                     for lm in LOAD_MODELS}
        return {"reseed_count": reseed_count, "legal_map": legal_map}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `conda run -n sbs python -m pytest tests/test_context.py tests/test_routes_plan.py -v`
Expected: PASS。注意 legal_map 注入 context 但模板未渲染 → `test_legal_map...` 的 `b"barbell"` 可能仍 FAIL。若是, 把该断言移至 Task 6 (lifts.html 渲染后) 再验, 本任务仅保留 `test_reseed_count`。

调整 `test_context.py` 为:

```python
def test_reseed_count_in_template_context(client, app):
    rv = client.get("/")
    assert rv.status_code == 200
```

- [ ] **Step 5: 全测试**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add webapp/app.py tests/test_context.py
git commit -m "feat(ui): context processor injects reseed_count + legal_map"
```

---

### Task 4: lifts 只读行 partial `_lift_row.html` + `GET /lifts/<id>/row`

**Files:**
- Modify: `webapp/templates/_lift_row.html` (重写为只读行)
- Modify: `webapp/routes/lifts.py` (加 `row()` 端点)
- Test: `tests/test_routes_lifts.py`

**Interfaces:**
- Consumes: Task 1 `.tag` `.tag-accent` `.tag-muted` `.meta` `.num`; repo `get_lift`。
- Produces: `_lift_row.html` 渲染只读卡片行 (id=`lift-{{lift.id}}`, 含"编辑"按钮 hx-get edit); `GET /lifts/<id>/row` 返回该 partial。Task 5 的 edit partial 与之配对。

- [ ] **Step 1: 写失败测试**

`tests/test_routes_lifts.py` 尾部加:

```python
def test_row_partial_renders_readonly(client, app):
    lid = _lift(app)
    rv = client.get(f"/lifts/{lid}/row")
    assert rv.status_code == 200
    assert b"Squat" in rv.data
    # read-only row has no editable form inputs
    assert b'hx-post' not in rv.data or b'name=' not in rv.data
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py::test_row_partial_renders_readonly -v`
Expected: FAIL — 404 (端点不存在)。

- [ ] **Step 3: 重写 _lift_row.html 为只读行**

```html
{% if lift %}
<div class="card" id="lift-{{ lift.id }}">
  <div class="field-row" style="justify-content:space-between">
    <div>
      <strong>{{ lift.name }}</strong>
      <span class="tag {{ 'tag-accent' if lift.mode=='sbs' }}">{{ lift.mode }}</span>
      <span class="tag-muted tag">{{ lift.load_model }}</span>
      <span class="meta num">day {{ lift.day }} · {{ lift.sets }} 组
        {%- if lift.mode=='sbs' %} · max {{ lift.max }}{% if lift.lift_kind %} · {{ lift.lift_kind }}{% endif %}
        {%- elif lift.mode in ('linear_t2','linear_t3') %} · start {{ lift.start }} · incr {{ lift.incr if lift.incr is not none else '全局' }}
        {%- endif -%}
      </span>
    </div>
    <div class="row-actions">
      <button class="btn-ghost" hx-get="{{ url_for('lifts.row_edit', lid=lift.id) }}"
              hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML">编辑</button>
    </div>
  </div>
</div>
{% endif %}
```

- [ ] **Step 4: 加 row() 端点到 lifts.py**

`webapp/routes/lifts.py` `view()` 后加:

```python
@bp.route("/lifts/<int:lid>/row")
def row(lid):
    conn = get_db()
    return render_template("_lift_row.html", lift=repo.get_lift(conn, lid))
```

- [ ] **Step 5: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -v`
Expected: 新测试 PASS。注意 `test_lifts_view_lists_lift` 等旧测试仍 PASS (lifts.html 尚未改, 仍 include 旧 _lift_row — 但旧 _lift_row 已重写!)。**风险**: 重写 _lift_row 后旧 `lifts.html` include 它会渲染新只读行 — 列表仍显 Squat, 旧测试 PASS 即可。若 `test_create_lift_via_post` 断言行内容, 检查。

Run 全套: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS 或仅 lifts.html 相关待 Task 6 修。

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/_lift_row.html webapp/routes/lifts.py tests/test_routes_lifts.py
git commit -m "feat(ui): read-only lift row partial + GET /lifts/<id>/row"
```

---

### Task 5: 展开编辑 partial `_lift_edit.html` + `GET /lifts/<id>/edit` + 校验失败回显

**Files:**
- Create: `webapp/templates/_lift_edit.html`
- Modify: `webapp/routes/lifts.py` (加 `row_edit()` GET; 改 `edit()` POST 失败分支渲染 `_lift_edit.html`)
- Test: `tests/test_routes_lifts.py`

**Interfaces:**
- Consumes: Task 1 `.field` `.field-row` `.btn-primary` `.btn-danger` `.btn-ghost`; Task 4 的 `row()`; 现有 `edit()` POST。
- Produces: `GET /lifts/<id>/edit` (端点名 `lifts.row_edit`) 返回 `_lift_edit.html`; `edit()` POST 校验失败返回 `_lift_edit.html` 带回显错误值 + 400 (不再返回只读行丢输入, grill Q3)。

- [ ] **Step 1: 写失败测试**

`tests/test_routes_lifts.py` 尾部加:

```python
def test_edit_partial_renders_form(client, app):
    lid = _lift(app)
    rv = client.get(f"/lifts/{lid}/edit")
    assert rv.status_code == 200
    assert b'name="name"' in rv.data  # edit form has inputs


def test_edit_failure_keeps_edit_state(client, app):
    lid = _t2_lift_with_incr(app, incr=5.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": "-1"})
    assert rv.status_code == 400
    # edit state preserved: form re-rendered, not the read-only row
    assert b'name="incr"' in rv.data
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py::test_edit_partial_renders_form tests/test_routes_lifts.py::test_edit_failure_keeps_edit_state -v`
Expected: FAIL — 404 (`/edit` GET 不存在); `test_edit_failure` 当前返回只读 `_lift_row.html` (无 `name="incr"` input) → FAIL。

- [ ] **Step 3: 建 _lift_edit.html**

字段按 mode 条件渲染 (沿用现 `_lift_row.html` 编辑逻辑), 套 `.field` 网格, 支持 `error` 回显:

```html
{% if lift %}
<div class="card" id="lift-{{ lift.id }}">
  {% if error %}<div class="flash flash-error">{{ error }}</div>{% endif %}
  <form hx-post="{{ url_for('lifts.edit', lid=lift.id) }}" hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML">
    <div class="field-row">
      <div class="field"><label>动作名</label>
        <input name="name" value="{{ lift.name }}"></div>
      <div class="field"><label>Day</label>
        <input name="day" type="number" value="{{ lift.day }}"></div>
      <div class="field"><label>组数</label>
        <input name="sets" type="number" value="{{ lift.sets }}"></div>
      <div class="field"><label>载荷模型 <span class="sub">(不可改)</span></label>
        <input name="load_model" value="{{ lift.load_model }}" readonly style="color:var(--muted)"></div>
      <div class="field"><label>Mode</label>
        <select name="mode">
          {% for m in legal_map.get(lift.load_model, []) %}
          <option value="{{ m }}" {{ 'selected' if lift.mode == m }}>{{ m }}</option>
          {% endfor %}
        </select></div>
    </div>
    <div class="field-row">
      {% if lift.mode == 'sbs' %}
      <div class="field"><label>类型</label>
        <select name="lift_kind">
          <option value="main" {{ 'selected' if lift.lift_kind == 'main' }}>main</option>
          <option value="aux" {{ 'selected' if lift.lift_kind == 'aux' }}>aux</option>
        </select></div>
      <div class="field"><label>Max</label>
        <input name="max" type="number" step="0.5" value="{{ lift.max or '' }}"></div>
      {% elif lift.mode in ('linear_t2','linear_t3') %}
      <div class="field"><label>强度</label>
        <input name="intensity" type="number" step="0.05" value="{{ lift.intensity or '' }}"></div>
      <div class="field"><label>次数</label>
        <input name="reps" type="number" value="{{ lift.reps or '' }}"></div>
      <div class="field"><label>Repout</label>
        <input name="repout" type="number" value="{{ lift.repout or '' }}"></div>
      <div class="field"><label>步进 <span class="sub">(空=全局)</span></label>
        <input name="incr" type="number" step="0.5" value="{{ lift.incr if lift.incr is not none else '' }}"></div>
      {% endif %}
      <div class="field"><label>Start</label>
        <input name="start" type="number" step="0.5" value="{{ lift.start or '' }}"></div>
      {% if lift.load_model in ('bodyweight','pure_bodyweight') %}
      <div class="field"><label>体重比例</label>
        <input name="bodyweight_pct" type="number" step="0.01" min="0" max="1"
               value="{{ lift.bodyweight_pct if lift.bodyweight_pct else '' }}"></div>
      {% endif %}
    </div>
    <div class="field-row" style="margin-top:12px">
      <button type="submit" class="btn-primary">保存</button>
      <button type="button" class="btn-ghost" hx-get="{{ url_for('lifts.row', lid=lift.id) }}"
              hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML">取消</button>
      <a class="btn" href="{{ url_for('lifts.mode_preview', lid=lift.id) }}">换 mode</a>
      <button type="button" class="btn-danger" style="margin-left:auto"
              hx-post="{{ url_for('lifts.delete', lid=lift.id) }}"
              hx-target="#lift-{{ lift.id }}" hx-swap="outerHTML"
              hx-confirm="删除 {{ lift.name }}?">删除</button>
    </div>
  </form>
</div>
{% endif %}
```

- [ ] **Step 4: 加 row_edit() GET + 改 edit() POST 失败分支**

`webapp/routes/lifts.py` `row()` 后加:

```python
@bp.route("/lifts/<int:lid>/edit")
def row_edit(lid):
    conn = get_db()
    return render_template("_lift_edit.html", lift=repo.get_lift(conn, lid))
```

`edit()` 失败分支 — 现 3 处 `render_template("_lift_row.html", lift=..., error=...)` 改为 `_lift_edit.html`:

- bad combo (行 ~104): `return render_template("_lift_edit.html", lift=cur, error="load_model 与 mode 组合非法"), 400`
- bad incr (行 ~111): `return render_template("_lift_edit.html", lift=repo.get_lift(conn, lid), error=err), 400`

`edit()` 成功仍返回 `_lift_row.html` (只读行)。

- [ ] **Step 5: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -v`
Expected: 全新旧 PASS (旧 `test_edit_rejects_*` 仍验 400 + 原值保留; 新验 edit 态保留)。

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/_lift_edit.html webapp/routes/lifts.py tests/test_routes_lifts.py
git commit -m "feat(ui): expandable lift edit partial; keep edit state on validation failure"
```

---

### Task 6: lifts.html 主模板 + 级联 app.js

**Files:**
- Modify: `webapp/templates/lifts.html`
- Create: `webapp/static/app.js`
- Test: `tests/test_routes_lifts.py` ( legal_map 渲染断言, 从 Task 3 移来)

**Interfaces:**
- Consumes: Task 3 `legal_map`; Task 4 `_lift_row.html`; Task 5 `_lift_edit.html`; Task 1 `.card` `.field`。
- Produces: lifts 页 — 新增动作 `.card` 表单 (级联) + 只读行列表 (`#lift-list`)。`app.js` 读 `legal_map` JSON 做 load_model→mode 级联。

- [ ] **Step 1: 写失败测试**

`tests/test_routes_lifts.py` 尾部加:

```python
def test_lifts_page_includes_legal_map_json(client, app):
    rv = client.get("/lifts")
    assert rv.status_code == 200
    # legal_map injected as JSON for the cascade (barbell -> its legal modes)
    assert b"legal-map" in rv.data or b"linear_t2" in rv.data
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py::test_lifts_page_includes_legal_map_json -v`
Expected: FAIL — 页面尚无 `legal-map` 元素/JSON。

- [ ] **Step 3: 重写 lifts.html**

```html
{% extends "base.html" %}
{% block title %}动作管理{% endblock %}
{% block content %}
<h1>动作管理</h1>

<div class="card">
  <h2 style="margin-top:0">新增动作</h2>
  <form hx-post="{{ url_for('lifts.new') }}" hx-target="#lift-list" hx-swap="beforeend">
    <div class="field-row">
      <div class="field"><label>动作名</label><input name="name" placeholder="动作名"></div>
      <div class="field"><label>载荷模型</label>
        <select name="load_model" id="new-load-model">
          <option value="barbell">barbell</option>
          <option value="bodyweight">bodyweight</option>
          <option value="pure_bodyweight">pure_bodyweight</option>
        </select></div>
      <div class="field"><label>Mode</label>
        <select name="mode" id="new-mode"></select></div>
      <div class="field"><label>类型</label>
        <select name="lift_kind"><option value="main">main</option><option value="aux">aux</option></select></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Day</label><input name="day" type="number" value="1"></div>
      <div class="field"><label>组数</label><input name="sets" type="number" value="3"></div>
      <div class="field"><label>Max <span class="sub">(sbs)</span></label>
        <input name="max" type="number" step="0.5" placeholder="max"></div>
      <div class="field"><label>Start <span class="sub">(t2/t3)</span></label>
        <input name="start" type="number" step="0.5" placeholder="start"></div>
      <div class="field"><label>步进 <span class="sub">(t2/t3, 空=全局)</span></label>
        <input name="incr" type="number" step="0.5" placeholder="incr"></div>
      <div class="field"><label>体重比例 <span class="sub">(负重)</span></label>
        <input name="bodyweight_pct" type="number" step="0.01" min="0" max="1" placeholder="bw%"></div>
    </div>
    <button type="submit" class="btn-primary" style="margin-top:8px">添加</button>
  </form>
</div>

<script id="legal-map" type="application/json">{{ legal_map | tojson }}</script>
<script src="{{ url_for('static', filename='app.js') }}"></script>

<h2>现有动作</h2>
<div id="lift-list">
  {% for lift in lifts %}
    {% include "_lift_row.html" %}
  {% else %}
    <p class="meta">暂无动作， 上方新增。</p>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 4: 建 app.js (级联)**

读 `#legal-map` JSON, load_model change 时重建 mode options:

```javascript
(function () {
  var el = document.getElementById('legal-map');
  var lm = document.getElementById('new-load-model');
  var mode = document.getElementById('new-mode');
  if (!el || !lm || !mode) return;
  var LEGAL = JSON.parse(el.textContent);
  function sync() {
    var allowed = LEGAL[lm.value] || [];
    mode.innerHTML = '';
    allowed.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m; o.textContent = m;
      mode.appendChild(o);
    });
  }
  lm.addEventListener('change', sync);
  sync();
})();
```

- [ ] **Step 5: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py tests/test_context.py -v`
Expected: 全 PASS (页面含 `legal-map` script 标签)。

- [ ] **Step 6: 全测试**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add webapp/templates/lifts.html webapp/static/app.js tests/test_routes_lifts.py
git commit -m "feat(ui): lifts page read-only list + cascade app.js from legal_map"
```

---

### Task 7: settings.html 分组卡片 + 独立 ↺ form + 中文标签

**Files:**
- Modify: `webapp/templates/settings.html`
- Test: `tests/test_routes_settings.py`

**Interfaces:**
- Consumes: Task 1 `.card` `.field` `.btn-ghost` `.btn-primary`; `url_for('settings.reset_field')`; `RESETTABLE_FIELDS`。
- Produces: settings 页 — 基础卡片 + 进阶卡片; ↺为每字段独立小 form; 中文主标签+英文副注。

**测试约束 (来自现有 test_routes_settings.py):** 页面必须含文本 `最小变动` 和 `全局参数` (test_settings_view 断言)。↺独立 form 的 `formaction`/`action` 仍指向 `/settings/<field>/reset` (现有 reset 测试不变)。

- [ ] **Step 1: 重写 settings.html**

↺ 独立 form 用 HTML `formaction` 会带主表单字段 — grill Q7 要求隔离。改每可重置字段用**独立小 form** (form 不可嵌套, 故可重置字段自成一行 form, 非可重置字段在主 form):

```html
{% extends "base.html" %}
{% block title %}全局参数{% endblock %}
{% block content %}
<h1>全局参数</h1>

<div class="card">
  <h2 style="margin-top:0">基础</h2>
  <form method="post" action="{{ url_for('settings.update') }}">
    <div class="field-row">
      <div class="field"><label>取整粒度 (kg) <span class="sub">rounding</span></label>
        <input type="number" step="0.5" name="rounding" value="{{ s.rounding }}"></div>
      <div class="field"><label>默认步进 (kg) <span class="sub">incr</span></label>
        <input type="number" step="{{ s.rounding }}" name="incr" value="{{ s.incr }}"></div>
      <div class="field"><label>体重 (kg) <span class="sub">bodyweight</span></label>
        <input type="number" step="0.1" name="bodyweight" value="{{ s.bodyweight }}"></div>
    </div>
    <button type="submit" class="btn-primary">保存</button>
  </form>
  {# 可重置的基础字段 days_per_week: 独立 form 使 ↺ 不牵连主表单 #}
  <form method="post" action="{{ url_for('settings.update') }}" class="field-row" style="margin-top:12px;align-items:flex-end">
    <div class="field"><label>每周天数 <span class="sub">days_per_week</span></label>
      <input type="number" name="days_per_week" value="{{ s.days_per_week }}"></div>
    <button type="submit" class="btn-primary">保存</button>
    <button type="submit" class="btn-ghost" formaction="{{ url_for('settings.reset_field', field='days_per_week') }}" formnovalidate>↺ 默认</button>
  </form>
</div>

<div class="card">
  <h2 style="margin-top:0">进阶 (T2/T3)</h2>
  {% for field, label, step in [
      ('t2_reset_pct', 'T2 重置比例', '0.05'),
      ('t2_fail', 'T2 失败次数上限', '1'),
      ('t3_target', 'T3 目标次数', '1')] %}
  <form method="post" action="{{ url_for('settings.update') }}" class="field-row" style="align-items:flex-end">
    <div class="field"><label>{{ label }} <span class="sub">{{ field }}</span></label>
      <input type="number" step="{{ step }}" name="{{ field }}" value="{{ s[field] }}"></div>
    <button type="submit" class="btn-primary">保存</button>
    <button type="submit" class="btn-ghost" formaction="{{ url_for('settings.reset_field', field=field) }}" formnovalidate>↺ 默认</button>
  </form>
  {% endfor %}
</div>
{% endblock %}
```

注： "最小变动" 文案改为 "取整粒度" — **会破坏 test_settings_view 的 `assert "最小变动" in text`**。两选： (a) 保留 "最小变动" 标签; (b) 改测试。grill Q21 要中文化清晰标签, "取整粒度" 更准。采 (b), 同步改测试 (Step 2)。

- [ ] **Step 2: 更新 test_settings_view 断言**

`tests/test_routes_settings.py` `test_settings_view` 改:

```python
def test_settings_view(client):
    rv = client.get("/settings")
    text = rv.data.decode("utf-8")
    assert rv.status_code == 200
    assert "取整粒度" in text           # rounding field, Chinese label
    assert "全局参数" in text            # page title still present
```

- [ ] **Step 3: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_settings.py -v`
Expected: 全 PASS (reset/update 路由逻辑未动, 仅模板+一处断言)。

- [ ] **Step 4: Commit**

```bash
git add webapp/templates/settings.html tests/test_routes_settings.py
git commit -m "feat(ui): settings grouped cards, per-field reset forms, Chinese labels"
```

---

### Task 8: schedule.html 排版 + confirm

**Files:**
- Modify: `webapp/templates/schedule.html`
- Test: `tests/test_routes_schedule.py`

**Interfaces:**
- Consumes: Task 1 `.card` `.table` `.btn-primary` `.btn-danger` `.num`。
- Produces: schedule 页 (已进 sidebar, Task 2) — main/aux 各卡片 + 细线表 + 21 行等宽输入 + 保存/恢复默认分级 + 恢复默认 confirm。

**测试约束:** 页面必须含 `Main` 和 `Aux` (test_schedule_view 断言 `b"Main"`/`b"Aux"` — 现模板用 `kind | capitalize`)。保留 capitalize 渲染。表单字段名 `{{kind}}_{{w}}_{{field}}` 不变 (save 路由解析依赖)。恢复默认 confirm 用 `onsubmit` return confirm (非 htmx, 因是普通 form POST)。

- [ ] **Step 1: 重写 schedule.html**

```html
{% extends "base.html" %}
{% block title %}21 周进度表{% endblock %}
{% block content %}
<h1>21 周进度表</h1>
<form action="{{ url_for('schedule.save') }}" method="post">
  {% for kind in kinds %}
  <div class="card">
    <h2 style="margin-top:0">{{ kind | capitalize }}</h2>
    <table class="table num">
      <tr><th>周</th><th>强度</th><th>次数</th><th>repout</th></tr>
      {% for w in weeks %}
      {% set r = by_kind[kind][w] %}
      <tr>
        <td>{{ w }}</td>
        <td><input type="number" step="0.025" name="{{ kind }}_{{ w }}_intensity"
                   value="{{ '%.3f'|format(r.intensity) }}"></td>
        <td><input type="number" name="{{ kind }}_{{ w }}_reps" value="{{ r.reps }}"></td>
        <td><input type="number" name="{{ kind }}_{{ w }}_repout" value="{{ r.repout }}"></td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endfor %}
  <button type="submit" class="btn-primary">保存</button>
</form>
<form action="{{ url_for('schedule.reset') }}" method="post" style="margin-top:12px"
      onsubmit="return confirm('恢复默认进度表? 当前自定义将丢失')">
  <button type="submit" class="btn-danger">恢复默认进度表</button>
</form>
{% endblock %}
```

- [ ] **Step 2: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_schedule.py -v`
Expected: 全 PASS (字段名/Main/Aux 保留)。

- [ ] **Step 3: Commit**

```bash
git add webapp/templates/schedule.html
git commit -m "feat(ui): schedule table styling + reset confirm"
```

---

### Task 9: plan.html 微调 + mode_preview/reseed 套样式

**Files:**
- Modify: `webapp/templates/plan.html`
- Modify: `webapp/templates/mode_preview.html`
- Modify: `webapp/templates/reseed.html`
- Test: `tests/test_routes_plan.py`, `tests/test_routes_reseed.py`

**Interfaces:**
- Consumes: Task 1 `.card` `.btn-primary` `.num` `.meta`; Task 2 sidebar; 现有 plan 逻辑。
- Produces: plan 页 Day 卡片 + 顶/底双 submit; mode_preview/reseed 套 `.card`。

**测试约束:** reseed banner 须含 "重测" 或 "reseed" (test_plan_banner 断言); reseed 页须含 lift name (Squat)。plan 逻辑 (表单字段 `log_<id>`, hx-post save_log) 不动。

- [ ] **Step 1: 重写 plan.html**

单 form 顶+底双 submit, Day 卡片化, 末组输入右侧:

```html
{% extends "base.html" %}
{% block title %}Week {{ week }} 计划{% endblock %}
{% block content %}
<h1>Week {{ week }} 计划</h1>
{% if due_reseeds %}
<div class="flash">
  新周期开始 — 待重测: {{ due_reseeds | join(", ") }}
  <a href="{{ url_for('reseed.view') }}">去重测</a>
</div>
{% endif %}
<p class="meta">练完填每个动作的<b>末组次数</b>(填完自动保存,关掉也不丢)。全部练完点 <b>提交并算下周</b>。</p>
<p><a class="btn" href="{{ url_for('plan.export_week') }}" download>📱 导出本周计划(手机看)</a></p>
<form method="post" action="{{ url_for('plan.submit') }}">
  <button type="submit" class="btn-primary" style="margin-bottom:16px">提交并算下周</button>
  {% for day, items in by_day %}
  <div class="card">
    <h2 style="margin-top:0">Day {{ day }}</h2>
    {% for it in items %}
      <div class="field-row" style="justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line)">
        <div>
          <strong>{{ it.name }}</strong>
          <span class="meta num">{{ it.mode }} |
            {%- if it.is_bodyweight %} +{{ it.weight }} ({{ it.working_weight }}){% else %} {{ it.weight }}{% endif %} kg
            {% if it.mode=='sbs' %} x {{ it.reps }} x {{ it.sets }} | rep-out {{ it.repout }}
            {% elif it.mode=='linear_t2' %} x {{ it.target }} x {{ it.sets }} | streak {{ it.streak }}
            {% else %} x {{ it.target }} x {{ it.sets }}
            {% endif %}
            | est 1RM {{ "%.2f"|format(it.est1rm) if it.est1rm is not none else '—' }}
          </span>
        </div>
        <label>末组: <input type="number" name="log_{{ it.id }}" value="{{ it.logged }}"
               hx-post="{{ url_for('plan.save_log', lid=it.id) }}" hx-trigger="change"
               hx-target="next .save-ok" hx-swap="innerHTML">
          <span class="save-ok num">{{ it.live_html|safe }}</span></label>
      </div>
    {% endfor %}
  </div>
  {% endfor %}
  <button type="submit" class="btn-primary">提交并算下周</button>
</form>
{% endblock %}
```

注： `.save-ok` 的 `.up`/`.down` 子 span 由后端 `_live_html` 生成 (含 class), app.css 需补 `.save-ok` 规则。加到 Task 1 app.css 尾部 (或此处补丁):

```css
/* live preview under log input (classes emitted by plan._live_html) */
.save-ok{color:var(--muted);font-size:.85em;margin-left:6px}
.save-ok .up{color:var(--up);font-weight:bold}
.save-ok .down{color:var(--down);font-weight:bold}
.save-ok .first{color:var(--muted)}
```

- [ ] **Step 2: 重写 mode_preview.html**

```html
{% extends "base.html" %}
{% block title %}换 mode{% endblock %}
{% block content %}
<h1>{{ lift.name }} → {{ preview.mode }}</h1>
<div class="card">
  <p class="meta">历史保留, est1rm 从历史重算。下面是新 mode 的起点状态, 可改后确认:</p>
  <form method="post" action="{{ url_for('lifts.mode_apply', lid=lift.id) }}">
    <input type="hidden" name="mode" value="{{ preview.mode }}">
    <div class="field"><label>est1RM (从历史)</label>
      <div class="num">{{ "%.2f"|format(preview.est1rm) if preview.est1rm is not none else '—' }}</div></div>
    {% if preview.mode == 'sbs' %}
    <div class="field"><label>新 TM</label>
      <input name="tm" type="number" step="0.5" value="{{ preview.tm }}"></div>
    {% else %}
    <div class="field"><label>新重量</label>
      <input name="weight" type="number" step="0.5" value="{{ preview.weight }}"></div>
    {% endif %}
    <div class="field-row" style="margin-top:12px">
      <button type="submit" class="btn-primary">确认切换</button>
      <a class="btn-ghost" href="{{ url_for('lifts.view') }}">取消</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: 重写 reseed.html**

```html
{% extends "base.html" %}
{% block title %}重测 max{% endblock %}
{% block content %}
<h1>第 {{ cycle }} 周期 — 重测 max</h1>
{% if not due %}
  <p class="meta">当前无需重测。</p>
{% else %}
  {% for r, st in due %}
  <div class="card">
    <div class="field-row" style="justify-content:space-between;align-items:center">
      <div><strong>{{ r.name }}</strong>
        <span class="meta num">当前 TM {{ '%.1f'|format(st.tm or 0) }}</span></div>
      <div class="field-row" style="align-items:center">
        <form action="{{ url_for('reseed.apply', lid=r.id) }}" method="post" class="field-row" style="align-items:center">
          <input type="number" step="0.5" name="max" placeholder="新 max" style="max-width:120px">
          <button type="submit" class="btn-primary">重测并重置</button>
        </form>
        <form action="{{ url_for('reseed.skip', lid=r.id) }}" method="post">
          <button type="submit" class="btn-ghost">跳过</button>
        </form>
      </div>
    </div>
  </div>
  {% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 4: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_plan.py tests/test_routes_reseed.py -v`
Expected: 全 PASS (banner 含 "重测"; reseed 页含 lift name)。

- [ ] **Step 5: Commit**

```bash
git add webapp/templates/plan.html webapp/templates/mode_preview.html webapp/templates/reseed.html webapp/static/app.css
git commit -m "feat(ui): plan day cards + dual submit; style mode_preview and reseed"
```

---

### Task 10: week_export token 同步 + 全页目检 + 全测试

**Files:**
- Modify: `webapp/templates/week_export.html`

**Interfaces:**
- Consumes: Task 1 token 值。
- Produces: week_export 视觉 token 与主站一致 (仍自包含, 不引外部 CSS)。

**约束:** week_export 保持自包含离线 (无 `<link>`, inline `<style>`)。只改 token 值 (色/字体) 同步。无 pytest (独立导出页), 手动验。

- [ ] **Step 1: 同步 week_export.html style token**

`week_export.html` `<style>` 块改字体/色引用同值 (手抄, 不用 CSS 变量以便老浏览器/离线):

```css
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:12px auto;max-width:680px;padding:0 8px;color:#1a1a1a;line-height:1.5}
h1{font-size:1.25em;margin-bottom:4px}
h2{margin-top:1.2em;border-bottom:1px solid #e2e2e2;font-size:1.05em}
.lift{padding:6px 0;border-bottom:1px solid #eee;word-break:break-word}
.name{font-weight:bold;font-size:1.02em}
.meta{color:#6b6b6b;font-size:.9em;display:block;margin-top:2px;font-family:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace}
.log{font-size:.9em;margin-top:2px;color:#2e7d32}
.log.empty{color:#999}
.save-ok{color:#6b6b6b;font-size:.85em;margin-left:4px}
.save-ok .up{color:#2e7d32;font-weight:bold}
.save-ok .down{color:#c62828;font-weight:bold}
.save-ok .first{color:#6b6b6b}
@media print{body{max-width:none}}
```

- [ ] **Step 2: 全测试**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS。

- [ ] **Step 3: 手动目检各页**

启动: `conda run -n sbs python -m webapp` (或项目启动命令)。
逐页目检: `/` (plan) `/lifts` (展开编辑) `/settings` `/schedule` `/reseed` `/lifts/1/mode`。验 sidebar 高亮、reseed 徽章、展开行编辑/取消/校验回显、级联、confirm。

- [ ] **Step 4: Commit**

```bash
git add webapp/templates/week_export.html
git commit -m "feat(ui): sync week_export tokens with design system"
```

---

## Self-Review 记录

- **Spec 覆盖:** §1 设计系统→Task1; §2 骨架→Task2+3; §3 动作页→Task4/5/6; §4 其余页→Task7/8/9; week_export→Task10; flash 分级→Task2; 组合表注入→Task3+6; reseed 徽章→Task2+3; 校验回显→Task5; 空态→Task6 (lifts) / reseed (现状)。全覆盖。
- **Placeholder 扫描:** 无 TBD/TODO。所有代码步含完整代码。
- **类型一致:** `lifts.row` / `lifts.row_edit` / `lifts.edit` 端点名跨 Task4/5/6 一致; `legal_map` (Task3 产 → Task5/6 用) 一致; `reseed_count` (Task3 产 → Task2 base.html 用) 一致; `.tag-accent`/`.tag-muted`/`.field-row`/`.flash-error` 类名跨任务一致。
- **既有测试兼容:** settings "最小变动"→"取整粒度" 断言已在 Task7 Step2 同步改; schedule "Main"/"Aux" 保留; reseed banner "重测" 保留; lifts 字段名全保留。Task4 重写 _lift_row 后 lifts.html (Task6 前) 短暂不一致 — Task4 Step5 已标注, 若中间态测试失败属预期, Task6 完成即恢复。