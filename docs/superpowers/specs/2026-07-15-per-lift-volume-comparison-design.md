---
date: 2026-07-15
status: revised
---

# Per-lift 周容量对比（实际吨位 WoW）— Design

- **Date:** 2026-07-15
- **Status:** Revised 2026-07-15 after grilling session（四项决策折入，见「Grilling outcomes」）
- **Trigger:** 在本周计划页（`/`）每个动作行上，增加该动作「本周实际吨位 vs 上周实际吨位」的对比，让用户一眼看出单动作负荷的周际增减。
- **References:** [live-est1rm-preview design](./2026-06-27-live-est1rm-preview-design.md)（本设计沿其 service 模式与即时预览模式）· [ADR 0001 — TM accumulates raw](../../adr/0001-tm-accumulates-raw.md) · [ADR 0003 — effective-step grid](../../adr/0003-t2t3-progression-snap-grid.md) · [CONTEXT.md — tonnage / lift](../../../CONTEXT.md)

## Context

当前 `webapp/templates/plan.html`（路由 `plan.view` → `webapp/routes/plan.py::_by_day`）按天列出每个动作的 `tier | weight kg x reps x sets | ...`，并在每行末组次数框旁经 HTMX 显示 est1RM 实时预览（`webapp/services/preview.py::live_preview`）。页面上**没有任何「容量/吨位」概念**，也没有周际对比。

数据已具备，无需 schema 变更：

- `history` 表（`webapp/repo.py::append_history` / `list_history`）：每动作每周一行 `(week, weight, reps, ts)`，其中 `reps` 是该周**末组实际次数**（输入框填入值），`weight` 是该周工作重量。由 `advance_week` 在推进周时写入。
- `week_log` 表（`save_log` / `get_week_logs`）：本周尚未推进的末组次数（autosave on change）。
- `lift_state`：当前 TM / weight / target / streak / est1rm。
- `sbs_schedule`：sbs 各周 intensity / reps / repout。
- `settings.week`：当前周次。

引擎调用链已核实：`sbs_cli/program.py::week_plan` / `advance_lift` / `recompute_state`，`sbs_cli/engine/progression.py::lookup_schedule` / `round_weight`，`webapp/services/advance.py::_lift_from_row` / `_profile_from_rows`，`webapp/services/recompute.py`，`webapp/services/preview.py::_working_weight`。`recompute_state` 只用 `profile` 的全局旋钮（`incr`/`t2_fail`/`t2_reset_pct`/`t3_target`），**不迭代 `profile.lifts`**——故传 `lifts=[]` 安全（镜像 `recompute.py::recompute_on_start_change` 现有用法）。

## Goals / Non-Goals

**Goals**
- 每个动作行内联显示「本周实际吨位 kg + Δ%」（如 `1234kg ↗+15%`），动作对动作（per lift-row）对比。
- 本周未填末组的动作跳过（不显示），不影响其他动作对比。
- 实际吨位 = 重量 × 总实际次数；末组用填入的实际次数，非末组按计划次数。
- 填末组即时更新（与 est1RM 预览一致的 HTMX 行为）；初始加载服务端预渲染已填动作。
- t2 上周 target 经引擎 replay 获得，**不改引擎源码**。

**Non-Goals**
- 不做聚合总卡（全周总吨位单数字）——用户明确要动作对动作。
- 不做按 tier 拆分卡。
- 不改 export 页（`week_export.html`）。
- 不存历史快照表（用现有 `history` + replay 即可）。
- 不引入新 ADR（四决策均可逆、不意外、非硬 trade-off；rep 方案假设属领域事实，doc 内记够）。

## Terminology（见 CONTEXT.md）

| 术语 | 指 |
|------|-----|
| 实际吨位 (actual tonnage) | 单动作单周：`weight × ((sets-1) × plannedReps + lastSetReps)`，单位 kg |
| plannedReps | 非末组的计划次数：sbs=schedule.reps(week)；t2=target(week)；t3=t3_target |
| lastSetReps | 末组填入的实际次数（就是输入框值，**不作 AMRAP/非 AMRAP 分类**）：本周=week_log；上周=history.reps |
| WoW Δ% | (本周吨位 − 上周吨位) / 上周吨位 × 100 |

## 关键领域假设（rep 方案）

每个动作 `sets` 组中，**前 (sets-1) 组按计划次数**（sbs=scheduled reps；t2=target；t3=t3_target），**末组用填入的实际次数**（输入框值——sbs/t3 通常 ≥ 目标属力竭型，t2 经典 GZCLP 到 target 即停，但公式不关心分类，直接消费填入值）。故：

```
actual_tonnage = weight × ((sets-1) × plannedReps + lastSetReps)
```

`sets==1` 时 `(sets-1)=0`，吨位 = `weight × lastSetReps`，数学成立。

> 限制：引擎只存末组 actual，不逐组记录。若非末组提前力竭/欠组，吨位为近似（高估）。inherent，接受。

## Grilling outcomes（四项决策）

1. **对比单位 = per lift-row**（非按动作名合并）。同名动作排在两天（如 Face Pull D2+D4）= 两个 `lift_id`、两份 history → 各自独立 WoW。与 DB/advance/filling 全按 `lift_id` 一致。CONTEXT.md 加 `Lift` 条目明确「行实例」语义。
2. **Δ 配色 = 绿增/红减**，复用现有 `.up`/`.down`。接受 sbs 减载周（schedule week 7/14/21）吨位掉而显假性红的代价（与 est1RM 预览配色一致，用户接受）。
3. **更新时机 = 填末组即时更新**。`save_log` HTMX 响应扩展含 tonnage；初始加载（`_by_day`）服务端预渲染已填动作的片段（否则刷新后丢显示）。不延后到提交。
4. **末组语义 = 填入次数**。不作 AMRAP 分类，三 tier 统一公式。术语 `lastSetReps` 取代原 `amrapReps`。

## Decisions

### D1 — 度量：单动作实际吨位 kg

卡显示每动作本周实际吨位 + 上周实际吨位算出的 Δ%。不做聚合。

### D2 — 实际 vs 实际

两周都按实际吨位。上周用 `history`，本周用 `week_log`。非「计划 vs 计划」——用户要练出来的真实负荷。

### D3 — 内联到现有 plan 行，活在 HTMX 区

片段放在末组输入框旁的 HTMX 目标区（`.save-ok` 或包裹之的 wrapper），使其随 `save_log` 响应即时刷新。初始加载由 `_by_day` 服务端预渲染同一片段（从 `week_log`）。不新建卡/区块/路由。

### D4 — 格式与配色

`{本周kg} {箭头}{符号}{Δ%}`：`1234kg ↗+15%` / `1073kg ↘-8%` / `980kg 首次`。
- 吨位：int kg 无小数。
- Δ%：带符号 int % + 箭头（↗=增 / ↘=减）。
- 配色：增=绿（`.up`）/ 减=红（`.down`）/ 首次=灰（`.first`）。

### D5 — 跳过与首次规则

- 本周 `week_log` 无该动作末组 → `this=None` → **该行不显示片段**。
- 上周无 `history` 行（week 1，或本周新加的动作）→ `last=None` → 显示 `{本周kg} 首次`。
- 两周都无 → 不显示。

### D6 — t2 上周 target：replay 引擎，零源码改动

t2 的 `target` 随 streak 变（8→6→4 波动）。上周（week=current-1）的 target = **进入该周前**的 target = replay `history` 中 `week < current-1` 的行后的 target。

复用 `sbs_cli.program.recompute_state(lift, history, profile)`：传**过滤后**的 history（`week < target_week`）即得该截点 target。

```
hist = [SetEntry(...) for h in list_history(lid) if h["week"] < target_week]
if not hist: return 8                      # t2 初始 target（见 _init_lift_state / advance_lift）
lift = advance._lift_from_row(get_lift(lid))
profile = advance._profile_from_rows(settings, [], schedule)
return recompute_state(lift, hist, profile).target
```

*备选*：(a) 在 `recompute_state` 加 `through_week` 参数——否，碰引擎、放大 blast radius、动现有测试；(b) 本地手抄 t2 replay 循环——否，重复 `advance_lift` 逻辑、易漂移。

### D7 — DB-reading service，镜像 `preview.live_preview`

新增 `webapp/services/volume.py`，函数 `lift_week_volume(conn, lid, week, is_current) -> float | None` 自取 DB（lift/state/settings/schedule/history/week_log）。与 `preview.live_preview` 同风格，可经临时 SQLite DB 单测（仿 `tests/test_preview_service.py`）。route/save_log 只负责拼装渲染数据。

### D8 — 复用现有 helper（DRY）

- 本周工作重量：`preview._working_weight(lift, state, settings, schedule)` 直接 import。
- Row→dataclass：`advance._lift_from_row` / `_profile_from_rows`。
- t2 replay：`program.recompute_state`（见 D6）。

### D9 — CSS：`.up/.down/.first` 提到可复用

`base.html` 现把三配色定义在 `.save-ok` 选择器下。容量片段所在区域需用同色，故把 color 规则提到根级（保留原 `.save-ok .up` 等不动，或合并）。

## 公式与数据源（每 tier × 周）

| | weight | lastSetReps | plannedReps |
|---|---|---|---|
| sbs 本周 | `round_weight(tm×intensity, rounding)` | `week_log[lid]` | `lookup_schedule(schedule, kind, week).reps` |
| sbs 上周 | `history(week).weight` | `history(week).reps` | `lookup_schedule(schedule, kind, week).reps` |
| t2 本周 | `state.weight` | `week_log[lid]` | `state.target` |
| t2 上周 | `history(week).weight` | `history(week).reps` | **`_t2_target_as_of(week)`（replay）** |
| t3 本周 | `state.weight` | `week_log[lid]` | `settings.t3_target` |
| t3 上周 | `history(week).weight` | `history(week).reps` | `settings.t3_target` |

吨位 = `weight × ((sets-1) × plannedReps + lastSetReps)`。

## 实现触点

| 文件 | 改动 |
|------|------|
| `webapp/services/volume.py`（新）| `lift_week_volume(conn, lid, week, is_current) -> float\|None`；私有 `_t2_target_as_of(conn, lid, target_week)`；纯函数 `_actual_tonnage(weight, sets, planned_reps, last_set_reps)` |
| `webapp/routes/plan.py::_by_day` | 每 item 算 `it.wow = (this, delta_pct\|None)` 或 `None`（D5）；服务端预渲染片段供初始加载 |
| `webapp/routes/plan.py::save_log` | 响应 HTML 扩展：est1RM 预览之后追加容量片段（重算 `this`+`last`），同一 HTMX 目标区即时刷新 |
| `webapp/templates/plan.html` | 末组输入旁的 HTMX 目标区内放容量片段（条件渲染 `it.wow`）；初始加载由 `_by_day` 预填 |
| `webapp/templates/base.html` | `.up/.down/.first` color 提根级（D9） |

**零改动**：引擎（`sbs_cli/*`）、`repo.py`、schema、迁移脚本。

## Edge Cases

- 本周未填末组 → 不显示（D5）。
- week 1（`settings.week==1`）→ 无上周，动作显示「首次」。
- 本周新加动作（上周无 history 行）→ 该动作「首次」。
- `sets==1` → 吨位 = `weight × lastSetReps`（数学成立）。
- sbs 无对应 schedule 行 → `lookup_schedule` 抛 `KeyError`（既有行为，不兜底）。
- t2 无 history 且 target_week>1（新动作首次出现在非首周）→ `hist` 过滤后空 → 返回初始 8。
- 上周吨位为 0 → 除零；`last==0` 按「首次」处理规避。
- **tier 中途切换的 lift**：history 不存 tier 戳，last-week 用当前 tier 公式。若上周 tier ≠ 本周，吨位失真。罕见，接受（见 Risks）。

## Risks / Trade-offs

- **sbs 减载周假性红**：schedule week 7/14/21 强度掉 → 吨位掉 → 显红。属计划性恢复非变差。接受（grilling 决策 2），与 est1RM 配色一致的代价。
- **tier 切换 lift 失真**：history 无 tier 戳，切 tier 后上周吨位按当前 tier 算。罕见（CONTEXT.md「tier 可切换」），记为已知限制；检测需 history 加 tier 列，出范围。
- **非末组欠组近似**：引擎只存末组 actual，吨位假设余组按计划。实际欠组则高估。inherent。
- **t2 replay 性能**：每动作上周 target 调一次 `recompute_state`，N 动作 N 次 replay。`save_log` 每次按键也会触发（即时更新）。个人 app（动作个位数、历史数周），可忽略；不预优化。
- **`preview._working_weight` 为模块私有**：跨模块 import 私有函数。本仓 `recompute.py` 已 import `advance` 私有 `_lift_from_row`，同仓约定允许。
- **save_log 响应体积**：HTMX 响应从「est1RM 一行」扩到含容量片段，行略长。手机端 plan 页可接受（export 页出范围）。

## 测试策略

仿 `tests/test_preview_service.py`（临时 SQLite DB + fixture lift/state/history）：

- `tests/test_volume_service.py`（新）：
  - `_actual_tonnage` 纯函数：各 tier、`sets==1`、边界。
  - `lift_week_volume` 本周：已填→吨位 / 未填→None。
  - `lift_week_volume` 上周：有 history→吨位 / 无→None。
  - `_t2_target_as_of`：replay 正确（构造 streak 变化历史，验证 target 回退到截点）/ 无历史→8。
  - sbs/t3 plannedReps 来源正确。
- `tests/test_routes_plan.py`：`it.wow` 三态（对比 / 首次 / 跳过）；`save_log` 响应含容量片段。
- `tests/test_html.py` 或 plan 模板渲染：片段条件出现 / 不出现；初始预渲染。

## Open Questions

无。五轮澄清 + 四轮 grilling 已锁全部决策。
