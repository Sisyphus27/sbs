# Brainstorm Summary

- Change: per-lift-t2t3-increment
- Date: 2026-07-10
- Status: grilling 完成，待用户确认精炼设计

## 确认的技术方案（经三轮 grill 精炼）

在 open 阶段 D1-D5 基础上深化。**grill #1/#2/#3 改动了 D2 范围与本体论**：

- **D1** lifts 加 `incr REAL NULL`，NULL = 继承全局 `settings.incr`（live inheritance——改全局时 NULL 动作自动跟随）。
- **D2（精炼）**：
  - t2/t3 命中加重量路径：`weight + eff_incr`，**无 snap**（自量化等差）。
  - **t2 reset + derive_state 起始重量**：snap 到 **eff_incr 网格**（不是全局 rounding）。
  - sbs：`round_weight(TM×intensity, rounding)` 不变。
  - → 每个动作有自己的 snap 网格：sbs→rounding，t2/t3→eff_incr。
- **D3** eff_incr 在引擎入口（`advance_lift` / `recompute_state` / `derive_state`）解析：`lift.incr if lift.incr is not None else profile.incr`。t2_next reset 分支的 quantum 参数由调用方传 eff_incr。
- **D4** 一次性 `migrate_incr.py`（ALTER + PRAGMA table_info 幂等）；`db.py._SCHEMA` 同步加列。
- **D5** 仅 `/lifts` 编辑器条件渲染 incr 框，sbs 隐藏，清空=NULL。
- **新边界**：tier 切换始终保留 incr（derive_state/apply_switch 不加特例）。
- **incr 校验**：>0 数值，无上限，无 rounding 倍数约束。

## Grill 成果（三处设计改进）

1. **Grill #1（词汇表冲突）→ (a)**：D2 去 rounding 撞 CONTEXT.md「loaded weight always rounded」。判定：词汇表偏杠铃语境；cable/器械附件的步长是**机器属性**，独立于杠铃 rounding。D2 正确。→ **改 CONTEXT.md + 写 ADR 0003**。
2. **Grill #2（reset 网格）→ (b)**：pull-downs 是 T2+cable，reset 选项 (a) 出 52.5（非 5 倍数，不可加载）。改 reset + derive snap 到 eff_incr 网格，每动作待在自己网格。默认配置向后兼容（incr=2.5=rounding）。
3. **Grill #3（术语碰撞）→ (a)**：increment 一词三用。规范术语三分：**rounding quantum（配片粒度，现仅 sbs）/ progression step（递进步长）/ effective step（有效步长 eff_incr，t2/t3 的 snap 网格）**。清 CONTEXT.md。

## 关键取舍与风险

- recompute 路径零额外管道：经 `_lift_from_row`（接入 incr）+ `recompute_state`（解析 eff_incr）自动继承。
- 去 rounding 默认配置 no-op（向后兼容）。
- reset/derive 改 snap 到 eff_incr：默认配置（incr=2.5=rounding）结果不变，仅 incr≠rounding 时变（新功能域）。
- recompute 用当前 eff_incr 重放整段历史（既有假设：reassume current config throughout；非本变更范围）。
- test_columns.py 须同步加 incr。
- 风险：迁移重复执行 → PRAGMA 守卫幂等。

## 测试策略

9 落点：test_progression（t3 全去 / t2 add 去 / t2 reset snap eff_incr）、test_program（eff_incr 解析）、test_repo（incr 读写）、test_columns（加列）、test_routes_lifts（创建/编辑/清空/sbs 不写/非法值）、test_tier_service（切换保留 incr）、test_recompute_service（重放 eff_incr）、test_advance_service（接线）、新 test_migrate_incr（幂等）。

## Spec Patch（回写 specs/t2t3-progression/spec.md）

1. **MODIFIED**「t2 reset 保留全局 rounding」requirement → 改为「t2 reset snap 到有效步长网格」，场景例子改（est1rm=70, eff_incr=5 → reset=50，非 52.5）。
2. **ADDED scenario**「tier 切换保留 incr」。
3. derive_state 起始重量 snap eff_incr 纳入对应场景描述。

## 文档交付物（Design Doc 步骤一并写）

- Design Doc：`docs/superpowers/specs/2026-07-10-per-lift-t2t3-increment-design.md`
- CONTEXT.md：改 rounding quantum + loaded-value 定义，加 progression step / effective step 术语。
- ADR 0003：`docs/adr/0003-t2t3-no-rounding-snap.md`——为何 t2/t3 不 snap 到 rounding（机器步长独立于杠铃配片；难逆转 + 无上下文会困惑 + 真实取舍）。
