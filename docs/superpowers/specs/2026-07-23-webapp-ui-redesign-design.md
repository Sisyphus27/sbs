# webapp UI 重做设计

日期： 2026-07-23
状态： 已确认 (用户全 OK)
范围： 呈现层重做 — 极简工具风 + 左侧 sidebar + 动作页展开行编辑

## 背景

webapp (Flask + HTMX + SQLite) 主页面 (本周计划) 清楚， 但其余页面混乱：

- 无设计系统 — 样式靠 `base.html` 一个 inline `<style>` (~13 规则) + 散落各模板 inline style。`week_export.html` 另起一套。
- 导航不完整 — `base.html` nav 只 3 链接 (本周计划/动作管理/全局参数)。`/schedule`、`/reseed` 无入口 (死页， reseed 只从 plan banner 进)。
- 表单失控 — lifts 编辑行 ~10 input 横排 flex-wrap 错位； settings 标签中英文混排、部分行带 ↺ 默认按钮部分没有、无对齐网格； schedule 42 输入裸 `<table>` 无样式。
- 无视觉层级 — 无主/次/危险按钮区分， 无卡片/分区容器。

## 核心原则

**只动呈现层。** 后端 `routes/*.py` / `repo.py` / `services/` / engine 一律不动 (干净、有测试覆盖)。唯一后端触碰： 为展开行加 2 个只读 GET 端点， 不改任何业务逻辑。

视觉方向： **极简工具风** — 白底、黑字、单 accent 深蓝、大量留白、表格细线、数字等宽。重内容轻装饰， 贴"个人工具 + 算法审美"。

## 1. 设计系统 (`webapp/static/app.css`)

抽全部样式出 inline `<style>`， 集中一文件。CSS 自定义属性定义 token:

```css
:root{
  --bg:#ffffff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2e2e2;
  --accent:#1f4e79;            /* 深蓝 单 accent */
  --up:#2e7d32; --down:#c62828;  /* 保留现有涨/降色 */
  --space:8px; --radius:3px;
  --font:system-ui,sans-serif; --mono:ui-monospace,monospace;
}
```

组件类:

| 类 | 用途 |
|---|---|
| `.btn` / `.btn-primary` / `.btn-danger` / `.btn-ghost` | 按钮分级 (主/危险/幽灵-如↺默认) |
| `.card` | 分区容器 (白底细边框) |
| `.field` | label+input 对齐网格 |
| `.tag` | mode / load_model 小徽章 |
| `.table` | 细线表格 (进度表) |

数字用 `--mono` 等宽保证对齐。`week_export.html` 保持自包含 (不引外部 CSS)， 只同步 token 值视觉一致。

## 2. 布局骨架 (`base.html`)

左侧固定 sidebar + 右内容区:

```
┌──────────┬────────────────────────────┐
│ SIDEBAR  │  顶栏: 页标题 + flash       │
│ (固定)    ├────────────────────────────┤
│ ▸ 训练    │                            │
│   本周计划│        内容区               │
│   进度表  │     (max-width ~1100px)    │
│ ▸ 管理    │                            │
│   动作   │                            │
│   重测   │                            │
│ ▸ 配置    │                            │
│   全局参数│                            │
└──────────┴────────────────────────────┘
```

- sidebar 分组导航 (训练/管理/配置) — 解决 schedule/reseed 死页。
- 当前页高亮： 用 `request.endpoint` 加 `.active`。
- 顶部品牌 "SBS"。
- 窄屏 sidebar 折到顶部 (media query)。
- flash 消息统一顶栏样式。

## 3. 动作管理页 (重点) `lifts.html` + `_lift_row.html`

**列表态 (默认只读):** 每动作一卡片行:
`名字 | [mode徽章][load_model徽章] | day·sets·重量 | 操作(编辑/换mode/删除)`。无 input 裸露。

**展开编辑态:** 点"编辑", HTMX 把该行换成展开表单卡片。字段分组成 `.field` 网格:

- 基础： name / day / sets
- 模式相关 (按 mode 条件渲染， 沿用现逻辑): sbs→max/lift_kind；linear_t2/t3→start/incr/intensity/reps/repout
- 负重 (bodyweight/pure_bodyweight): bodyweight_pct

"保存" HTMX 替换回只读行； "取消"换回只读行。删除 (`.btn-danger`)、换 mode 收进展开行底部。

**新增动作:** 顶部一 `.card` 表单， 同 `.field` 网格 + load_model→mode 级联 (现有 JS 保留)。

**新增后端端点 (只读， 无逻辑改动):**

| 端点 | 用途 |
|---|---|
| `GET /lifts/<id>/row` | 返回只读行局部模板 (取消/保存后换回) |
| `GET /lifts/<id>/edit` | 返回展开表单局部模板 (点编辑) |

`POST /lifts/new`、`POST /lifts/<id>/edit`、`POST /lifts/<id>/delete` 复用现有。

模板变量名保持不变， 后端逻辑不变。

## 4. 其余页面

- **全局参数 `settings.html`:** 字段分卡片 — 基础 (rounding/days_per_week/incr/体重)、进阶 (t2_reset_pct/t2_fail/t3_target)。`.field` 网格统一中文标签+单位； ↺默认按钮对齐右侧 `.btn-ghost`。
- **进度表 `schedule.html`:** 进 sidebar。main/aux 各一卡片， `.table` 细线， 21 行输入等宽对齐； 保存 `.btn-primary` + 恢复默认 `.btn-danger` 分级。
- **本周计划 `plan.html`:** 已清楚， 微调 — Day 用卡片分区， 末组输入对齐右侧， 提交按钮 `.btn-primary` 置顶+置底。reseed banner 保留。
- **mode_preview / reseed:** 套 `.card` + `.field`, 统一按钮分级。
- **week_export.html:** 独立离线页保持自包含， 同步 token 视觉一致。

## 5. 错误/边界 + 测试

- HTMX 端点失败： 保留现有 `flash` + 400 返回错误行模式， 错误行红边。
- 空列表： lifts 空时显"暂无动作， 上方新增"。
- 非法输入： 后端校验不变， flash 统一顶栏样式。
- **测试:** 不动逻辑， 现有 `tests/test_routes_*.py` 应全绿 (模板变量名保持)。新增 GET `/lifts/<id>/row`、`/lifts/<id>/edit` 补 2-3 个 render 测试。各页手动目检。

## 不做 (YAGNI)

- 不引入前端框架/构建步骤 (保留 HTMX + Jinja)。
- 不动后端业务逻辑 / engine / DB schema。
- 不做深色模式、响应式复杂交互、modal。
- 不改 week_export 的自包含离线特性。
