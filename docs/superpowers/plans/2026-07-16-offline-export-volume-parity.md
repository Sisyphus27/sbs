# 手机离线导出容量片段对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/export/week.html`（手机离线只读视图）输出与桌面 `plan.html` 同一份 `live_html` 片段（est1RM + delta + 容量 WoW），并清掉只服务旧渲染路径的死代码。

**Architecture:** 零新逻辑。`_by_day`（`webapp/routes/plan.py:49`）已经为每个 item 算好 `item.live_html = _live_html(conn, item.id, reps)`，桌面 `plan.html` 已渲染它；`week_export.html` 只是一直没引用，仍输出旧的 `it.live`（纯 est1RM 数值）。A1 改模板输出 `live_html` + 内联桌面同款 `.save-ok` CSS；A3 删掉 `export_week` 中只为旧模板计算 `it.live` 的循环及其本地 `live_preview` 导入。TDD：先加导出测试（RED）→ A1（GREEN）→ A3（refactor，保持 GREEN）。

**Tech Stack:** Flask + Jinja2，SQLite，pytest。所有命令经 `conda run -n sbs`（项目固定环境）。

## Global Constraints

- **范围 = 片段一致**：目标只是 est1RM+delta+容量 WoW 这段串（同一 `_live_html` helper）在桌面与手机逐字相同。标签（`末组` vs `本周末组`）、rep 呈现（input `[12]` vs bare `12`）、字体大小（手机 `.save-ok` 嵌在 `.log{0.9em}` 内 ≈ 0.765em vs 桌面裸 0.85em）是手机端有意取舍，**不**计入一致性目标。
- **A1（模板）+ A3（路由清理）仅此两项**。不改 CLI 产物 `sbs_cli/view/templates/week.html.j2`（另一条路径）。不加客户端 JS 实时算（手机只读）。不做投影/兜底（未填末组即无容量，同桌面）。
- **分支先行**：开始 commit 前从 `main` 切出 feature 分支（仓库当前在 `main`，遵循"默认分支上不直接提交"）。建议名 `feature/offline-export-volume-parity`。
- **环境**：所有 pytest / python 命令前缀 `conda run -n sbs`。
- **TDD 顺序锁定**：必须 A1 先于 A3。A3 删除 `it.live` 的计算，若 A1 未先把模板里的 `it.live` 引用换掉，`export_week` 渲染会因 `it.live` 未定义而报错。

---

## File Structure

- **Modify** `webapp/templates/week_export.html` — A1：logged 分支改为输出 `it.live_html`（外包 `.save-ok` span），`<style>` 增补桌面 base.html 同款 `.save-ok` 配色。单一职责：自包含离线 HTML 模板。
- **Modify** `webapp/routes/plan.py` — A3：`export_week`（149–164 行）删除 155–161 行（`live_preview` 本地导入 + 计算 `it.live` 的循环）。`_by_day` / `_live_html` / `_tonnage_html` 不动。
- **Modify** `tests/test_routes_plan.py` — 新增 2 个导出测试，镜像桌面端既有吨位测试。

无新文件。`_by_day` 已产出 `item.live_html`，无需改 service / repo / 引擎。

---

### Task 1: 新增导出测试（RED）

**Files:**
- Modify: `tests/test_routes_plan.py`（文件末尾追加 2 个测试）

**Interfaces:**
- Consumes: `client` / `app` fixtures（既有 conftest，同文件其他测试已在用）；`repo.create_lift`、`repo.save_log`（签名见 `webapp/repo.py`，与既有 `test_plan_view_shows_tonnage_for_logged_lift` 完全一致的 fixture 形态）。
- Produces: 两个失败测试，驱动 Task 2 的 A1 模板改动。`test_export_week_shows_tonnage_when_logged` 在 A1 前必 FAIL（模板不输出 `容量`），A1 后 PASS。`test_export_week_omits_tonnage_when_logged` 是回归守卫（空状态本就无 `容量`），A1 前后都 PASS，用于钉住"未填分支不被 A1 污染"。

- [ ] **Step 1: 在 `tests/test_routes_plan.py` 末尾追加两个测试**

在文件最后一行（`test_plan_view_shows_tonnage_wow_delta_for_t2` 之后）追加：

```python
def test_export_week_shows_tonnage_when_logged(client, app):
    """手机离线导出含与桌面同源的 容量 片段（经 _by_day -> _live_html 接出）。
    week 1 -> 首次 标记，不除零。fixture 同 test_plan_view_shows_tonnage_for_logged_lift：
    t3 Curl, start=30, log 18 -> 30 * (2*15 + 18) = 1440。"""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        repo.save_log(conn, lid, 1, 18)   # 30 * (2*15 + 18) = 1440
        conn.close()
    html = client.get("/export/week.html").get_data(as_text=True)
    assert "容量" in html and "1440kg" in html   # 容量片段已接到导出 HTML
    assert "≈" in html                            # est1RM 仍在同一片段内
    assert "首次" in html                          # week 1，无上周


def test_export_week_omits_tonnage_when_not_logged(client, app):
    """未填末组 -> 本周末组: 未填，无 容量 片段（与桌面空状态对齐）。
    回归守卫：A1 不应把 容量 渗进未填分支。"""
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
        conn.close()
    html = client.get("/export/week.html").get_data(as_text=True)
    assert "未填" in html
    assert "容量" not in html
```

- [ ] **Step 2: 运行新测试，确认 `shows_tonnage_when_logged` FAIL（RED）**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py::test_export_week_shows_tonnage_when_logged tests/test_routes_plan.py::test_export_week_omits_tonnage_when_not_logged -v
```
Expected:
- `test_export_week_shows_tonnage_when_logged` → **FAIL**（`AssertionError: assert "容量" in html`，因为当前模板只输出 `it.live` 纯数值，无容量片段）。
- `test_export_week_omits_tonnage_when_not_logged` → **PASS**（空状态本就无 `容量`；这是守卫，非 RED 驱动）。

若 `shows_tonnage_when_logged` 意外 PASS，说明 `容量` 已泄露进导出路径——停止，先查 `week_export.html` 是否已被改动。

- [ ] **Step 3: 确认既有导出测试仍 PASS（A1 前 baseline）**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py::test_export_week_standalone_with_progress -v
```
Expected: **PASS**（既有断言 `本周末组: 11` / `≈` / 离线无 `htmx` 均不受新测试影响）。

- [ ] **Step 4: Commit（RED 状态，feature 分支上记录 TDD 意图）**

```bash
git checkout -b feature/offline-export-volume-parity
git add tests/test_routes_plan.py
git commit -m "test(export): pin tonnage fragment in offline week export (RED)"
```

---

### Task 2: A1 — 模板输出 live_html + 内联 .save-ok CSS（GREEN）

**Files:**
- Modify: `webapp/templates/week_export.html:7-17`（`<style>` 增补）与 `:34-38`（logged 分支）

**Interfaces:**
- Consumes: `it.live_html`（`_by_day` 在 `webapp/routes/plan.py:80` 已为每个 item 设置；`_live_html` 返回 `≈{est1rm:.2f} {delta_html} {tonnage_html}` 或 `""`）。`it.logged`（既有）。
- Produces: 导出 HTML 含 `容量` 片段；Task 1 的 `shows_tonnage_when_logged` 由 RED 转 GREEN。

- [ ] **Step 1: 在 `<style>` 中 `.log.empty` 规则之后增补桌面同款 `.save-ok` 配色**

当前 `week_export.html` 第 7–17 行 `<style>` 末尾两行为：
```css
    .log{font-size:0.9em;margin-top:2px;color:#2e7d32}
    .log.empty{color:#999}
    @media print{body{max-width:none}}
```
把 `.log.empty` 与 `@media print` 两行之间插入 `.save-ok` 规则块。改后 `<style>` 相关段为：
```css
    .log{font-size:0.9em;margin-top:2px;color:#2e7d32}
    .log.empty{color:#999}
    .save-ok{color:#4caf50;font-size:0.85em;margin-left:4px}
    .save-ok .up{color:#2e7d32;font-weight:bold}
    .save-ok .down{color:#c62828;font-weight:bold}
    .save-ok .first{color:#888}
    @media print{body{max-width:none}}
```
（这 4 行与 `webapp/templates/base.html:15-18` 逐字一致，保证手机/桌面同款配色。）

- [ ] **Step 2: 替换 logged 分支，输出 `it.live_html`**

当前 `week_export.html` 第 34–38 行：
```jinja
      {% if it.logged not in (None, '') %}
        <span class="log">本周末组: {{ it.logged }} → est1RM ≈{{ "%.2f"|format(it.live) }}</span>
      {% else %}
        <span class="log empty">本周末组: 未填</span>
      {% endif %}
```
改为（去掉 `→ est1RM` 字样与 `it.live` 引用，改成外包 `.save-ok` 的 `live_html|safe`）：
```jinja
      {% if it.logged not in (None, '') %}
        <span class="log">本周末组: {{ it.logged }}
          <span class="save-ok">{{ it.live_html|safe }}</span>
        </span>
      {% else %}
        <span class="log empty">本周末组: 未填</span>
      {% endif %}
```
说明：`live_html` 已含 `≈{est1rm:.2f}`，故去掉旧标签 `→ est1RM` 即与桌面 `plan.html` 的 `.save-ok` 内容对齐。未填分支不变（`live_html` 此前就是空串）。`|safe` 与桌面 `plan.html:29` 一致——`live_html` 由服务端受控拼装（仅含 `<span class="up|down|first">` 与数值），无用户输入注入面。

- [ ] **Step 3: 运行 Task 1 的两个测试，确认 GREEN**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py::test_export_week_shows_tonnage_when_logged tests/test_routes_plan.py::test_export_week_omits_tonnage_when_not_logged -v
```
Expected: **2 PASS**。

- [ ] **Step 4: 运行既有导出测试，确认未回归**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py::test_export_week_standalone_with_progress -v
```
Expected: **PASS**。关键校验点：
- `"本周末组: 11" in html` 仍成立（`本周末组: {{ it.logged }}` 后接换行+span，`本周末组: 11` 仍是连续子串）。
- `re.search(r"≈\s*\d+\.\d{2}", html)` 仍命中（`live_html` 以 `≈{est1rm:.2f}` 开头）。
- 离线断言（`hx-post` / `/log/` / `htmx` 均不在）不受影响。

- [ ] **Step 5: 跑 routes 全量，确认无他处回归**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py -v
```
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add webapp/templates/week_export.html
git commit -m "feat(export): render live_html (est1rm+delta+tonnage) in offline week export"
```

---

### Task 3: A3 — 删除 export_week 中冗余的 it.live 计算（REFACTOR）

**Files:**
- Modify: `webapp/routes/plan.py:149-164`（`export_week`）

**Interfaces:**
- Consumes: A1 后模板不再引用 `it.live`，故 `export_week` 中为它计算的循环成为死代码。
- Produces: `export_week` 只剩 `_by_day` + `render_template`；`live_preview` 在该函数内的本地导入一并删除（`_live_html` 在 `:38` 有自己的导入，不受影响）。行为零变化（Task 1/2 测试保持 GREEN）。

- [ ] **Step 1: 删除 `export_week` 中 155–161 行（本地导入 + it.live 循环）**

当前 `webapp/routes/plan.py:149-164`：
```python
@bp.route("/export/week.html")
def export_week():
    """Standalone offline HTML of this week's plan + logged progress, for phone viewing.
    Self-contained (no nav/HTMX/server-relative URLs) so it opens offline after copy to phone."""
    conn = get_db()
    week, by_day = _by_day(conn)
    from ..services.preview import live_preview
    for day, items in by_day:
        for it in items:
            if it.logged not in ("", None):
                it.live = live_preview(conn, it.id, int(it.logged))["est1rm"]
            else:
                it.live = None
    html = render_template("week_export.html", week=week, by_day=by_day)
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'})
```
改为（删掉本地 `live_preview` 导入 + 整个 `for day, items in by_day` 循环）：
```python
@bp.route("/export/week.html")
def export_week():
    """Standalone offline HTML of this week's plan + logged progress, for phone viewing.
    Self-contained (no nav/HTMX/server-relative URLs) so it opens offline after copy to phone."""
    conn = get_db()
    week, by_day = _by_day(conn)
    html = render_template("week_export.html", week=week, by_day=by_day)
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="week-{week}.html"'})
```
说明：`live_html`（含 est1RM）已由 `_by_day` 在 `:80` 算好；`it.live` 不再被任何模板引用（见 Step 2 校验），本地 `live_preview` 导入只服务被删循环，留着是死代码。

- [ ] **Step 2: 全仓确认无残余 `it.live` 引用**

Run:
```bash
git grep -n "it\.live\b" -- webapp/
```
Expected: **无输出**（`webapp/` 下不再有 `it.live`；`it.live_html` 不被该正则匹配，因 `\b` 后无 `_`）。文档 `docs/` 与 `.md` 中的历史引用不计——限定 `-- webapp/`。

若仍有命中，停止并核查：A1 是否真的把 `week_export.html` 的 `it.live` 换掉了。

- [ ] **Step 3: 确认 `live_preview` 仍被 `_live_html` 使用（导入只是从 export_week 移除，不是全局删除）**

Run:
```bash
git grep -n "live_preview" -- webapp/routes/plan.py
```
Expected: 仅命中 `:38`（`_live_html` 内的 `from ..services.preview import live_preview`）与 `:39`（`p = live_preview(conn, lid, reps)`）。`export_week` 内不再出现。

- [ ] **Step 4: 跑导出 + routes 全量测试，确认 GREEN 不变（refactor 零行为变化）**

Run:
```bash
conda run -n sbs python -m pytest tests/test_routes_plan.py -v
```
Expected: 全 PASS（含 Task 1 两个新测试 + 既有 `test_export_week_standalone_with_progress`）。

- [ ] **Step 5: 跑全量测试套件，确认无他处回归**

Run:
```bash
conda run -n sbs python -m pytest -q
```
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/plan.py
git commit -m "refactor(export): drop dead it.live loop + live_preview import in export_week"
```

---

## Self-Review

**1. Spec coverage**
- §目标（片段一致）→ Task 2 Step 2 输出 `live_html`；Global Constraints 已声明范围。✓
- §A1（模板输出 live_html + `.save-ok` CSS）→ Task 2 Step 1（CSS）+ Step 2（jinja）。✓
- §A3（删 155–161 含本地 `live_preview` 导入）→ Task 3 Step 1。✓
- §测试（logged 含容量 presence-only / 未填无容量 / week1 首次）→ Task 1 两测试覆盖；test 1 合并 spec 测试 1+3（同 week-1 fixture，`容量`+`首次`）。✓
- §非目标（不改 CLI j2、不加 JS、不投影）→ Global Constraints 锁定；无任务触及。✓

**2. Placeholder scan** — 无 TBD/TODO/"add appropriate"；每步含完整代码或确切命令。✓

**3. Type consistency** — `it.live_html`（`_by_day:80` 设置，`str`）、`it.logged`（`str`）在 Task 2 模板与 Task 1 测试中一致；`_live_html(conn, lid, reps)->str`、`_by_day(conn)->(week, by_day)` 签名在 Task 2/3 引用与源码 `:30`/`:49` 一致。✓

**依赖顺序**：Task 2（A1）必须先于 Task 3（A3）——Global Constraints 已锁；Task 编号即执行顺序。
