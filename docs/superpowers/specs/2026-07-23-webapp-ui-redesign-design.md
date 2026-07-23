# webapp UI 重做设计

日期： 2026-07-23
状态： 已确认 (脑暴全 OK + grilling 24 问决议注入)
范围： 呈现层重做 — 极简工具风 + 左侧 sidebar + 动作页展开行编辑
关联： ADR 0006, CONTEXT.md `## Presentation`

## 背景

webapp (Flask + HTMX + SQLite) 主页面 (本周计划) 清楚， 但其余页面混乱：

- 无设计系统 — 样式靠 `base.html` 一个 inline `<style>` (~13 规则) + 散落各模板 inline style。`week_export.html` 另起一套。
- 导航不完整 — `base.html` nav 只 3 链接 (本周计划/动作管理/全局参数)。`/schedule`、`/reseed` 无入口 (死页， reseed 只从 plan banner 进)。
- 表单失控 — lifts 编辑行 ~10 input 横排 flex-wrap 错位； settings 标签中英文混排、部分行带 ↺ 默认按钮部分没有、无对齐网格； schedule 42 输入裸 `<table>` 无样式。
- 无视觉层级 — 无主/次/危险按钮区分， 无卡片/分区容器。

## 核心原则

**只动呈现层。** 后端 `routes/*.py` / `repo.py` / `services/` / engine 一律不动 (干净、有测试覆盖)。后端仅新增： 2 个只读 GET 端点 (展开行 partial) + 1 个 context processor (注入组合表 + 待重测计数) + flash 错误类别。不改任何业务逻辑。

视觉方向： **极简工具风** — 白底、黑字、单 accent 深蓝、大量留白、表格细线、数字等宽。重内容轻装饰， 贴"个人工具 + 算法审美"。

## 1. 设计系统 (`webapp/static/app.css`)

抽全部样式出 inline `<style>`， 集中一文件。CSS 自定义属性定义 token:

```css
:root{
  --bg:#ffffff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2e2e2;
  --accent:#1f4e79;            /* 深蓝 单 accent */
  --up:#2e7d32; --down:#c62828;  /* 保留现有涨/降色 */
  --danger:#c62828;
  --space:8px; --radius:3px;
  --font:system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
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
| `.flash` / `.flash-error` | 成功灰条 / 错误红条 |

**Accent 边界 (grill Q8):** 深蓝 accent 专属 主按钮 / sidebar 当前页高亮 / 链接 / input focus 描边。**不用于** 危险按钮 (红)、涨跌色 (绿/红)、徽章。

**徽章策略 (Q9):** mode 徽章**只突出 sbs** (accent 描边); linear_t2/t3/none 灰边中性。load_model 徽章纯灰小字注记， 不抢戏。**不引彩虹色。**

**等宽字体边界 (Q10):** 成列对齐的数字 (重量/强度/reps/est1RM/WoW%/schedule 输入) 用 `--mono`; 散文内联数字保持正文字体。

**字体 (Q20):** 正文 15px / 行高 1.5; 标题 h1 1.4em / h2 1.2em / h3 1.05em。系统字体栈， 不自托管网络字体。

`week_export.html` 保持自包含 (不引外部 CSS), 只同步 token **值** 视觉一致 (Q17)。

## 2. 布局骨架 (`base.html`)

左侧固定 sidebar + 右内容区:

```
┌──────────┬────────────────────────────┐
│ SIDEBAR  │  顶栏: 页标题               │
│ (固定)    ├────────────────────────────┤
│ 品牌 SBS  │                            │
│ ▸ 训练    │        内容区               │
│   本周计划│     (max-width ~1100px)    │
│   进度表  │   flash 在内容区顶部        │
│ ▸ 动作    │                            │
│   动作   │                            │
│   重测 ●N│                            │
│ ▸ 配置    │                            │
│   全局参数│                            │
└──────────┴────────────────────────────┘
```

- **sidebar 3 组 (Q1):** 训练 (本周计划/进度表) / 动作 (动作/重测) / 配置 (全局参数)。重测并入动作组 — Reseed 是 per-Lift 操作， 非程序级视图。
- **当前页高亮 (Q2):** 用 `request.blueprint` (非 endpoint) 判所属组加 `.active`。
- **待重测徽章 (Q16):** reseed 链接旁计数徽章 `●N`, `due_reseeds` 非空时显。经 context processor 每页查 `_due_lifts` (本地单用户， 开销忽略)。plan banner 保留。
- **flash (Q12):** 内容区顶部全宽细条， 成功灰边 / 错误红边。后端校验失败处加 `flash(msg, "error")` 类别。不自动消失。
- **窄屏 (Q11):** ≤900px sidebar 折顶部一条横 nav (纯 CSS media query), 无汉堡菜单/手势/折叠动画。

## 3. 动作管理页 (重点) `lifts.html` + `_lift_row.html`

**列表态 (默认只读):** 每动作一卡片行:
`名字 | [mode徽章][load_model徽章] | day·sets·重量 | 操作(编辑)`。无 input 裸露。

**展开编辑态:** 点"编辑", HTMX `GET /lifts/<id>/edit` 把该行换成展开表单卡片。字段分组成 `.field` 网格:

- 基础： name / day / sets
- 模式相关 (按 mode 条件渲染， 沿用现逻辑): sbs→max/lift_kind；linear_t2/t3→start/incr/intensity/reps/repout
- 负重 (bodyweight/pure_bodyweight): bodyweight_pct

**交互决议:**

- **整行一次保存 (Q14):** 一个"保存"提交展开表单全部字段到 `POST /lifts/<id>/edit` (复用现 upsert 逻辑)。
- **校验失败保留编辑态 (Q3):** `POST edit` 校验失败 (如 incr≤0 / 非法 combo) 返回**展开表单 partial** 带回显错误值 + 行内红字， **不**回只读行丢输入。后端 error 分支 render edit-partial 而非 row-partial。
- **取消 (Q4):** `hx-get="/lifts/<id>/row"` 重新拉只读行 (保证所见 = DB 最新， 无前端缓存)。
- **换 mode 独立页 (Q5):** 展开行底部"换 mode"链接 → 跳 `mode_preview.html` 整页确认 (est1RM/TM 预览), 样式统一但结构不动。**不**行内嵌预览。
- **删除 (Q6):** `.btn-danger` + `hx-confirm` 原生 confirm。

**新增动作 (Q22):** 顶部 `.card` 表单， `.field` 网格。默认值维持现状 (day=1/sets=3/barbell; max/start/incr 留空 placeholder; bodyweight_pct 默认 1.0)。load_model→mode 级联。

**新增后端端点 (只读， 无逻辑改动):**

| 端点 | 用途 |
|---|---|
| `GET /lifts/<id>/row` | 只读行 partial (取消/保存后换回) |
| `GET /lifts/<id>/edit` | 展开表单 partial (点编辑) |

**级联 JS (Q13):** 抽到 `static/app.js`。合法组合表**后端注入** — `is_legal_combo` 同源导 JSON 给模板 (`{{ legal_map|tojson }}`), JS 只读它。前后端单一事实源， 避免硬编码副本漂移。

## 4. 其余页面

- **全局参数 `settings.html` (Q7/Q21):** 字段分卡片 — 基础 (取整粒度/每周天数/默认步进/体重)、进阶 (T2重置比例/T2失败上限/T3目标)。`.field` 网格。**中文主标签 + 英文参数名小字副注** (如 "每周天数" + `days_per_week` 灰小字)。**↺默认按钮 = 每字段独立小 form**, 点 ↺ 只重置该字段， 不提交/丢弃主表单未保存输入。
- **进度表 `schedule.html` (Q6/Q18):** 进 sidebar。main/aux 各一卡片 (窄屏上下), `.table` 细线 21 行输入等宽对齐。**只排版不加额外交互** (无批量编辑/复制上周)。保存 `.btn-primary` + 恢复默认 `.btn-danger` **带 confirm**。
- **本周计划 `plan.html` (Q15/Q23):** 信息结构零改动 (引擎计算/涨跌色/meta 全保留)。仅视觉统一 — Day 卡片分区、末组输入右侧对齐、数值 mono。**单 form 顶+底双 submit** ("提交并算下周")。reseed banner 保留。
- **mode_preview / reseed:** 套 `.card` + `.field`, 统一按钮分级。reseed 重测表单 (输入 max + 按钮) 与跳过**不加 confirm** (Q6 原则： 需输入/可再来 = 不加)。
- **week_export.html (Q17):** 独立离线页保持自包含 + 680px 手机窄列结构不动， 只同步 token 值视觉一致。

**确认原则 (Q6):** 不可逆 + 一键 = 要 confirm (lift 删除、schedule 重置); 需输入/可再来 = 不加 (reseed 各动作)。

## 5. 空态 (Q19)

- lifts 空 → "暂无动作， 上方新增"
- plan 空 (无 lift) → 引导去动作页新增
- reseed 空 → "当前无需重测" (现状已有)
- schedule 永有默认 42 行， 无空态
- history/est1RM 空 → 显 "—" (现状)
- **不加加载 spinner** (本地请求毫秒级)

## 6. 错误处理 + 测试

- HTMX 校验失败： 保留编辑态回显错误值 (Q3), 行内红字 + flash 红条。
- 非法输入后端校验不变。
- **测试:** 不动逻辑， 现有 `tests/test_routes_*.py` 应全绿 (模板变量名保持)。新增 GET `/lifts/<id>/row`、`/lifts/<id>/edit` 补 render 测试； context processor 注入的组合表/计数补测试。各页手动目检。

## 7. 实施阶段 (Q24)

按依赖排序， 每阶段独立验证 + `pytest` 保绿:

1. **设计系统 + 骨架** — `app.css` (token+组件类) + `base.html` (sidebar 3 组 + blueprint 高亮 + flash 分级 + context processor 注入 reseed 计数)。全站裸奔但骨架在。
2. **动作管理页** — lifts 列表只读化 + 展开行编辑 (2 新 GET 端点) + 校验失败回显 + `app.js` 级联 + 后端注入组合表 (context processor 扩展)。
3. **其余页** — settings (分组卡片 + 独立 ↺ form + 中文标签) / schedule (进 nav + 排版 + confirm) / mode_preview / reseed 套样式。
4. **收尾** — week_export token 同步 + plan 微调 (双 submit) + 空态 + 测试补齐 + 全页目检。

## 不做 (YAGNI)

- 不引入前端框架/构建步骤 (保留 HTMX + Jinja)。
- 不动后端业务逻辑 / engine / DB schema。
- 不做深色模式、hamburger/折叠手势、modal、加载 spinner。
- 不做 schedule 批量编辑/拖拽/复制上周。
- 不换 mode 行内化 (保持独立确认页)。
- 不改 week_export 的自包含离线特性。
- 不自托管网络字体。
