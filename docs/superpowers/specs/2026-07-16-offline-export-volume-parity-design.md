# 手机离线导出容量显示对齐（offline export volume parity）

Date: 2026-07-16
Status: Approved (A1 + A3)
Related: `2026-07-15-per-lift-volume-comparison-design.md`（容量 WoW 功能本体）

## 背景

`2026-07-15-per-lift-volume-comparison-design.md` 给 webapp 实时 plan 视图加了 per-lift 容量 WoW（`_tonnage_html`，经 `_live_html` 在 HTMX `save_log` 时实时刷新）。桌面端每行显示：`末组: [输入] ≈est1rm ±delta 容量 Xkg ↗+Y%`。

webapp 另有手机离线导出：`plan.export_week`（`/export/week.html`）→ `week_export.html`，注释明写 "for phone viewing… opens offline after copy to phone"。该路由调 `_by_day(conn)`，**已经**为每个 item 算出 `it.live_html`（内含 est1rm + delta + 容量 WoW 片段）。

**问题**：`week_export.html` 模板只输出了 `it.live`（纯 est1RM 数值），**从未输出 `it.live_html`**，容量段被丢弃。故手机离线版看不到容量。

## 目标（用户决策）

- 手机离线版显示**与桌面端 plan 视图完全一致**的容量信息（P1：严格一致）。
- 手机版定位为**只读参考**（用户练前/练中看，不在手机填末组次数，回家在 app 填 → A）。因此未填末组时容量为空，与桌面未填时一致，不做投影兜底（否决 P2）。

## 非目标

- 不改 CLI 离线产物 `sbs_cli/view/templates/week.html.j2`（另一条路径，非"手机离线版"）。
- 不加客户端 JS 实时算（手机只读，不在手机填次数）。
- 不做投影/兜底显示（P1 严格一致）。

## 方案

**A1（模板）+ A3（路由清理）**。

### A1 — 模板输出 live_html

`week_export.html` 当前（logged 分支）：

```jinja
<span class="log">本周末组: {{ it.logged }} → est1RM ≈{{ "%.2f"|format(it.live) }}</span>
```

改为输出 `_by_day` 已算好的 `it.live_html`（其内容 = `≈est1rm ±delta 容量 Xkg ↗Y%`，与桌面 `_live_html` 完全相同），外包 `.save-ok` span 以套用桌面同款颜色样式：

```jinja
{% if it.logged not in (None, '') %}
  <span class="log">本周末组: {{ it.logged }}
    <span class="save-ok">{{ it.live_html|safe }}</span>
  </span>
{% else %}
  <span class="log empty">本周末组: 未填</span>
{% endif %}
```

未填分支不变（live_html 为空字符串，桌面此时也为空）。

`week_export.html` 的 `<style>` 增加桌面 base.html 中对应规则：

```css
.save-ok{color:#4caf50;font-size:0.85em;margin-left:4px}
.save-ok .up{color:#2e7d32;font-weight:bold}
.save-ok .down{color:#c62828;font-weight:bold}
.save-ok .first{color:#888}
```

### A3 — 路由清理

`export_week` 中 155–161 行单独计算 `it.live`（仅 est1RM 数值）的循环删除——`live_html` 已含 est1RM，`it.live` 不再被模板引用。

## 数据流

零新逻辑。`_by_day` 现有：`item.live_html = _live_html(conn, item.id, reps)`，其中 `reps = item.logged or None`。

- `_live_html` → `_tonnage_html` → `lift_week_volume(conn, lid, week, is_current=True/False)`：已就绪，返回 `容量 Xkg ↗+Y%` / `容量 Xkg 首次`（week 1）/ `""`（未 log）。
- est1RM delta 经 `preview.live_preview`：已就绪。

## 渲染效果对照

桌面 plan.html 行：
```
Squat  sbs | 100 kg x 5 x 5 | rep-out 10 | est 1RM 120.00
末组: [12] ≈132.50 +2.10 容量 2600kg ↗+8%
```

手机 week_export.html 行（改后）：
```
Squat
sbs | 100 kg × 5 × 5 | rep-out 10 | 最佳 1RM 120.00
本周末组: 12 ≈132.50 +2.10 容量 2600kg ↗+8%
```

未填时：`本周末组: 未填`（无容量段，同桌面）。

## 边界（均由现有 service 处理，无需新增）

| 场景 | 行为 |
|------|------|
| 本周末组未填 | live_html 空 → 手机显示 `未填`，无容量（= 桌面空）|
| week 1（无上周历史） | `_tonnage_html` → `容量 Xkg 首次` |
| 无历史 est1rm | delta → `(首次)` |
| 同名两行（如 Face Pull day2/day4） | `_by_day` 按 row id 构造 item，不混淆 |
| `it.live_html` 含 HTML（span 标签） | 模板用 `|safe`，与 plan.html 一致 |

## 测试（TDD）

新增 webapp 导出测试（仿现有 `tests/` 中 webapp route 测试风格）：

1. **logged → 含容量**：某 lift 本周已 log 末组次数，`export_week` 输出 HTML 含 `容量` 字样 + 正确 WoW% 符号（`↗+` / `↘`）。
2. **未 log → 不含容量**：无任何 log 时，输出含 `未填`，不含 `容量`。
3. **week 1**：`首次` 标记出现，不报除零。

测试驱动：先写测试（RED）→ A1+A3 改（GREEN）→ 必要时 refactor。

## 改动文件清单

- `webapp/templates/week_export.html`（A1：模板 + CSS）
- `webapp/routes/plan.py`（A3：删 `it.live` 循环，155–161 行）
- `tests/`（新增导出测试）
