---
comet_change: per-lift-t2t3-increment
role: technical-design
canonical_spec: openspec
---

# Per-lift T2/T3 Progression Step — Design

- **Date:** 2026-07-10
- **Status:** Revised 2026-07-10 after grilling session (three findings folded in; see "Grilling outcomes")
- **Trigger:** 龙门架类动作（Face Pull、Pull-downs）器械配片只能 5kg 一跳，全局 `incr=2.5` 无法加载；需要一个 per-lift 可配置的 t2/t3 递进步长。
- **References:** [ADR 0003 — T2/T3 snap to effective-step grid](../../adr/0003-t2t3-progression-snap-grid.md)（build 阶段创建）· [ADR 0001 — TM accumulates raw](../../adr/0001-tm-accumulates-raw.md) · [CONTEXT.md — glossary](../../../CONTEXT.md) · [OpenSpec change](../../../openspec/changes/per-lift-t2t3-increment/proposal.md)

## Context

当前 t2/t3 动作的增长步长由全局 `settings.incr`（默认 2.5kg）单一决定，喂给所有 t2/t3：

```
settings.incr → Profile.incr → advance_lift / recompute_state
                                  → t2_next(incr=…) / t3_next(incr=…)
                                      → round_weight(weight + incr, quantum)
```

引擎调用链已读（`sbs_cli/engine/progression.py`、`sbs_cli/program.py`、`webapp/services/advance.py`、`webapp/services/recompute.py`、`webapp/services/tier.py`、`webapp/repo.py`、`webapp/db.py`、`webapp/routes/lifts.py`、`templates/_lift_row.html`）。`t2_next`/`t3_next` 已是收 `incr`/`quantum` 参数的纯函数；`Profile.incr`/`Profile.rounding` 是全局旋钮；lifts 表无 per-lift incr 列。

## Goals / Non-Goals

**Goals**
- t2/t3 支持 per-lift 递进步长（progression step），解 cable 动作 5kg 一跳。
- NULL = 继承全局 `settings.incr`（live inheritance），已有动作零行为变化。
- t2/t3 命中加重量走纯等差，不 snap；reset 与 tier-switch 起始推导 snap 到该动作的 effective-step 网格。
- sbs 不变。

**Non-Goals**
- 不改 t2 `reset_pct`/`fail` 全局化；不动 sbs 公式/TM/schedule。
- 不改 `/settings` 全局 incr（留作 NULL fallback）；不加 plan 页显示。
- 不 rename/split 全局 `rounding` 设置（行为收窄到 sbs，配置保持）。
- 不补齐 t2/t3 级联/阈值的完整 spec（留待后续变更）。

## Terminology（规范术语，build 阶段写入 CONTEXT.md）

| 规范术语 | 中文 | 指 |
|---------|------|-----|
| rounding quantum | 配片粒度 | 权铃片 snap 网格；**行为上仅 sbs** 用 |
| progression step | 递进步长 | t2/t3 命中后的 +Δ；全局默认 `settings.incr`，per-lift 覆盖 `lifts.incr` |
| effective step (eff_incr) | 有效步长 | 解析后实际步长 = per-lift ?? 全局；也是 t2/t3 的 snap 网格 |

## Grilling outcomes（三轮设计改进）

1. **词汇表冲突**：D2 去 rounding 撞 CONTEXT.md「loaded weight always rounded」。判定词汇表偏杠铃语境——cable/器械步长是机器属性，独立于杠铃配片。D2 正确 → 改 CONTEXT.md + 写 ADR 0003。
2. **reset 网格**：Pull-downs 是 T2+cable，reset 选项「snap 全局 rounding」出 52.5（非 5 倍数，5kg 堆不可加载）。改 reset + derive_state 起始重量 snap 到 **eff_incr 网格**。每动作一个 snap 网格。
3. **术语碰撞**：increment 一词三用。三分 progression step / effective step / rounding quantum。

## Decisions

### D1 — per-lift incr 用 nullable 列，NULL 继承全局（live）

`lifts.incr REAL NULL`。eff_incr = `lift.incr if lift.incr is not None else profile.incr`。NULL = 跟随全局，改全局时 NULL 动作自动跟随（每次 advance 重读）。用户要固定值就显式设。
*备选*：存显式默认 2.5。否——失去 fallback，改全局时老动作不跟随，migrate 要填值。

### D2 —（经 grill 精炼）每动作一个 snap 网格

- t2/t3 命中加重量：`weight + eff_incr`，**无 snap**（自量化等差）。
- t2 reset（`est1rm × reset_pct`）+ derive_state 起始推导：snap 到 **eff_incr 网格** `round_weight(·, eff_incr)`。
- sbs：`round_weight(TM × intensity, rounding)` 不变。
- *向后兼容*：默认 incr=2.5=rounding → eff_incr=2.5 → add-path snap 本是 no-op、reset 网格本就是 2.5 → 全部结果与现在相同。仅 incr≠rounding 时变（新功能域）。
- *备选*：(a) reset 仍 snap 全局 rounding——否，cable T2（Pull-downs）reset 出非 5 倍数不可加载；(a′) incr 强制 rounding 倍数——否，把机器步长耦合到杠铃配片，正是要修的类别错误。

### D3 — eff_incr 在引擎入口解析，progression 保持纯函数

`advance_lift` / `recompute_state` / `derive_state` 各自解析 eff_incr 并传入。`t2_next` 仍收 `quantum` 参数（reset 分支用，调用方传 eff_incr）；`t3_next` 去 `quantum` 参数（无 reset，全去 snap）。recompute 路径经 `_lift_from_row`（接入 incr）+ `recompute_state`（解析 eff_incr）自动继承，零额外管道。
*备选*：把 lift 传进 progression。否——耦合引擎与 dataclass，破坏纯函数可测性。

### D4 — 一次性 ALTER 迁移脚本 + init_schema bootstrap

新增 `migrate_incr.py`：`ALTER TABLE lifts ADD COLUMN incr REAL`，`PRAGMA table_info(lifts)` 守卫幂等（列已存在跳过）。`db.py._SCHEMA` 同步加列供新 DB。沿用 `migrate_lift_kind.py`/`migrate_schedule.py` 模式。
*备选*：PRAGMA 自动迁移。否——项目约定显式迁移脚本，可审计可回滚。

### D5 — 仅 `/lifts` 编辑器条件渲染

`_lift_row.html`（编辑行）+ `lifts.html`（新建表单）为 t2/t3 加 incr number 框，sbs 隐藏，清空=NULL=reset 默认。`/settings` 是全局，解决不了 per-lift。

### D6 — tier 切换始终保留 incr

`derive_state`/`apply_switch` 不加特例。incr 是动作属性（同 `start`/`max`，按 tier 消费）；sbs 忽略、t2/t3 共用，切回时原值仍在。

### D7 — incr 校验

`> 0` 数值；无上限；无 rounding 倍数约束（D2）。非法（≤0 / 非数字）路由层 flash + 保留原值。

## 实现触点（已逐一核实）

| 文件 | 改动 |
|------|------|
| `sbs_cli/engine/progression.py` | `t3_next` 去 `quantum` 参数与 `round_weight` → `weight+incr`；`t2_next` HIT 分支去 `round_weight`（reset 分支保留 `round_weight(est1rm×reset_pct, quantum)`，quantum 由调用方传 eff_incr） |
| `sbs_cli/data/schema.py` | `Lift.incr: Optional[float] = None` |
| `sbs_cli/program.py` | `advance_lift`/`recompute_state` 解析 eff_incr；t2 分支传 eff_incr 作 incr 与 reset 的 quantum |
| `webapp/db.py` | `_SCHEMA` lifts 加 `incr REAL` |
| `webapp/repo.py` | `_LIFT_COLS` 加 incr；`create_lift` 加 `incr=None` |
| `webapp/services/advance.py` | `_lift_from_row` 读 incr |
| `webapp/services/recompute.py` | 零改动（经 `_lift_from_row`+`recompute_state` 自动继承） |
| `webapp/services/tier.py` | `derive_state` t2/t3 起始重量 snap 网格 rounding → eff_incr；apply_switch 不动（保留 incr） |
| `webapp/routes/lifts.py` | new/edit 接 incr 字段；sbs 传 None；≤0/非数字校验 |
| `templates/_lift_row.html` + `lifts.html` | t2/t3 加 incr 框，sbs 隐藏 |
| `migrate_incr.py`（新）| ALTER + PRAGMA 幂等 |
| `migrate.py` | create_lift 传 incr=None |
| `CONTEXT.md`（build）| 改 rounding quantum + loaded-value 定义；加 progression step / effective step 术语 |
| `docs/adr/0003-t2t3-progression-snap-grid.md`（build）| 新建 ADR（推理见下「ADR 0003 草案」） |

## ADR 0003 草案（build 阶段落盘到 docs/adr/）

**Context**: ADR 0001 说 rounding 管「所有 loaded weight 含 T2/T3 increments and resets」——偏杠铃语境。cable/器械附件的步长是机器属性（5kg 堆），独立于杠铃配片。per-lift incr 暴露该错配：cable 动作步长不是杠铃 rounding 的函数。

**Decision**: (1) t2/t3 命中加重量不 snap，纯等差；(2) t2 reset + tier-switch 起始推导 snap 到 effective-step 网格（非全局 rounding）；(3) rounding quantum 行为收窄到 sbs；(4) effective_step = per-lift incr ?? 全局 incr，既是 add-step Δ 也是该动作派生重量的 snap 网格。

**Why**: 每个动作由自己的器械加载，有自己的最小增量。cable 动作 snap 到杠铃网格出非可加载值——与 rounding 的目的（保可加载）相反。

**Considered**: B（选中，每动作一个网格，默认兼容）/ A（保全局 rounding，cable reset 不可加载）/ A′（incr 强制 rounding 倍数，耦合机器与杠铃）/ C（reset 不 snap，est1rm 派生浮点不可加载）。

**Consequences**: rounding 行为上变 sbs-only（配置仍全局，rename 出范围）；每 t2/t3 动作一个 snap 网格；默认 incr=rounding=2.5 完全向后兼容；ADR 0001 的「T2/T3 increments and resets」措辞对本变更的 T2/T3 部分被 ADR 0003 取代（0001 仍权威于 TM + sbs loaded weight）。

## Risks / Trade-offs

- **去 rounding 默认 no-op** → 仅 incr≠rounding 触发，默认配置零变化。
- **reset/derive 改 eff_incr 网格** → 默认 eff_incr=2.5=rounding，结果不变；仅 incr≠rounding 变（新域）。
- **recompute 用当前 eff_incr 重放整段历史** → 既有假设（recompute 全程用当前配置），非本变更范围；与现状一致。
- **test_columns.py 须同步加 incr** → 否则红。
- **迁移重复执行** → PRAGMA table_info 守卫幂等。
- **rounding 行为收窄** → 老用户若曾依赖 t2/t3 snap 到 rounding 的边角（incr 非 rounding 倍数），行为变；默认配置不触发，ADR 0003 记录。

## Migration Plan

1. 部署代码（schema 加列 + 引擎 + UI + CONTEXT.md + ADR 0003）。
2. 已存在 `sbs.db` 跑 `python migrate_incr.py`：加 nullable incr 列，全行 NULL（继承全局）。
3. 新 DB 由 init_schema 直接建列。
4. **回滚**：列未被老代码读取即无害；去 rounding 与 reset 网格变更是行为变更，不可仅靠 schema 回滚，须连代码回退。

## 测试策略

9 落点（项目已有完整 tests/）：
- `test_progression.py`：t3_next 去 snap（精确累加 / 非倍数不 snap / 默认 no-op）；t2_next HIT 去 snap + reset snap eff_incr（est1rm=70,eff_incr=5→50 非 52.5）。
- `test_program.py`：advance_lift/recompute_state eff_incr 解析（per-lift 优先 / NULL 回退 / sbs 不沾）。
- `test_repo.py`：incr 读写往返 / NULL 读写 / `_LIFT_COLS` 未知列拒绝。
- `test_columns.py`：lifts 列集合加 incr。
- `test_routes_lifts.py`：创建/编辑带 incr / 清空回 NULL / sbs 不写 / 非法值拒绝。
- `test_tier_service.py`：tier 切换保留 incr；derive_state 起始重量 snap eff_incr。
- `test_recompute_service.py`：重放按 eff_incr。
- `test_advance_service.py`：advance_week incr 接线。
- 新 `test_migrate_incr.py`：幂等（空 / 已升级 / 有数据）。

## Spec Patch（build task 0 回写）

> 注：design handoff 在 grilling 前生成，hash 锁定了 open 阶段的 spec.md/tasks.md 内容。comet 工具不支持 handoff 后重生成（stale guard 无 force），故 spec/tasks 精炼**推迟到 build task 0** 先回写再实现。下方即 build task 0 要回写到 `openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md` 的变更：

1. **MODIFIED**「t2 reset」requirement：snap 网格 rounding → effective step；场景例子改（est1rm=70, eff_incr=5 → reset 50）。
2. **ADDED scenario**「tier 切换保留 incr」。
3. derive_state 起始重量 snap eff_incr 纳入 reset requirement 的场景描述。

## Open Questions

无。三轮 grill 已resolve：rounding 本体论（#1→a）、reset 网格（#2→b）、术语（#3→a）。tier 切换 incr 保留（D6）、incr 校验（D7）、NULL live inheritance（D1）均已确认。
