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

- **[去 rounding 改变非默认配置行为]** → 仅当全局 incr 曾被设为非 rounding 倍数时触发（非常规配置）；默认 2.5/2.5 完全 no-op。缓解：迁移脚本输出提示 + design 记录。
- **[迁移脚本对已升级 DB 重复执行]** → `PRAGMA table_info` 守卫，列已存在则跳过，幂等。
- **[recompute 路径漏解析 eff_incr 导致重放错误]** → 单一解析点（D3），recompute_state 与 advance_lift 共用同一解析逻辑；单测覆盖 recompute 用 per-lift incr 重放。
- **[t2 reset 落 2.5 网格后按 per-lift incr 爬，网格不一致]** → 可接受：reset 是失败兜底、罕见；落 2.5 网格可加载，之后按 per-lift incr（多为 5，仍是 2.5 倍数）爬，保持可加载。若未来需 reset 落 incr 网格，另开变更。

## Migration Plan

1. 部署代码（schema 加列 + 引擎 + UI）。
2. 已存在的 `sbs.db` 跑 `python migrate_incr.py`：加 nullable `incr` 列，所有行 NULL（继承全局）。
3. 新 DB 由 `init_schema` 直接建列。
4. **回滚**：列未被老代码读取即无害；老代码忽略多余列，无数据损失。需回滚引擎行为则连代码一起回退（去 rounding 是行为变更，不可仅靠 schema 回滚）。

## Open Questions

无。reset 路径 rounding（D2 选保留全局）、UI 位置（D5 仅 `/lifts`）、默认语义（D1 NULL 继承）均已在 open 阶段与用户确认。
