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
