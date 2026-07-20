---
date: 2026-07-20
status: revised
---

# 自重动作的工作重量（bodyweight working weight）— Design

- **Date:** 2026-07-20
- **Status:** Revised 2026-07-20 after grilling session（五项决策折入，见「Grilling outcomes」）
- **Trigger:** profile 内 Dips / Chin-ups / High Crunch 三个自重动作 `start: 0.0`，导致所有依赖重量的计算失真：吨位 `_actual_tonnage = 0 × reps = 0`、est1RM `estimate_1rm(0, reps) = 0`、live preview 与历史 est1RM 同病。用户提出「加个体重」修复。
- **References:** [ADR 0004 — bodyweight working-weight seam](../../adr/0004-bodyweight-working-weight-seam.md)（本设计核心决策）· [ADR 0001 — TM accumulates raw](../../adr/0001-tm-accumulates-raw.md) · [ADR 0003 — effective-step grid](../../adr/0003-t2t3-progression-snap-grid.md) · [per-lift volume design](./2026-07-15-per-lift-volume-comparison-design.md) · [live-est1rm-preview design](./2026-06-27-live-est1rm-preview-design.md) · [CONTEXT.md — Working Weight / Added weight / Bodyweight / Bodyweight percentage](../../../CONTEXT.md)

## Grilling outcomes（2026-07-20）

1. **术语重整**：原草案用 `load` / `to_load`，但 CONTEXT.md 两次把 `load` 列为 _Avoid_。改用 canonical **Working Weight**，引入新术语 **Added weight**。`to_load` → `working_weight()`。
2. **裸读点穷举**：原草案列 6 点，核实代码漏了 `recompute_state` 两条（est1RM + t2 reset 的 est_k）和 `week_plan` CLI 显示一条。补全至 8+ 点（见「裸读点穷举清单」）。
3. **承重比例模型**：原 `工作重量 = 附加 + 体重` 隐含 fraction=1.0，对俯卧撑等部分承重动作是 latent bug。改 `工作重量 = 附加 + 体重 × bodyweight_pct`。
4. **字段去冗余**：原 `bodyweight: bool` + `bodyweight_pct: float` 两字段冗余（bool 可从 pct>0 推出）。合并为单字段 `bodyweight_pct`，默认 `0.0`（普通动作）。
5. **ADR 0004**：存附加 + 单接缝决策（路 1 存负荷 vs 路 2 存附加）满足难逆/无背景困惑/真 trade-off 三条，立 ADR 0004。

## Context

引擎与数据模型现状（经 graphify + codegraph + grep 核实）：

- `sbs_cli/data/schema.py::Lift`（静态，profile.yaml）：`max`（sbs）/`start`（t2/t3）即该动作的「重量」。
- `sbs_cli/data/schema.py::LiftState`（动态，state.yaml / DB `lift_state`）：`tm`（sbs）/`weight`（t2/t3）、`est1rm`、`history: List[SetEntry]`。
- `SetEntry(week, weight, reps)`：`weight` 由 `advance_lift` 写入 = 当周工作重量（对自重动作 = 附加）。

**根因**：`weight` 字段语义重载 —— 普通动作 = 工作重量，自重动作 = 附加重量，而代码对二者一视同仁。任何「在每个读点 `if bodyweight: +体重`」的修法（补丁式）都保留这个重载，漏一处即 bug，新增计算点必忘。

## Decision

**彻底修 = 消灭重载**：所有 engine 纯函数只认 **Working Weight**（CONTEXT canonical 术语），由唯一接缝 `working_weight()` 算出。存储仍存附加（保历史稳定，见 ADR 0004），读取时归一为工作重量喂给 engine。

### 核心接缝（新文件 `sbs_cli/engine/load.py`）

```python
def working_weight(added: float, bodyweight: float, bodyweight_pct: float) -> float:
    """Canonical working weight fed to ALL engine math.

    added + bodyweight × bodyweight_pct. For an ordinary lift bodyweight_pct == 0,
    so this returns added unchanged. Every call site that feeds estimate_1rm /
    tonnage / round_weight / t2_next-reset MUST pass through here — never a raw
    .weight / .start / history.weight. Enforced by behavior-guard tests.
    See ADR 0004.
    """
    return added + bodyweight * bodyweight_pct
```

**契约**：`estimate_1rm` / `_actual_tonnage` / `round_weight` / `t2_next` 等纯函数**签名零改**，但调用方必须传 working weight。`bodyweight_pct` 是 `Lift` 属性，`bodyweight`（用户体重）从 `Profile` / settings 取。

流向：

```
存储(附加) ──┬─ advance 写回 ──→ state.weight = 附加 (不变)
            └─ 读取 ──→ working_weight(附加, bodyweight, lift.bodyweight_pct) ──→ engine 纯函数
history(附加,稳定) ──→ working_weight ──→ estimate_1rm
```

engine 纯函数零改。裸读点改为「先 `working_weight()` 再喂 engine」。

### 数据模型

**CLI schema（`sbs_cli/data/schema.py`）**

`Profile` 加：

```python
bodyweight: float = 0.0   # 用户体重(kg)，全局；working_weight 用
```

`Lift` 加两字段（正交、去冗余）：

```python
bodyweight_pct: float = 0.0       # 承重比例：0.0=普通动作；1.0=全身体重自重；0.64=俯卧撑
progression: str = "weight"       # "weight"(默认,走 t2_next/t3_next) | "none"(跳过自动进阶)
```

单字段 `bodyweight_pct`（非 bool+pct）：`0.0` = 普通动作（工作重量 = 附加 + 体重×0 = 附加，旧行为零变），`> 0` = 自重动作。是否自重可由 `bodyweight_pct > 0` 推出，无需冗余 bool。

当前三动作：

| 动作 | tier | bodyweight_pct | progression | 说明 |
|------|------|----------------|-------------|------|
| Dips | t3 | 1.0 | weight | 可加负重腰带，+incr 到附加 |
| Chin-ups | t2 | 1.0 | weight | 同上 |
| High Crunch | t3 | 1.0 | none | 纯自重，不进阶，手动改 profile reps |

**webapp DB**

- `settings` 表 + `bodyweight REAL DEFAULT 0`（与 rounding/incr 同表，`repo.get_settings` 已返回 dict）。
- `lifts` 表 + `bodyweight_pct REAL DEFAULT 0.0`、`+ progression TEXT DEFAULT 'weight'`。
- `repo.create_lift` 签名 + `bodyweight_pct`、`progression` 两参数；`_lift_from_row` 读两列。

**profile.yaml** 顶层 `bodyweight: 75.0`；三动作各加 `bodyweight_pct: 1.0`（Crunch 再加 `progression: none`）。

**同步**：`migrate.py`（profile→DB）已同步 rounding 等，加 `bodyweight` / `bodyweight_pct` / `progression` 同链路传给 `create_lift`。

### 裸读点穷举清单（grep 核实，8+ 点）

按「读 weight 喂计算」分类。**A–F 为计算点（必过 `working_weight()` 接缝），G–H 为显示点（按 UI 规则），I 为存储点（保持附加）。**

| # | 位置 | 现状 | 改造 |
|---|------|------|------|
| A | `program.py::best_1rm:13` | `estimate_1rm(h.weight, h.reps)` 排序+取值 | 用 working weight 排序与返回（需传 pct+bw） |
| B | `program.py::_est1rm_from_history:21` | `estimate_1rm(b[0], b[1])` | 由 A 返回 working weight 即自动正确；或显式接缝 |
| C | `program.py::recompute_state:98` | `est = _est1rm_from_history(history)` | 接缝（**原草案漏**）|
| D | `program.py::recompute_state:110` | t2 重放 `est_k = _est1rm_from_history(...)` 喂 `t2_next` reset | 接缝（**原草案漏；Chin-ups t2 reset 不补则崩**）|
| E | `preview.py::_working_weight:19` | `return state.weight` | `return working_weight(state.weight, bw, lift["bodyweight_pct"])` |
| F | `volume.py::lift_week_volume:72` | history 分支 `weight=row["weight"]` | 接缝（current 分支走 E 已是工作重量 ✓）|
| G | `program.py::week_plan:87,89` | `PlanItem(weight=ls.weight)` t2/t3 | CLI 显示（**原草案漏**）；按 UI 规则显示附加/工作重量 |
| H | `plan.py::_by_day:71,75` | `weight=st["weight"]` t2/t3 | webapp 显示；按 UI 规则 |
| I | `program.py::advance_lift:43` / `advance.py:59` | `w=state.weight`→history / `append_history` | **保持附加**（存储不变，历史稳定）|

sbs 分支（`:41`/`:66`/`:84`）不动 —— 当前无 sbs 自重动作（YAGNI）；未来加权引体作 main 时再议。

**调用链传参**：`best_1rm` / `_est1rm_from_history` 需知 lift 的 `bodyweight_pct` + 全局 `bodyweight`，签名扩展（从 `advance_lift` / `live_preview` / `recompute_state` 传入）。

### 进阶规则

`advance_lift`（program.py）t2/t3 段加 progression 分支：

```python
if lift.progression == "none":
    pass   # 纯自重：只记 history + est1rm，不改 state.weight/target
else:
    # 现有 t2_next / t3_next 逻辑不变（操作 state.weight = 附加）
```

- Dips/Chin-ups（`progression="weight"`）：`t3_next`/`t2_next` 照常，`state.weight` += incr（附加涨），工作重量同步涨。
- High Crunch（`progression="none"`）：`state.weight` 恒 0，工作重量=体重×pct 不变，est1rm/吨位正确；进阶靠手动改 profile reps。若不设 none，t3_next 会给 Crunch 堆幻影附加（2.5/5/7.5…），毫无意义。

history + est1rm 照记（`progression="none"` 也记）。纯函数 `t2_next`/`t3_next`/`sbs_next` **零改**，分支在调用方。webapp `services/advance.py` 经 `advance_lift` 间接受益；`recompute_state` 同套 progression 检查（C/D 点）。

### UI

- `base.html` `body max-width: 900px → 1200px`（给「附加 (工作重量)」腾位，防 `.row` flex-wrap 把末组 input 挤下行）。
- 重量显示（G/H 点）：自重动作 `+{{ added }} ({{ working_weight }}) kg`，普通动作 `{{ weight }} kg` 不变。
- 备选：`.meta{white-space:nowrap}` 防重量段内部断行（实现期定）。

## Goals / Non-Goals

**Goals**
- 自重动作的吨位、est1RM、live preview、history est1RM、t2 reset 全部按 `工作重量 = 附加 + 体重 × bodyweight_pct` 正确计算。
- 消灭 `weight` 语义重载：engine 纯函数只收 working weight，单一 `working_weight()` 接缝（ADR 0004）。
- history 稳定（存附加，体重变化不污染历史）。
- 承重比例建模（`bodyweight_pct`），不留「全身体重硬编码」latent bug。
- 可加重自重动作（Dips/Chin-ups）照常进阶；纯自重（Crunch）不自动进阶。
- 守卫测试防「新计算点漏接缝」回潮。

**Non-Goals**
- sbs tier 自重动作（当前无，YAGNI）。
- 体重随时间变化（全局静态值；已知精度代价，见 ADR 0004 后果）。
- est1RM 对 Crunch 是否隐藏（值会正确；显示与否是后续 UI 问题）。
- per-week 体重日志（ADR 0004 明确排除）。

## 守卫测试

两层：

1. **行为守卫（主）** — fixture bodyweight lift（`bw=75, pct=1.0, added=0, reps=5`），断言：
   - `live_preview` est1rm ≈ `estimate_1rm(75, 5)` ≠ 0。
   - `lift_week_volume` = `75 × 总reps` ≠ 0。
   - `_working_weight` = 75。
   - `advance_lift` 后 Crunch `state.weight` 仍 0、Dips `state.weight` += incr。
   - `recompute_state` 对 Chin-ups（t2）reset 用工作重量算的 est1rm（**针对原草案漏的 D 点**）。

   任何新计算点漏接缝 → 算出 0（或附加）→ 测试红。

2. **契约文档（辅）** — `load.py` docstring 写死契约（见上）。可选：实现期评估 grep-lint 扫 `estimate_1rm(` 调用点（脆弱，优先行为守卫）。

## 迁移

- **DB**：`settings` + `bodyweight REAL DEFAULT 0`；`lifts` + `bodyweight_pct REAL DEFAULT 0.0`、`+ progression TEXT DEFAULT 'weight'`。SQLite `ALTER TABLE ADD COLUMN`（现有库自动升级；旧 lifts 默认 0.0/`weight` = 普通动作，行为不变）。
- **profile.yaml**：顶层 `bodyweight: 75.0`；Dips/Chin-ups `bodyweight_pct: 1.0`；High Crunch `bodyweight_pct: 1.0, progression: none`。
- **`migrate.py`**（profile→DB）：`create_lift` 调用传 `bodyweight_pct` / `progression`。
- **history 一致性**：旧 Dips/Chin-ups `history.weight` 当年从 `start=0` 来 = 附加 0，语义已对（`working_weight` 后 = 75）。**无需改 history**。
- **`lift_state.est1rm` 重算**：旧值按 weight=0 算 = 错。迁移先加列、再触发 `recompute_on_start_change`（t2/t3）重放 history 重算 est1rm（注意：recompute 本身须先上接缝，即 C/D 点改造先行或同批）。

## 测试计划

- **单元**：`working_weight`（含 pct=0/1/0.64 三态）；`_est1rm_from_history(pct, bw)`；`best_1rm` 排序（工作重量）；`_working_weight` / `_actual_tonnage` bodyweight 分支；`recompute_state` t2 reset 用工作重量；`advance_lift` `progression="none"` 跳过进阶。
- **集成**：`_by_day` / `week_plan` 自重显示「+附加 (工作重量)」；`live_preview` est1rm≠0；`save_log` 后吨位≠0。
- **守卫**：见上行为守卫套件。
- **迁移**：旧库升级后三列在（`settings.bodyweight`/`lifts.bodyweight_pct`/`progression`）；profile sync 正确；est1rm 重算后非 0。
- **回归**：全量测试。`estimate_1rm` 签名不变，普通动作 `working_weight(added, bw, 0.0)=added` → 旧行为零变。

## 待查（实现期）

1. `best_1rm` 返回 `(weight, reps)` 的 weight 语义 —— 返回工作重量还是附加？（影响 `_est1rm_from_history` 是否需显式接缝；倾向返回工作重量，B 点自动正确）
2. UI `max-width` 具体值（900→1200?）、`.meta` 是否加 `white-space:nowrap`。
3. grep-lint 守卫做不做。
4. 迁移顺序：先上 C/D 接缝改造再重算 est1rm，避免重算时仍用旧逻辑。

## Terminology（见 CONTEXT.md）

| 术语 | 指 |
|------|-----|
| 附加 (Added weight) | 自重动作 `weight`/`start`/`history.weight` 存的值：腰带/哑铃等额外负荷 |
| 工作重量 (Working Weight) | engine 计算用：普通=附加，自重=附加 + 体重×bodyweight_pct |
| 体重 (Bodyweight) | 用户全局体重（`Profile.bodyweight` / `settings.bodyweight`），单值静态 |
| 承重比例 (bodyweight_pct) | 该动作移动的体重占比：0.0 普通、1.0 全身体重、0.64 俯卧撑 |
