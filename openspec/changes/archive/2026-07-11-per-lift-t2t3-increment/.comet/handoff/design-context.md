# Comet Design Handoff

- Change: per-lift-t2t3-increment
- Phase: design
- Mode: compact
- Context hash: f070b0004347fa3951db94fa28c3e9a803f9172629b3538c8a1bf4e9c13e1cd8

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/per-lift-t2t3-increment/proposal.md

- Source: openspec/changes/per-lift-t2t3-increment/proposal.md
- Lines: 1-43
- SHA256: 4e07a785d559aa6815be247209bf72c8c541a19c4f9418fc2442e3903bf49a27

```md
## Why

t2/t3 动作目前共用全局 `incr`（默认 2.5kg）作为命中后的增长步长。但龙门架类动作（face pull、lat pull-down 等）器械配片只能 5kg 一跳，2.5kg 步长无法实际加载，需要一个 per-lift 可配置的增长幅度。

附带修正一个概念错位：t2/t3 工作重量本质是「起始重量 + N×步长」的纯等差数列，步长本身就是粒度，无需再 snap 到全局 rounding；只有 sbs（公式 `TM × intensity` 产出任意浮点）才需要 rounding 落到可加载值。

## What Changes

- lifts 表新增 `incr REAL NULL` 列：NULL = 继承全局 `settings.incr`；非 NULL = 该动作专用步长（如 face pull = 5.0）。
- t2/t3 命中加重量路径去掉 `round_weight(..., quantum)`：直接 `weight + incr` 累加。向后兼容——默认 `incr=2.5` + `rounding=2.5` 时该 snap 本就是 no-op，已有动作零行为变化；仅当 incr 非 rounding 倍数时结果才变（默认配置不触发）。
- 引擎（`advance_lift` / `recompute_state`）解析有效步长：`eff_incr = lift.incr if lift.incr is not None else profile.incr`，传入 `t2_next` / `t3_next`。
- `/lifts` 编辑器为 t2/t3 行新增 incr 输入框；sbs 行隐藏（sbs 公式驱动无固定步长）；清空 = 回到全局默认。
- 一次性 schema 迁移脚本：为已存在的 DB 执行 `ALTER TABLE lifts ADD COLUMN incr REAL`（仿 `migrate_lift_kind.py` 模式）。
- `migrate.py`：旧 profile/state 来源无 per-lift incr 字段 → 全部写 NULL（继承全局），迁移后行为不变。
- t2 reset 路径（连续 miss `fail` 次后 `est1rm × reset_pct`）保留全局 rounding snap —— 不变（est1rm 是派生浮点，需 snap 到可加载值）。

## Capabilities

### New Capabilities

- `t2t3-progression`: t2/t3 动作的递进规则——命中后按步长累加工作重量、miss 的级联/重置处理、以及步长来源（per-lift 覆盖优先，回退全局默认）。本变更首次建立该 capability 的 spec（`openspec/specs/` 此前为空）。

### Modified Capabilities

<!-- openspec/specs/ 当前为空，无既有 spec 文件可改 -->

（无）

## Impact

- **代码**：
  - `sbs_cli/data/schema.py`：`Lift` dataclass 新增 `incr: Optional[float] = None`。
  - `sbs_cli/engine/progression.py`：`t3_next` 去 rounding（移除 `quantum` 参数）；`t2_next` HIT 分支去 rounding，reset 分支保留 rounding。
  - `sbs_cli/program.py`：`advance_lift` / `recompute_state` 解析 `eff_incr` 并传入。
  - `webapp/db.py`：`_SCHEMA` lifts 加 `incr REAL` 列。
  - `webapp/repo.py`：`_LIFT_COLS` 加 incr；`create_lift` / `update_lift` 支持。
  - `webapp/services/advance.py` 与 `webapp/routes/lifts.py` 的 `_lift_from_row`：读取 incr 列。
  - `webapp/routes/lifts.py` + `templates/_lift_row.html`（+ `lifts.html` 新建表单）：incr 输入框，按 tier 条件渲染。
  - 新增 `migrate_incr.py`：一次性列迁移。
  - `migrate.py`：`create_lift` 显式传 `incr=None`。
- **数据**：DB schema 变更（加 nullable 列，向后兼容；老 DB 经迁移脚本升级）。
- **API**：无对外 API 变更（纯本地单用户 webapp）。
- **测试**：per-lift incr 单测、eff_incr 解析、recompute 用 per-lift incr 重放、迁移幂等性、t2/t3 去 rounding 行为、UI 条件渲染。

```

## openspec/changes/per-lift-t2t3-increment/design.md

- Source: openspec/changes/per-lift-t2t3-increment/design.md
- Lines: 1-95
- SHA256: d7b50459cf06d4d15e20bbe6a13a84023b237ed4d58600d8c670713b1a9b7125

[TRUNCATED]

```md
## Context

当前 t2/t3 动作的增长步长由全局 `settings.incr`（默认 2.5kg）单一决定，喂给所有 t2/t3 动作。引擎调用链：

```
settings.incr → Profile.incr → advance_lift / recompute_state
                                  → t2_next(incr=…) / t3_next(incr=…)
                                      → round_weight(weight + incr, quantum)
```

两个问题：
1. **龙门架动作无法加载 2.5kg 步长**：face pull、lat pull-down 等器械配片最小 5kg 一跳，全局 2.5kg 不适用。
2. **概念错位**：t2/t3 工作重量是「起始重量 + N×步长」的纯等差数列，步长即粒度，`round_weight(..., quantum)` 是多余 snap；只有 sbs（`TM × intensity` 产出任意浮点）才真正需要 rounding。当前对 t2/t3 也 snap，在 incr 非 rounding 倍数时会产出怪值（如 incr=3 + 50 → snap 52.5）。

`openspec/specs/` 此前为空，本变更是项目首次建立 spec，`t2t3-progression` capability 以 increment 相关需求起步，后续变更可补齐级联/阈值规则。

## Goals / Non-Goals

**Goals:**
- t2/t3 动作支持 per-lift 自定义增长步长（`lifts.incr`），解决龙门架动作 5kg 一跳需求。
- NULL = 继承全局 `settings.incr`，保证已有动作零行为变化。
- 去掉 t2/t3 命中加重量路径的 rounding snap（纯等差累加）。
- t2 reset 路径保留全局 rounding（est1rm 派生浮点需 snap）。
- 已存在的 DB 经一次性迁移平滑升级。

**Non-Goals:**
- 不把 t2 `reset_pct` / `fail` 改为 per-lift（本次只做 incr）。
- 不动 sbs 公式 / TM / schedule。
- 不改 `/settings` 全局 incr（保留作 NULL 的 fallback）。
- 不在 plan 页显示有效步长（仅 `/lifts` 编辑器可配）。
- 不补齐 t2/t3 级联/阈值规则的完整 spec（留待后续变更）。

## Decisions

### D1：per-lift incr 用 nullable 列，NULL = 继承全局

`lifts.incr REAL NULL`。NULL → 解析为 `settings.incr`；非 NULL → 该动作专用。

**为什么**：向后兼容（已有动作 NULL，行为不变）；与现有「reset-to-default」模式一致（commit 8714890）；当用户改全局 incr 时，NULL 动作自动跟随。

**备选**：存显式默认值（每个 t2/t3 写 2.5）。被否——失去 fallback 语义，改全局时老动作不跟随，且 migrate.py 要给所有行填值。

### D2：t2/t3 命中加重量去 rounding；t2 reset 保留 rounding

- `t3_next`：`weight + incr`（移除 `quantum` 参数，t3 无 reset 路径，彻底去 rounding）。
- `t2_next` HIT 分支：`weight + incr`（去 rounding）。
- `t2_next` reset 分支：`round_weight(est1rm × reset_pct, quantum)` 保留。

**为什么**：t2/t3 = 起始 + N×步长，步长即粒度，snap 多余；reset 的 `est1rm × reset_pct` 是派生浮点（如 103.3×0.75=77.48），不 snap 不可上杠。

**向后兼容验证**：默认 `incr=2.5` + `rounding=2.5` 时，`round_weight(w+2.5, 2.5)` 本就是 no-op → 去 rounding 后结果完全相同。仅当 incr 非 rounding 倍数时才变（默认配置不触发）。

**备选**：(a) 保留 rounding——否，违背龙门架 5kg 意图（5 是 2.5 倍数恰好不触发，但 incr=3 等会被错误 snap）；(b) reset 也去 rounding——否，产出不可加载的怪数。

### D3：eff_incr 在引擎边界解析，progression 保持纯函数

`advance_lift` / `recompute_state` 解析 `eff_incr = lift.incr if lift.incr is not None else profile.incr`，传入 `t2_next` / `t3_next`。

**为什么**：`t2_next` / `t3_next` 已收 `incr` 参数，签名不变（仅 t3 去 `quantum`）；解析集中在引擎入口，progression 保持纯函数、不耦合数据模型。

**备选**：把 `lift` 传进 progression。否——耦合引擎与 dataclass，破坏纯函数可测性。

### D4：一次性 `ALTER TABLE` 迁移脚本，不走 init_schema PRAGMA

新增 `migrate_incr.py`：`ALTER TABLE lifts ADD COLUMN incr REAL`，用 `PRAGMA table_info(lifts)` 守卫幂等（列已存在则跳过）。`db.py._SCHEMA` 同步加列供新 DB bootstrap。

**为什么**：沿用项目既有模式（`migrate_lift_kind.py`、`migrate_schedule.py`）；`init_schema` 只 bootstrap 空 DB，不负责在线 schema 升级。

**备选**：PRAGMA 自动迁移。否——项目约定显式迁移脚本，可审计可回滚。

### D5：UI 仅在 `/lifts` 编辑器，按 tier 条件渲染

`_lift_row.html`（编辑行）+ `lifts.html`（新建表单）为 t2/t3 加 incr number 输入框；sbs 行隐藏；清空提交 = 写 NULL = reset 默认。

**为什么**：贴合现有条件字段模式（sbs 显 lift_kind，t2/t3 显 intensity/reps/repout）；`/settings` 是全局，解决不了 per-lift。

**备选**：settings 页加 per-lift 区。否——全局页不适合 per-lift 配置。

## Risks / Trade-offs


```

Full source: openspec/changes/per-lift-t2t3-increment/design.md

## openspec/changes/per-lift-t2t3-increment/tasks.md

- Source: openspec/changes/per-lift-t2t3-increment/tasks.md
- Lines: 1-43
- SHA256: 5e6da025881fbdd0c4d37e0117c379d0fe6039b13ceb58e4b3e8d0d7c86370d8

```md
# Tasks — per-lift-t2t3-increment

实现 t2/t3 per-lift 增长步长。引擎层走 TDD（先红后绿）。命令在 `D:\WorkSpace\sbs\` 下用 `conda run -n sbs` 跑。

## 1. Engine: progression 纯函数（TDD）

- [ ] 1.1 写 `t3_next` 去 rounding 测试：命中精确累加（20+5=25）、非 rounding 倍数不 snap（50+3=53）、默认配置 no-op（50+2.5=52.5）；改 `sbs_cli/engine/progression.py` 的 `t3_next` 移除 `quantum` 参数与 `round_weight`，直接 `weight + incr`
- [ ] 1.2 写 `t2_next` 测试：HIT 分支精确累加（去 rounding）、reset 分支仍 `round_weight(est1rm×reset_pct, quantum)`；改 `t2_next` 仅 HIT 分支去 `round_weight`，reset 分支与签名保留 `quantum`
- [ ] 1.3 `sbs_cli/data/schema.py` 的 `Lift` dataclass 加 `incr: Optional[float] = None`

## 2. Engine: 有效步长解析（TDD）

- [ ] 2.1 写 `advance_lift` eff_incr 测试：per-lift incr 优先（t2/t3 用 lift.incr）、NULL 回退 `profile.incr`、sbs 路径不沾 incr；改 `sbs_cli/program.py` 的 `advance_lift` 解析 `eff_incr = lift.incr if lift.incr is not None else profile.incr` 并传入 t2/t3 分支
- [ ] 2.2 写 `recompute_state` eff_incr 测试：t2/t3 重放历史按 per-lift 步长累加；改 `recompute_state` 用同一 eff_incr 解析传入

## 3. DB schema + repo

- [ ] 3.1 `webapp/db.py` 的 `_SCHEMA` lifts 表加 `incr REAL` 列
- [ ] 3.2 `webapp/repo.py`：`_LIFT_COLS` 加 `incr`；`create_lift` 加 `incr=None` 参数与 INSERT 列；`update_lift` 经 `_LIFT_COLS` 自动支持
- [ ] 3.3 写 repo incr 读写测试：create 带 incr、update 改 incr、NULL 读写往返、`_LIFT_COLS` 校验拒绝未知列

## 4. Webapp 服务/路由接线

- [ ] 4.1 `webapp/services/advance.py` 的 `_lift_from_row` 读 `incr` 列传入 `Lift`
- [ ] 4.2 `webapp/routes/lifts.py`：`_lift_from_row`（new/edit 共用逻辑若有）读 incr；`new`/`edit` 路由接收 `incr` 字段；sbs 创建时传 `incr=None`
- [ ] 4.3 写 webapp 集成测试：t2/t3 创建带 incr、编辑改 incr、清空写回 NULL、sbs 不写 incr

## 5. UI 模板

- [ ] 5.1 `webapp/templates/_lift_row.html` 编辑行：t2/t3 加 incr number 输入框（值=`lift.incr`），sbs 行隐藏（仿 intensity/reps/repout 条件模式）
- [ ] 5.2 `webapp/templates/lifts.html` 新建表单：t2/t3 加 incr 输入框，sbs 隐藏
- [ ] 5.3 incr 服务端校验：≤0 或非数字 → flash + 保留原值（路由层）

## 6. 迁移

- [ ] 6.1 新增 `migrate_incr.py`：`ALTER TABLE lifts ADD COLUMN incr REAL`，用 `PRAGMA table_info(lifts)` 守卫幂等（列已存在则跳过）；CLI `--db` 参数
- [ ] 6.2 写迁移幂等测试：空 DB、已升级 DB（重复跑无错）、有数据 DB（现有行 incr 保持 NULL）
- [ ] 6.3 `migrate.py`：`create_lift` 调用显式传 `incr=None`（老 YAML/xlsx 来源无此字段）

## 7. 验收

- [ ] 7.1 全量测试：`conda run -n sbs python -m pytest`，全绿
- [ ] 7.2 手动验证：face pull 设 incr=5 命中后 +5；其他 t2/t3 NULL 动作仍 +2.5；sbs 行无 incr 框；清空 incr 回全局；reseed/schedule 等既有流程不回归

```

## openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md

- Source: openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md
- Lines: 1-76
- SHA256: 35b5dee19ef65a553c0ac9508fc63f7a959a6666300bf15fa0df47dba9f95c9f

```md
## ADDED Requirements

### Requirement: Per-lift increment override with global fallback

t2/t3 动作 SHALL 支持一个可选的 per-lift 增长步长（`lifts.incr`）。当该值被设置（非 NULL）时，系统 MUST 用它作为该动作命中后的增长步长；当该值为 NULL 时，系统 MUST 回退到全局 `settings.incr`。此「有效步长」（effective increment）解析 SHALL 在引擎入口（`advance_lift` 与 `recompute_state`）统一完成。

#### Scenario: per-lift incr 命中后按专用步长增长

- **WHEN** 一个 t2/t3 动作的 `incr=5.0` 且本周命中目标次数
- **THEN** 下次工作重量 = 当前重量 + 5.0

#### Scenario: incr 为 NULL 时回退全局

- **WHEN** 一个 t2/t3 动作的 `incr=NULL`（全局 `settings.incr=2.5`）且本周命中目标次数
- **THEN** 下次工作重量 = 当前重量 + 2.5

#### Scenario: 清空 incr 回到全局

- **WHEN** 用户把一个先前设为 5.0 的动作的 incr 字段清空并提交
- **THEN** 该动作写回 NULL，下次命中按全局 incr 增长

#### Scenario: 非法 incr 被拒绝

- **WHEN** 用户提交 incr ≤ 0 或非数字
- **THEN** 系统拒绝该输入，保留该动作原值不变

### Requirement: t2/t3 命中加重量不做 rounding

t2/t3 动作命中后累加有效步长时，系统 SHALL 直接 `weight + effective_increment`，MUST NOT 对该累加结果做 rounding-quantum snap。sbs 路径（`round_weight(TM × intensity, rounding)`）不受影响。

#### Scenario: t3 命中按步长精确累加

- **WHEN** 一个 t3 动作（有效步长 5.0，当前重量 20）命中目标次数
- **THEN** 下次重量 = 25（精确，无 snap）

#### Scenario: 非 rounding 倍数的步长不被 snap

- **WHEN** 一个 t3 动作（有效步长 3.0，当前重量 50，全局 rounding=2.5）命中目标次数
- **THEN** 下次重量 = 53（不 snap 到 52.5）

#### Scenario: 默认配置下与旧行为一致

- **WHEN** 一个 t3 动作（incr=NULL，全局 incr=2.5、rounding=2.5，当前重量 50）命中目标次数
- **THEN** 下次重量 = 52.5（与本变更前完全一致）

### Requirement: t2 reset 保留全局 rounding

t2 动作连续 miss 达 `fail` 次触发 reset 时，系统 SHALL 将重置重量 `est1rm × reset_pct` snap 到全局 rounding quantum。per-lift incr 不参与 reset 路径。

#### Scenario: reset 重量 snap 到全局 rounding

- **WHEN** 一个 t2 动作连续 miss 达 `fail` 次（est1rm=103.3，reset_pct=0.75，全局 rounding=2.5）
- **THEN** reset 重量 = round_weight(103.3 × 0.75, 2.5) = 77.5

### Requirement: 重算历史使用有效步长

当 t2/t3 动作的起始重量（start）被编辑触发历史重放时，系统 SHALL 使用该动作的有效步长（per-lift 优先，回退全局）重放每一次命中累加。

#### Scenario: 重放按 per-lift 步长累加

- **WHEN** 一个 t2/t3 动作（incr=5.0）的 start 被编辑，系统重放其历史
- **THEN** 重放中每一次命中累加均 +5.0，最终工作重量反映该步长

### Requirement: incr 字段仅适用于 t2/t3

per-lift incr 字段 SHALL 只对 t2/t3 动作生效。sbs 动作（公式驱动 `TM × intensity`）MUST 忽略 incr 字段，其工作重量不受 incr 影响。UI MUST 对 sbs 动作隐藏 incr 输入框。

#### Scenario: sbs 动作忽略 incr

- **WHEN** 一个 sbs 动作被设置了任意 incr 值
- **THEN** 其工作重量仍为 `round_weight(TM × intensity, rounding)`，incr 无任何效果

#### Scenario: UI 对 sbs 隐藏 incr 框

- **WHEN** 用户在 `/lifts` 编辑器查看一个 sbs 动作行
- **THEN** 该行不显示 incr 输入框（仅 t2/t3 行显示）

```
