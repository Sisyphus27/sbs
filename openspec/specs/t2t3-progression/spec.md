# t2t3-progression Specification

## Purpose
TBD - created by archiving change per-lift-t2t3-increment. Update Purpose after archive.
## Requirements
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

### Requirement: t2 reset 与 tier 切换起始重量 snap 到有效步长

t2 动作连续 miss 达 `fail` 次触发 reset 时，系统 SHALL 将重置重量 `est1rm × reset_pct` snap 到**该动作的有效步长（eff_incr）网格**，而非全局 rounding quantum。tier 切换时 `derive_state` 推导的 t2/t3 起始重量同样 SHALL snap 到 eff_incr 网格。sbs 路径不受影响（其工作重量仍 snap 到全局 rounding）。

依据：cable/器械动作（如 Pull-downs）的配片堆最小增量（如 5kg）独立于杠铃 rounding；snap 到全局 rounding 会产生该器械不可加载的重量（见 ADR 0003）。

#### Scenario: reset 重量 snap 到 eff_incr 网格

- **WHEN** 一个 t2 动作（per-lift incr=5，全局 rounding=2.5）连续 miss 达 `fail` 次（est1rm=103.3，reset_pct=0.75）
- **THEN** reset 重量 = round_weight(103.3 × 0.75, eff_incr=5) = 75（5kg 堆可加载；旧的全局 rounding 会得 77.5，非 5 倍数不可加载）

#### Scenario: incr 为 NULL 时 reset 仍 snap 到全局 incr

- **WHEN** 一个 t2 动作 incr=NULL（全局 incr=2.5、rounding=2.5）触发 reset
- **THEN** eff_incr=2.5，reset 重量 = round_weight(est1rm × reset_pct, 2.5)，与本变更前完全一致

#### Scenario: tier 切换保留 per-lift incr

- **WHEN** 一个设了 incr=5 的动作经历 tier 切换（如 t2 → t3 → sbs → t2）
- **THEN** `lifts.incr` 列始终保持 5（tier 切换只改 `lifts.tier` 与 `lift_state`，不触碰 incr 列）

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

