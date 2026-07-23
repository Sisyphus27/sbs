# 训练模式统一重构 — 设计

日期： 2026-07-23
状态： 已批准 (4/4 节通过）

## 背景与问题

当前训练分类混乱： 一个 lift 的行为由三个叠加字段决定， 概念互相重叠：

- `tier` (`sbs`/`t2`/`t3`) — 名义上的进阶模式
- `progression` (`weight`/`none`) — 补丁式进阶开关， 只挂 t2/t3
- `bodyweight_pct` — 既表达"是自重动作"又表达"负重比例", 靠 `>0` 隐式推断

进阶分派逻辑散落在 `advance_lift` / `week_plan` / `tier.derive_state` / `repo._init_lift_state` 四处 if/else, 加模式要改多点。纯自重需求 (不带负重腰带， 不自动进阶， 但仍统计 est1rm/history) 在当前模型里没有一等位置。

## 目标 (第一性原理)

一个 lift 的训练行为由**两个正交维度**唯一决定：

- **载荷模型 (load model)** — 工作重量怎么算
- **进阶模式 (progression mode)** — 下周重量/次数怎么变

引擎按组合分派， 新增模式 = 注册一行 + 一个 handler 文件， 不动既有分派点。

## 方案： 双枚举 + 注册表分派

### 1. 数据模型

`lifts` 表两列取代旧概念：

| 新列 | 值 | 取代 |
|---|---|---|
| `load_model` | `barbell` \| `bodyweight` \| `pure_bodyweight` | `bodyweight_pct` 隐式推断 |
| `mode` | `sbs` \| `linear_t2` \| `linear_t3` \| `none` | `tier` + `progression` |

`Lift` dataclass:
```python
load_model: str = "barbell"
mode: str = "none"
bodyweight_pct: float = 0.0   # 保留为载荷参数 (非 mode 标志)
# 删除: tier, progression
```

语义：
- `barbell` — working_weight = added (bodyweight_pct 强制 0)
- `bodyweight` — working_weight = added + bw×pct (ADR 0004 seam 不变)
- `pure_bodyweight` — added 恒 0, working_weight = bw×pct, 配合 `mode=none`
- `mode` 决定进阶； `load_model` 决定载荷。正交。

`lift_state.tier` 列 → 改名 `mode` (值域同 mode)。

### 2. 引擎注册表

新文件 `sbs_cli/engine/modes.py`。每个 mode 一个 handler, 统一接口：

```python
class Mode(Protocol):
    def initial_state(self, lift, settings) -> LiftState: ...
    def advance(self, profile, lift, state, actual, week) -> None: ...
    def plan_item(self, profile, lift, state, week) -> PlanItem: ...
    def derive_on_switch(self, lift, history, settings) -> dict: ...

PROGRESSION_REGISTRY: dict[str, Mode] = {
    "sbs":       SbsMode(),
    "linear_t2": LinearT2Mode(),
    "linear_t3": LinearT3Mode(),
    "none":      RecordOnlyMode(),
}
```

现有纯函数 (`sbs_next`/`t2_next`/`t3_next`/`round_weight`/`working_weight`/`estimate_1rm`) 不动， 由对应 handler 复用。载荷统一走 `working_weight(added, bw, pct)` seam。

调用点改造 (全部 if/else 收拢为查表）:
- `program.advance_lift` → `PROGRESSION_REGISTRY[lift.mode].advance(...)`
- `program.week_plan` → `...plan_item(...)`
- `program.initial_state` → `...initial_state(...)`
- `tier.derive_state` → `...derive_on_switch(...)`
- `repo._init_lift_state` → `...initial_state(...)`

### 3. 各 handler 行为 (迁移现有逻辑)

| mode | initial_state | advance | plan_item | derive_on_switch |
|---|---|---|---|---|
| `sbs` | tm=max | tm=sbs_next(tm, repout, actual); 重量走 21 周表 | round(tm×intensity) | tm=est1rm (ADR 0001) |
| `linear_t2` | weight=start, target=8 | t2_next 瀑布 (8→6→4, N 次 miss 重置) | weight, target | weight=round(est1rm×t2_reset_pct) |
| `linear_t3` | weight=start | t3_next (命中≥target +incr) | weight, t3_target | weight=round(est1rm×0.6) |
| `none` | weight=start (可 None) | 不进阶， 仅记 history+est1rm | weight (或体重), 无 target | weight=start 或 0 |

载荷在 handler 内部统一经 `working_weight` seam:
- `sbs`/`linear_*` + `barbell`: pct=0
- `sbs`/`linear_*` + `bodyweight`: pct>0, est1rm/tonnage/t2 重置全走 seam
- `none` + `pure_bodyweight`: added=0, 显示 bw×pct

纯自重 = `load_model=pure_bodyweight` + `mode=none` → 只记 est1rm/history, 不自动加重。

### 4. 迁移 + 依赖适配

**迁移脚本** `migrate_modes.py` (一次性， 幂等）:
```
旧 (tier, progression, bodyweight_pct) → 新 (load_model, mode)
- tier=sbs                        → load_model=barbell,         mode=sbs
- tier=t2, pct=0                  → load_model=barbell,         mode=linear_t2
- tier=t2, pct>0                  → load_model=bodyweight,      mode=linear_t2
- tier=t3, pct=0                  → load_model=barbell,         mode=linear_t3
- tier=t3, pct>0                  → load_model=bodyweight,      mode=linear_t3
- progression=none (任意 tier)     → load_model=pure_bodyweight, mode=none
```
history 不动 (added weight 语义不变， ADR 0004)。`lift_state.tier` 列 → `mode`。

**依赖适配点**:
- `webapp/routes/lifts.py` — 表单 new/edit: tier → load_model+mode 两个下拉； `tier_preview`/`tier_apply` → `mode_preview`/`mode_apply`
- `webapp/services/advance.py` `_lift_from_row` — 读新列
- `webapp/services/preview.py` / `volume.py` — 经 seam, 接口不变
- `sbs_cli/data/io.py` — YAML profile/state 序列化新字段
- `sbs_cli/view/{html,terminal}.py` — 显示 label 用 mode
- 模板 `lifts.html`/`_lift_row.html`/`tier_preview.html` — 文案 tier→mode

**测试**: 现有 `test_bodyweight_guard`/`test_progression`/`test_tier_service`/`test_advance_service` 改成新字段重跑； 新增注册表分派测试 + 迁移映射测试。

## 影响面

引擎核心 (`sbs_cli/engine/` + `program.py`) + schema + webapp 表单/服务/模板 + 一次性迁移脚本。history 数据不动。ADR 0001-0004 语义保留， 仅字段名/分派方式重构。
