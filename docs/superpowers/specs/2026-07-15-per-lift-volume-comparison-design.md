---
date: 2026-07-15
status: draft
---

# Per-lift 周容量对比（实际吨位 WoW）— Design

- **Date:** 2026-07-15
- **Status:** Draft（brainstorming 产出，待用户复核）
- **Trigger:** 在本周计划页（`/`）每个动作行上，增加该动作「本周实际吨位 vs 上周实际吨位」的对比，让用户一眼看出单动作负荷的周际增减。
- **References:** [live-est1rm-preview design](./2026-06-27-live-est1rm-preview-design.md)（本设计沿其 service 模式）· [ADR 0001 — TM accumulates raw](../../adr/0001-tm-accumulates-raw.md) · [ADR 0003 — effective-step grid](../../adr/0003-t2t3-progression-snap-grid.md)

## Context

当前 `webapp/templates/plan.html`（路由 `plan.view` → `webapp/routes/plan.py::_by_day`）按天列出每个动作的 `tier | weight kg x reps x sets | ...`，并在每行末组次数框旁经 HTMX 显示 est1RM 实时预览（`webapp/services/preview.py::live_preview`）。页面上**没有任何「容量/吨位」概念**，也没有周际对比。

数据已具备，无需 schema 变更：

- `history` 表（`webapp/repo.py::append_history` / `list_history`）：每动作每周一行 `(week, weight, reps, ts)`，其中 `reps` 是该周**末组 AMRAP 实际次数**，`weight` 是该周工作重量。由 `advance_week` 在推进周时写入。
- `week_log` 表（`save_log` / `get_week_logs`）：本周尚未推进的末组次数（autosave on change）。
- `lift_state`：当前 TM / weight / target / streak / est1rm。
- `sbs_schedule`：sbs 各周 intensity / reps / repout。
- `settings.week`：当前周次。

引擎调用链已核实：`sbs_cli/program.py::week_plan` / `advance_lift` / `recompute_state`，`sbs_cli/engine/progression.py::lookup_schedule` / `round_weight`，`webapp/services/advance.py::_lift_from_row` / `_profile_from_rows`，`webapp/services/recompute.py`，`webapp/services/preview.py::_working_weight`。

## Goals / Non-Goals

**Goals**
- 每个动作行内联显示「本周实际吨位 kg + Δ%」（如 `1234kg ↗+15%`），动作对动作对比。
- 本周未填末组的动作跳过（不显示），不影响其他动作对比。
- 实际吨位 = 重量 × 总实际次数，末组按 AMRAP 实际次数计，非末组按计划次数计。
- t2 上周 target 经引擎 replay 获得，**不改引擎源码**。

**Non-Goals**
- 不做聚合总卡（全周总吨位单数字）——用户明确要动作对动作。
- 不做按 tier 拆分卡。
- 不改 export 页（`week_export.html`）。
- 不存历史快照表（用现有 `history` + replay 即可）。
- 不引入新 ADR（rep 方案假设属领域事实，文档内记录即可）。

## Terminology

| 术语 | 指 |
|------|-----|
| 实际吨位 (actual tonnage) | 单动作单周：`weight × [(sets-1) × plannedReps + amrapReps]`，单位 kg |
| plannedReps | 非末组的计划次数：sbs=schedule.reps(week)；t2=target(week)；t3=t3_target |
| amrapReps | 末组 AMRAP 实际次数：本周=week_log；上周=history.reps |
| WoW Δ% | (本周吨位 − 上周吨位) / 上周吨位 × 100 |

## 关键领域假设（rep 方案）

SBS/GZCLP 每个动作 `sets` 组中，**前 (sets-1) 组按计划次数**，**末组 AMRAP**（力竭）。`advance_lift` 只收单个 `actual_reps`（末组）佐证此结构。故：

```
actual_tonnage = weight × ((sets-1) × plannedReps + amrapReps)
```

`sets==1` 时 `(sets-1)=0`，吨位 = `weight × amrapReps`，数学成立。

## Decisions

### D1 — 度量：单动作实际吨位 kg

卡显示每动作本周实际吨位 + 上周实际吨位算出的 Δ%。不做聚合。用户澄清：「动作对动作」「未填可跳过」。

### D2 — 实际 vs 实际（非计划 vs 计划）

两周都按实际吨位（AMRAP 重建）。上周用 `history`，本周用 `week_log`。非「计划 vs 计划」——用户要的是练出来的真实负荷对比。
*备选*：计划 vs 计划（deterministic、不要 replay）。否——不反映实际力竭程度。

### D3 — 内联到现有 plan 行

在 `plan.html` 每个动作的 `.meta` span 内、est1RM 之后追加容量片段。不新建卡/区块/路由。
*备选*：顶部新卡（表）/ 单独 dashboard。否——用户选内联，就地看，零新导航。

### D4 — 格式：本周绝对 + Δ%

`{本周kg} {箭头}{符号}{Δ%}`，如 `1234kg ↗+15%` / `1073kg ↘-8%` / `980kg 首次`。复用现有 `.up`/`.down`/`.first` 配色语义（绿=增/红=减/灰=首次）。
*备选*：仅 Δ%（缺绝对值参考）/ 两绝对+Δ%（行过长）。否。

### D5 — 跳过规则

- 本周 `week_log` 无该动作末组 → `this=None` → **该行不显示容量片段**（Q3：不耽误其他动作）。
- 上周无 `history` 行（week 1，或本周新加的动作）→ `last=None` → 显示 `{本周kg} 首次`。
- 两周都无 → 不显示。

### D6 — t2 上周 target：replay 引擎，零源码改动

t2 的 `target` 随 streak 变（8→6→4 波动）。上周（week=current-1）的 target = **进入该周前**的 target = replay `history` 中 `week < current-1` 的行后的 target。

复用 `sbs_cli.program.recompute_state(lift, history, profile)`：它接受任意 history 列表，按 t2 分支从 `lift.start` replay，返回末态 `LiftState.target`。传**过滤后**的 history（`week < target_week`）即得该截点 target。镜像 `webapp/services/recompute.py::recompute_on_start_change` 现有模式（同样 `_lift_from_row` + `_profile_from_rows(settings, [], schedule)`，`lifts=[]` 安全——`recompute_state` 不迭代 `profile.lifts`，只用全局旋钮）。

```
hist = [SetEntry(...) for h in list_history(lid) if h["week"] < target_week]
if not hist: return 8                      # t2 初始 target（见 _init_lift_state / advance_lift）
lift = advance._lift_from_row(get_lift(lid))
profile = advance._profile_from_rows(settings, [], schedule)
return recompute_state(lift, hist, profile).target
```

*备选*：(a) 在 `recompute_state` 加 `through_week` 参数——否，碰引擎、放大 blast radius、动现有测试；(b) 本地手抄 t2 replay 循环——否，重复 `advance_lift` 逻辑、易漂移。

### D7 — DB-reading service，镜像 `preview.live_preview`

新增 `webapp/services/volume.py`，函数 `lift_week_volume(conn, lid, week, is_current) -> float | None` 自取 DB（lift/state/settings/schedule/history/week_log）。与 `preview.live_preview` 同风格，可经临时 SQLite DB 单测（仿 `tests/test_preview_service.py`）。route 只负责拼装 `it.wow`。

### D8 — 复用现有 helper（DRY）

- 本周工作重量：`preview._working_weight(lift, state, settings, schedule)` 直接 import，不再写第三份 sbs=round(tm×intensity) 逻辑。
- Row→dataclass：`advance._lift_from_row` / `_profile_from_rows`。
- t2 replay：`program.recompute_state`（见 D6）。

### D9 — CSS：`.up/.down/.first` 提到可复用

`base.html` 现把 `.up/.down/.first` 配色定义在 `.save-ok` 选择器下（est1RM 预览专用）。容量片段不在 `.save-ok` 内，需把这三个 class 的 color 规则提到根级（或新 `.vol` 包裹 span 复用同名 class）。最小改动：在 `base.html <style>` 增加根级 `.up{...}.down{...}.first{...}`，保留原 `.save-ok .up` 等不动（或合并）。

## 公式与数据源（每 tier × 周）

| | weight | amrapReps | plannedReps |
|---|---|---|---|
| sbs 本周 | `round_weight(tm×intensity, rounding)` | `week_log[lid]` | `lookup_schedule(schedule, kind, week).reps` |
| sbs 上周 | `history(week).weight` | `history(week).reps` | `lookup_schedule(schedule, kind, week).reps` |
| t2 本周 | `state.weight` | `week_log[lid]` | `state.target` |
| t2 上周 | `history(week).weight` | `history(week).reps` | **`_t2_target_as_of(week)`（replay）** |
| t3 本周 | `state.weight` | `week_log[lid]` | `settings.t3_target` |
| t3 上周 | `history(week).weight` | `history(reps)` | `settings.t3_target` |

吨位 = `weight × ((sets-1) × plannedReps + amrapReps)`。

## 实现触点

| 文件 | 改动 |
|------|------|
| `webapp/services/volume.py`（新）| `lift_week_volume(conn, lid, week, is_current) -> float\|None`；私有 `_t2_target_as_of(conn, lid, target_week)`；纯函数 `_actual_tonnage(weight, sets, planned_reps, amrap)` |
| `webapp/routes/plan.py` | `_by_day` 每 item 算 `it.wow = (this, delta_pct\|None)` 或 `None`（见 D5） |
| `webapp/templates/plan.html` | `.meta` 内 est1RM 后追加容量片段（条件渲染 `it.wow`） |
| `webapp/templates/base.html` | `.up/.down/.first` color 提根级（D9） |

**零改动**：引擎（`sbs_cli/*`）、`repo.py`、schema、迁移脚本。

## Edge Cases

- 本周未填末组 → 不显示（D5）。
- week 1（`settings.week==1`）→ 无上周，所有动作显示「首次」。
- 本周新加动作（上周无 history 行）→ 该动作「首次」。
- `sets==1` → 吨位 = `weight × amrap`（数学成立）。
- sbs 无对应 schedule 行 → `lookup_schedule` 抛错（既有行为，不兜底；说明 schedule 配置缺失）。
- t2 无 history 且 target_week>1（新动作首次出现在非首周）→ `hist` 过滤后为空 → 返回初始 8（正确：该动作首周 target=8）。
- 上周吨位为 0（理论上 amrap=0 且 planned=0，不会发生）→ 除零风险；`last==0` 时显示「首次」规避。

## Risks / Trade-offs

- **t2 replay 性能**：每动作上周 target 调一次 `recompute_state`，N 动作 N 次 replay。个人 app（动作个位数、历史数周），可忽略；不预优化。
- **rep 方案假设**：`(sets-1)×planned + amrap` 依赖「末组力竭、余组按计划」的 SBS 结构。若用户实际练法偏离（如多组力竭），吨位为近似。假设写明在 doc，可后续按需精化。
- **本周吨位随填入滚动**：填一个动作的末组 → 该行动态出容量片段（需 HTMX refresh 或下次整页渲染）。当前 `save_log` 的 HTMX 只更 `.save-ok`（est1RM 预览），容量片段不在其 target 内 → 填入后容量片段**下次整页加载才出现**。可接受（提交推进后必整页 redirect）；若要即时，扩展 hx-target 范围（留作可选增强，非本范围）。
- **`preview._working_weight` 为模块私有（下划线）**：跨模块 import 私有函数。本仓 `recompute.py` 已 import `advance` 私有 `_lift_from_row`，同仓约定允许；若介意可后续提升为公开。

## 测试策略

仿 `tests/test_preview_service.py`（临时 SQLite DB + fixture lifts/state/history）：

- `tests/test_volume_service.py`（新）：
  - `_actual_tonnage` 纯函数：各 tier、`sets==1`、边界。
  - `lift_week_volume` 本周：已填→吨位 / 未填→None。
  - `lift_week_volume` 上周：有 history→吨位 / 无→None。
  - `_t2_target_as_of`：replay 正确（构造 streak 变化历史，验证 target 回退到截点）/ 无历史→8。
  - sbs/t3 plannedReps 来源正确。
- `tests/test_routes_plan.py`：`it.wow` 挂载三种态（有对比 / 首次 / 跳过）。
- `tests/test_html.py` 或 plan 模板渲染：容量片段条件出现 / 不出现。

## Open Questions

无。五轮澄清已锁：度量（总吨位）/ 基准（实际 vs 实际）/ 粒度（动作对动作，跳过未填）/ 位置（内联）/ 格式（本周绝对+Δ%）。
