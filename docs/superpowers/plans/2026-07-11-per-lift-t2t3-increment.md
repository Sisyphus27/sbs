---
change: per-lift-t2t3-increment
design-doc: docs/superpowers/specs/2026-07-10-per-lift-t2t3-increment-design.md
base-ref: 3c8bb1238caadcb31eadf896190c431ae71a53cc
archived-with: 2026-07-11-per-lift-t2t3-increment
---

# Per-lift T2/T3 递进步长 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为 t2/t3 动作增加可选的 per-lift 递进步长（`lifts.incr`，NULL 继承全局 `settings.incr`），解决 cable/器械动作（Face Pull、Pull-downs）配片 5kg 一跳无法用全局 `incr=2.5` 加载的问题。

**Architecture:** 引擎入口（`advance_lift` / `recompute_state` / `derive_state`）统一解析 effective step = `lift.incr if not None else profile.incr`。t2/t3 命中加重量走纯等差（`weight + eff_incr`，不 snap）；t2 reset 与 tier 切换起始推导 snap 到该动作的 eff_incr 网格；sbs 路径不动（仍 `round_weight(TM×intensity, rounding)`）。默认 `incr=2.5 = rounding`，所有既有结果不变（完全向后兼容）。`Lift.incr: Optional[float] = None` 经 `_lift_from_row` + `recompute_state` 自动贯穿 recompute 路径，零额外管道。nullable 列经一次性 `ALTER TABLE` 迁移脚本上线。

**Tech Stack:** Python 3 (CPython)，SQLite (sqlite3 stdlib)，Flask + HTMX + Jinja2，pytest。运行环境：`conda run -n sbs`。

## Global Constraints

- **运行命令前缀**：所有 Python/pytest 命令在 `D:\WorkSpace\sbs\` 下用 `conda run -n sbs` 执行（例：`conda run -n sbs python -m pytest tests/test_progression.py -v`）。
- **本体论（ADR 0003，Task 0 落盘）**：t2/t3 命中加重量不 snap（纯等差）；t2 reset + tier 切换起始推导 snap 到 eff_incr 网格（不是全局 rounding）；rounding quantum 行为收窄到 sbs；effective_step = per-lift incr ?? 全局 incr，既是 add-step Δ 也是该动作派生重量的 snap 网格。
- **术语（Task 0 写入 CONTEXT.md）**：rounding quantum（配片粒度，行为上仅 sbs 用）/ progression step（递进步长，全局默认 `settings.incr`，per-lift 覆盖 `lifts.incr`）/ effective step / eff_incr（有效步长，解析后实际步长 = per-lift ?? 全局，也是 t2/t3 的 snap 网格）。
- **校验（D7）**：`incr > 0`，数值；无上限；无 rounding 倍数约束（D2）。非法（≤0 / 非数字）路由层 flash + 保留原值。
- **向后兼容是硬约束**：默认 `incr=2.5 = rounding`，既有测试（`test_progression.py`、`test_program.py`、`test_advance_service.py`、`test_tier_service.py` 全部）必须零修改全绿——每个引擎任务完成后立即跑既有相关测试确认无回归。
- **out of scope**：`tools/sbs_gzclp/progression.py`（Excel 公式生成器的镜像源，含独立 `T2Params`/`T3Params`/`round_weight`）**不动**——它不是引擎，cable 动作的 xlsx 公式生成与本变更无关；不要"顺手统一"。`recompute.py` 服务层零改动（经 `_lift_from_row` + `recompute_state` 自动继承，仅在 Task 6 验证）。
- **提交节奏**：每个 task 末尾单独 commit（conventional commits：feat/fix/refactor/docs/test/chore）。Attribution 已全局禁用，不要加 Co-authored-by。

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## 文件结构

| 文件 | 责任 | 改动类型 |
|------|------|---------|
| `openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md` | delta spec（handoff-locked open 版） | MODIFY（reset requirement）+ ADD（tier-switch 场景） |
| `openspec/changes/per-lift-t2t3-increment/tasks.md` | change 的任务清单 | MODIFY（并入精炼任务） |
| `CONTEXT.md` | 项目术语表 | MODIFY（rounding quantum / loaded-value 定义）+ ADD（progression step / effective step） |
| `docs/adr/0003-t2t3-progression-snap-grid.md` | ADR 0003 | CREATE |
| `sbs_cli/engine/progression.py` | t2/t3 纯函数规则 | MODIFY（t3_next 去 quantum/snap；t2_next HIT 去 snap） |
| `sbs_cli/data/schema.py` | `Lift` dataclass | MODIFY（加 `incr` 字段） |
| `sbs_cli/program.py` | 引擎入口编排 | MODIFY（advance_lift / recompute_state 解析 eff_incr） |
| `webapp/db.py` | SQLite schema bootstrap | MODIFY（`_SCHEMA` lifts 加 `incr REAL`） |
| `webapp/repo.py` | DB CRUD | MODIFY（`_LIFT_COLS` + `create_lift` 加 incr） |
| `webapp/services/advance.py` | DB→dataclass 适配 | MODIFY（`_lift_from_row` 读 incr） |
| `webapp/services/recompute.py` | start 编辑重放 | 零改动（Task 6 验证自动继承） |
| `webapp/services/tier.py` | tier 切换推导 | MODIFY（derive_state t2/t3 snap 网格 rounding → eff_incr） |
| `webapp/routes/lifts.py` | lift CRUD 路由 | MODIFY（new/edit 接 incr + 校验） |
| `webapp/templates/_lift_row.html` | 编辑行片段 | MODIFY（t2/t3 加 incr 框，sbs 隐藏） |
| `webapp/templates/lifts.html` | 动作管理页 | MODIFY（新建表单加 incr 框） |
| `migrate_incr.py` | 一次性列迁移 | CREATE |
| `migrate.py` | YAML/xlsx → DB | 零改动（Task 11 审计，create_lift 的 incr 默认 None） |
| `tests/test_db.py` | schema 列断言 | MODIFY（加 incr 列断言） |

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 0: Spec / CONTEXT.md / ADR 0003 回写（文档先行，无源码）

> 设计 handoff 在 grilling 前生成并 hash 锁定了 open 阶段的 spec.md/tasks.md；grilling 后的精炼（reset snap eff_incr、tier 切换保留 incr、derive_state 起始 snap、术语三分、ADR 0003）推迟到本 task 先回写，再进入引擎/DB/UI 实现。

**Files:**
- Modify: `openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md`
- Modify: `openspec/changes/per-lift-t2t3-increment/tasks.md`
- Modify: `CONTEXT.md`
- Create: `docs/adr/0003-t2t3-progression-snap-grid.md`

- [x] **Step 1: 回写 spec.md 的 t2 reset requirement**

把 `openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md` 中这一段（open 阶段版本，snap 全局 rounding）：

```markdown
### Requirement: t2 reset 保留全局 rounding

t2 动作连续 miss 达 `fail` 次触发 reset 时，系统 SHALL 将重置重量 `est1rm × reset_pct` snap 到全局 rounding quantum。per-lift incr 不参与 reset 路径。

#### Scenario: reset 重量 snap 到全局 rounding

- **WHEN** 一个 t2 动作连续 miss 达 `fail` 次（est1rm=103.3，reset_pct=0.75，全局 rounding=2.5）
- **THEN** reset 重量 = round_weight(103.3 × 0.75, 2.5) = 77.5
```

整段替换为（snap eff_incr 网格 + NULL 兼容 + tier 切换保留 incr 场景）：

```markdown
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
```

- [x] **Step 2: 回写 tasks.md，并入精炼任务**

在 `openspec/changes/per-lift-t2t3-increment/tasks.md` 中：

(a) 在「## 1. Engine」之前插入新的「## 0. 文档/术语先行」段：

```markdown
## 0. 文档/术语先行

- [x] 0.1 回写 spec.md：MODIFY t2 reset requirement（snap 网格 rounding → effective step）+ ADD「tier 切换保留 incr」场景
- [x] 0.2 改 CONTEXT.md：rounding quantum / loaded-value 定义收窄到 sbs；加 progression step / effective step 术语
- [x] 0.3 落盘 docs/adr/0003-t2t3-progression-snap-grid.md（每动作一个 snap 网格）
```

(b) 在「## 4. Webapp 服务/路由接线」的 4.2 之后加 4.4：

```markdown
- [x] 4.4 `webapp/services/tier.py` 的 `derive_state`：t2/t3 起始重量 snap 网格由 rounding 改为 eff_incr（`lift["incr"] if not None else settings["incr"]`）；`apply_switch` 不动（incr 在 lifts 列，tier 切换不触碰）
```

- [x] **Step 3: 改 CONTEXT.md 术语**

在 `CONTEXT.md` 中：

(a) 把「**Loaded weight vs bookkeeping value**:」段落中这一句：

```markdown
A *loaded weight* is put on the bar (working weight, T2/T3
increments and resets) and is therefore always rounded to the rounding quantum.
```

改为（T2/T3 不再 snap 到 rounding，而是各自的有效步长网格）：

```markdown
A *loaded weight* is put on the bar — the sbs working weight (rounded to the
rounding quantum) and T2/T3 increments and resets (rounded to that lift's
effective step). The two grids differ only when a lift sets a per-lift incr that
differs from the global rounding.
```

(b) 把「**Rounding quantum**:」段落中这一句：

```markdown
The single
parameter governing snap-to-grid for every loaded weight. Explicitly NOT applied to TM.
```

改为（行为收窄到 sbs；配置仍全局）：

```markdown
The parameter governing snap-to-grid for **sbs** loaded weights (working weight).
Explicitly NOT applied to TM, and NOT applied to T2/T3 increments/resets — those snap to
the effective step (per-lift incr ?? global incr). Kept as a single global setting for
configuration continuity; its behavioural scope was narrowed to sbs by ADR 0003.
```

(c) 在「**Working Weight**:」段落之后、「**Loaded weight vs bookkeeping value**:」之前，插入两个新术语：

```markdown
**Progression step**:
The weekly increment added to a T2/T3 lift's working weight on a hit (global default
`settings.incr`, overridable per lift via `lifts.incr`; NULL = inherit global live).
Distinct from the rounding quantum — a cable/attachment lift's step is a property of
the machine's plate stack (e.g. 5 kg jumps), not of the barbell plate grid.
_Avoid_: increment (ambiguous — see effective step / rounding quantum)

**Effective step (eff_incr)**:
The resolved progression step actually applied for a given lift: `lifts.incr` when set,
else the global `settings.incr`. It is both the Δ added on a T2/T3 hit (no further
rounding — self-quantising arithmetic) AND the grid that lift's T2 resets and tier-switch
starting weights snap to. Every lift therefore carries its own snap grid.
_Avoid_: increment (ambiguous)
```

- [x] **Step 4: 落盘 ADR 0003**

创建 `docs/adr/0003-t2t3-progression-snap-grid.md`：

```markdown
# 0003 — T2/T3 progression snaps to the per-lift effective-step grid

- **Date:** 2026-07-11
- **Status:** accepted

## Context

ADR 0001 states the rounding quantum governs "all loaded weight — including T2/T3
increments and resets." That wording is barbell-shaped. Cable/attachment lifts (face pulls,
pull-downs) are loaded from a machine stack whose minimum jump (e.g. 5 kg) is a property of
the machine, independent of the gym's barbell plate increment (rounding, default 2.5 kg).
Introducing a per-lift `incr` (so a cable lift can progress 5 kg/week) exposes the mismatch:
if that lift's reset / tier-switch start weight snaps to the global rounding, the result
(e.g. `round_weight(52.5, 2.5) = 52.5`) is not loadable on a 5 kg stack — the opposite of
what rounding is for (keeping weights loadable).

## Decision

1. **T2/T3 hit progression is pure arithmetic.** A hit adds the effective step with no
   further snap: `weight + eff_incr`.
2. **T2 reset and tier-switch-derived T2/T3 starting weights snap to the effective-step
   grid** `round_weight(·, eff_incr)`, not the global rounding.
3. **The rounding quantum's behavioural scope narrows to sbs.** Only the sbs working weight
   `round_weight(TM × intensity, rounding)` snaps to it. (The setting stays global; renaming
   it is out of scope.)
4. **effective_step = per-lift `lifts.incr` ?? global `settings.incr`.** It is resolved at
   the engine entry points (`advance_lift`, `recompute_state`, `derive_state`). It is both
   the hit-add Δ and the snap grid for that lift's derived weights. Each T2/T3 lift carries
   its own snap grid.

## Why

Each lift is loaded by its own apparatus, which has its own minimum increment. Snapping a
cable lift's derived weight to a barbell grid yields a value the machine cannot load —
defeating the purpose of snapping. Default `incr = rounding = 2.5` makes every existing
result identical (add-path snap was a no-op, reset grid was already 2.5), so the change is
invisible unless a lift sets `incr ≠ rounding`.

## Considered Options

- **B (chosen)** — each lift snaps to its own eff_incr grid; default stays compatible.
- **A** — keep snapping reset/derived T2/T3 weights to global rounding. Rejected: cable T2
  (e.g. Pull-downs) resets come out non-loadable.
- **A′** — force `incr` to be a multiple of rounding. Rejected: couples a machine property
  to the barbell plate grid — exactly the category error this change fixes.
- **C** — don't snap derived T2/T3 weights at all (leave `est1rm × pct` raw float).
  Rejected: produces un-loadable fractional weights.

## Consequences

- `rounding` becomes behaviourally sbs-only (still a global setting; rename is out of
  scope). Each T2/T3 lift has its own snap grid (its eff_incr).
- Default `incr = rounding = 2.5` is fully backward-compatible.
- ADR 0001's "T2/T3 increments and resets" wording is superseded for T2/T3 by this ADR.
  ADR 0001 remains authoritative for TM accumulation and the sbs loaded weight.
```

- [x] **Step 5: 提交**

```bash
git add openspec/changes/per-lift-t2t3-increment/specs/t2t3-progression/spec.md \
        openspec/changes/per-lift-t2t3-increment/tasks.md \
        CONTEXT.md docs/adr/0003-t2t3-progression-snap-grid.md
git commit -m "docs(per-lift-incr): backfill spec reset/eff_incr, CONTEXT terms, ADR 0003"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 1: Engine progression — t2_next/t3_next 命中加重量去 snap（TDD）

> t2/t3 命中后累加步长不再 snap（纯等差）。`t3_next` 去掉 `quantum` 参数；`t2_next` 的 HIT 分支去 `round_weight`，reset 分支保留 `round_weight(est1rm × reset_pct, quantum)`（调用方传 eff_incr 作 quantum）。

**Files:**
- Modify: `sbs_cli/engine/progression.py:42-49`（t3_next）、`sbs_cli/engine/progression.py:59-74`（t2_next HIT 分支）
- Test: `tests/test_progression.py`（追加测试）

**Interfaces:**
- Produces: `t3_next(weight, actual, target=15, incr=2.5) -> float`（**移除 `quantum` 参数**）；`t2_next(state, actual, est1rm, fail=3, incr=2.5, reset_pct=0.75, quantum=2.5) -> T2State`（签名不变，HIT 分支不再 round）。下游 `program.py`（Task 3）是首个依赖新 `t3_next` 签名的调用方——不得再传 `quantum=` 给 `t3_next`。

- [x] **Step 1: 写失败测试（追加到 `tests/test_progression.py` 末尾）**

```python
# --- T3 命中精确累加（去 rounding snap；D2）---
def test_t3_hit_adds_incr_without_snapping():
    # incr=3（非 rounding 倍数）：新实现精确 50+3=53；旧实现 round_weight(53, 2.5)=52.5
    assert t3_next(weight=50, actual=16, incr=3) == 53


def test_t3_hit_default_incr_backcompat():
    # 默认 incr=2.5：50+2.5=52.5，与本变更前完全一致
    assert t3_next(weight=50, actual=16) == 52.5


def test_t3_next_signature_has_no_quantum():
    # t3_next 不再接受 quantum 参数（调用方不应再传）
    import inspect
    assert "quantum" not in inspect.signature(t3_next).parameters


# --- T2 命中精确累加（HIT 去 rounding snap；D2）---
def test_t2_hit_adds_incr_without_snapping():
    # incr=3：HIT 时 50+3=53；旧实现 round_weight(53, 2.5)=52.5
    s = t2_next(T2State(target=8, streak=0, weight=50), actual=8, est1rm=100, incr=3)
    assert s == T2State(target=8, streak=0, weight=53)


def test_t2_reset_snaps_to_provided_quantum():
    # reset 分支保留 round_weight(est1rm*reset_pct, quantum)：characterization，
    # 锁定 reset 仍由调用方传入的 quantum 决定（Task 3 把 quantum 从 rounding 改为 eff_incr）。
    # est1rm=90, reset_pct=0.75 -> 67.5；round_weight(67.5, 5)=70（5kg 堆可加载）
    s = t2_next(T2State(target=4, streak=2, weight=50), actual=3, est1rm=90,
                incr=5, reset_pct=0.75, quantum=5)
    assert s == T2State(target=8, streak=0, weight=70.0)
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_progression.py -v`
Expected: FAIL — `test_t3_hit_adds_incr_without_snapping`（旧实现 `round_weight(50+3, 2.5)=52.5 ≠ 53`）、`test_t2_hit_adds_incr_without_snapping`（同理 52.5 ≠ 53）、`test_t3_next_signature_has_no_quantum`（旧签名仍有 quantum）。`test_t3_hit_default_incr_backcompat` 与 `test_t2_reset_snaps_to_provided_quantum` 应已绿（向后兼容 characterization）。

- [x] **Step 3: 改 `sbs_cli/engine/progression.py` 的 `t3_next`（去 quantum/snap）**

把：

```python
def t3_next(weight: float, actual, target: int = 15, incr: float = 2.5,
            quantum: float = 2.5) -> float:
    """T3 accessories: +incr when last set >= target, else repeat."""
    if actual is None:
        return weight
    if actual >= target:
        return round_weight(weight + incr, quantum)
    return weight
```

改为：

```python
def t3_next(weight: float, actual, target: int = 15, incr: float = 2.5) -> float:
    """T3 accessories: +incr when last set >= target, else repeat.

    Pure arithmetic — the hit add is NOT snapped. The incr IS the lift's
    effective step (per-lift ?? global, resolved by the caller), which is itself
    the loadable grid for that apparatus (see ADR 0003)."""
    if actual is None:
        return weight
    if actual >= target:
        return weight + incr
    return weight
```

- [x] **Step 4: 改 `sbs_cli/engine/progression.py` 的 `t2_next` HIT 分支（去 snap，reset 分支不动）**

把 `t2_next` 函数体中的 HIT 行：

```python
    if actual >= state.target:                                   # HIT
        return T2State(state.target, 0, round_weight(state.weight + incr, quantum))
```

改为：

```python
    if actual >= state.target:                                   # HIT — pure arithmetic (ADR 0003)
        return T2State(state.target, 0, state.weight + incr)
```

（reset 分支 `return T2State(8, 0, round_weight(est1rm * reset_pct, quantum))` 与函数签名**保持不变**——`quantum` 仍由调用方传入，Task 3 改传 eff_incr。）

- [x] **Step 5: 运行测试，确认全绿（含既有测试零回归）**

Run: `conda run -n sbs python -m pytest tests/test_progression.py -v`
Expected: PASS（全部，含既有的 `test_t3_hit_adds`、`test_t2_hit_adds_weight_stays_at_target`、`test_t2_third_miss_resets_to_8_at_est1rm_pct` 等——默认 incr=2.5/quantum=2.5 时 `50+2.5=52.5` 与旧 `round_weight(52.5,2.5)=52.5` 相同）。

- [x] **Step 6: 提交**

```bash
git add sbs_cli/engine/progression.py tests/test_progression.py
git commit -m "feat(engine): t2/t3 hit progression drops rounding snap (ADR 0003)"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 2: schema.py Lift.incr 字段（TDD）

> `Lift` dataclass 加 `incr: Optional[float] = None`。NULL = 继承全局（live inheritance）。后续 program.py / repo.py / advance.py 均依赖此字段。

**Files:**
- Modify: `sbs_cli/data/schema.py:15-29`（Lift dataclass）
- Test: `tests/test_schema.py`（追加断言）

**Interfaces:**
- Produces: `Lift(..., incr: Optional[float] = None)`。下游：`program.py` 读 `lift.incr`（Task 3）、`repo.create_lift` 写 incr（Task 5）、`advance._lift_from_row` 读 incr 填入（Task 6）。

- [x] **Step 1: 写失败测试（追加到 `tests/test_schema.py` 末尾）**

```python
from sbs_cli.data.schema import Lift


def test_lift_incr_defaults_to_none():
    # NULL = 继承全局 settings.incr（live inheritance）
    l = Lift(name="Face Pull", tier="t3", day=2)
    assert l.incr is None


def test_lift_incr_can_be_set():
    l = Lift(name="Pull-downs", tier="t2", day=1, incr=5.0)
    assert l.incr == 5.0
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_schema.py -v`
Expected: FAIL — `AttributeError: 'Lift' object has no attribute 'incr'`（或 dataclass 构造拒绝未知 kwarg）。

- [x] **Step 3: 改 `sbs_cli/data/schema.py` 的 `Lift`**

把：

```python
    # t2 / t3
    start: Optional[float] = None
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None for t2/t3
```

改为：

```python
    # t2 / t3
    start: Optional[float] = None
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None for t2/t3
    incr: Optional[float] = None      # t2/t3 per-lift progression step; None = inherit global incr
```

- [x] **Step 4: 运行测试，确认全绿**

Run: `conda run -n sbs python -m pytest tests/test_schema.py -v`
Expected: PASS。

- [x] **Step 5: 提交**

```bash
git add sbs_cli/data/schema.py tests/test_schema.py
git commit -m "feat(schema): add Lift.incr (nullable per-lift progression step)"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 3: program.py eff_incr 解析（TDD）

> 引擎入口解析 `eff_incr = lift.incr if lift.incr is not None else profile.incr`，传入 t2/t3 分支。`advance_lift` 的 t2 分支把 eff_incr 同时作为 incr 与 reset 的 quantum；`recompute_state` 同理。sbs 路径不沾。

**Files:**
- Modify: `sbs_cli/program.py:36-58`（advance_lift）、`sbs_cli/program.py:89-112`（recompute_state）
- Test: `tests/test_program.py`（追加测试）

**Interfaces:**
- Consumes: `Lift.incr`（Task 2）；`t3_next` 无 quantum 参数、`t2_next` 仍收 quantum（Task 1）。
- Produces: `advance_lift` / `recompute_state` 现按 eff_incr 推进 t2/t3。recompute 服务层（`webapp/services/recompute.py`）经此自动继承（Task 6 验证）。

- [x] **Step 1: 写失败测试（追加到 `tests/test_program.py` 末尾）**

```python
# ---- per-lift eff_incr 解析 (D1/D3) ----

def test_advance_t3_uses_per_lift_incr_over_global():
    # lift.incr=5 覆盖 profile.incr=2.5；HIT 时 40+5=45（旧实现用 profile.incr=2.5 -> 42.5）
    p = Profile(incr=2.5, lifts=[Lift(name="Curls", tier="t3", day=1, start=40, incr=5)])
    s = initial_state(p)
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=16, week=1)  # 16>=15 hit
    assert s.lifts["Curls"].weight == 45.0


def test_advance_t3_null_incr_falls_back_to_global():
    # incr=None -> eff_incr=profile.incr=2.5；40+2.5=42.5（向后兼容）
    p = Profile(incr=2.5, lifts=[Lift(name="Curls", tier="t3", day=1, start=40)])
    s = initial_state(p)
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=16, week=1)
    assert s.lifts["Curls"].weight == 42.5


def test_advance_sbs_ignores_incr():
    # sbs 路径不沾 incr：working weight = round(TM*intensity, rounding)
    sched = [ScheduleRow("main", 1, 0.75, 4, 8)]
    p = Profile(rounding=2.5, schedule=sched,
                lifts=[Lift(name="Squat", tier="sbs", day=1, max=100, sets=3,
                            lift_kind="main", incr=99)])
    s = initial_state(p)
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=8, week=1)
    assert s.lifts["Squat"].history[0].weight == 75  # round(100*0.75, 2.5)=75, incr=99 被忽略


def test_recompute_state_t2_reset_snaps_to_eff_incr():
    # recompute 重放：incr=5 的 t2，reset 重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.program import _est1rm_from_history
    p = Profile(t2_reset_pct=0.75, incr=2.5, rounding=2.5,
                lifts=[Lift(name="PD", tier="t2", day=1, start=100, incr=5)])
    lift = p.lift("PD")
    # 最佳组 100x5 -> est1rm≈115；×0.75≈86.4 落在 5-grid(85) 与 2.5-grid(87.5) 之间
    hist = [SetEntry(1, 100.0, 5), SetEntry(2, 100.0, 3),
            SetEntry(3, 100.0, 3), SetEntry(4, 100.0, 3)]  # 1 hit 后 3 连 miss -> reset
    ls = recompute_state(lift, hist, p)
    est = _est1rm_from_history(hist)
    assert ls.weight == round_weight(est * 0.75, 5)       # NEW: eff_incr 网格
    assert ls.weight != round_weight(est * 0.75, 2.5)     # OLD: 全局 rounding 会给不同值
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_program.py -k "per_lift_incr_over_global or null_incr_falls_back or sbs_ignores_incr or reset_snaps_to_eff_incr" -v`
Expected: FAIL — `test_advance_t3_uses_per_lift_incr_over_global`（旧实现传 `incr=profile.incr=2.5` → 42.5 ≠ 45）、`test_recompute_state_t2_reset_snaps_to_eff_incr`（旧实现传 `quantum=profile.rounding=2.5`）。`test_advance_t3_null_incr_falls_back_to_global`、`test_advance_sbs_ignores_incr` 应已绿（向后兼容 characterization）。

- [x] **Step 3: 改 `sbs_cli/program.py` 的 `advance_lift`**

把：

```python
def advance_lift(profile: Profile, lift: Lift, state: LiftState, actual_reps, week: int) -> None:
    """Apply this week's logged last-set reps; mutate state in place. All knobs from profile."""
    # working weight this week (before progression)
    if lift.tier == "sbs":
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, sc.repout, actual_reps)
    elif lift.tier == "t3":
        state.weight = t3_next(state.weight, actual_reps,
                               target=profile.t3_target, incr=profile.incr, quantum=profile.rounding)
    elif lift.tier == "t2":
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                     fail=profile.t2_fail, incr=profile.incr,
                     reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight
```

改为（在 t2/t3 分支前解析 eff_incr；t3 不再传 quantum；t2 把 eff_incr 同时作 incr 与 reset 的 quantum）：

```python
def advance_lift(profile: Profile, lift: Lift, state: LiftState, actual_reps, week: int) -> None:
    """Apply this week's logged last-set reps; mutate state in place. All knobs from profile."""
    # working weight this week (before progression)
    if lift.tier == "sbs":
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
    else:
        w = state.weight
    if actual_reps is not None:
        state.history.append(SetEntry(week=week, weight=w, reps=actual_reps))
        state.est1rm = _est1rm_from_history(state.history)
    # progress
    if lift.tier == "sbs":
        state.tm = sbs_next(state.tm, sc.repout, actual_reps)
    else:
        # effective step: per-lift incr ?? global incr (ADR 0003). It is both the hit-add Δ
        # and the snap grid for this lift's T2 reset. sbs ignores incr entirely.
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        if lift.tier == "t3":
            state.weight = t3_next(state.weight, actual_reps,
                                   target=profile.t3_target, incr=eff_incr)
        elif lift.tier == "t2":
            est = state.est1rm if state.est1rm is not None else 0.0
            ns = t2_next(T2State(state.target, state.streak, state.weight), actual_reps, est,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight
```

- [x] **Step 4: 改 `sbs_cli/program.py` 的 `recompute_state`**

把 `recompute_state` 中 t3 与 t2 的循环改为使用 eff_incr。把：

```python
def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start`` ..."""
    est = _est1rm_from_history(history)
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target,
                             incr=profile.incr, quantum=profile.rounding)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1]) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=profile.incr,
                         reset_pct=profile.t2_reset_pct, quantum=profile.rounding)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")
```

改为（顶部解析 eff_incr 一次；t3 不传 quantum；t2 传 eff_incr 作 incr 与 quantum）：

```python
def recompute_state(lift: Lift, history: List[SetEntry], profile: Profile) -> LiftState:
    """Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``
    over ``history``. History rows are immutable facts; only their reps drive the
    replay. ``est1rm`` is computed from the real history weights (unchanged by the
    new start). Not applicable to sbs (sbs has no start-based progression)."""
    est = _est1rm_from_history(history)
    # effective step: per-lift incr ?? global incr (ADR 0003).
    eff_incr = lift.incr if lift.incr is not None else profile.incr
    if lift.tier == "t3":
        weight = lift.start or 0.0
        for h in history:
            weight = t3_next(weight, h.reps, target=profile.t3_target, incr=eff_incr)
        return LiftState(name=lift.name, tier="t3", weight=weight, target=None,
                         streak=0, est1rm=est, history=history)
    if lift.tier == "t2":
        target, streak, weight = 8, 0, lift.start or 0.0
        for k, h in enumerate(history):
            est_k = _est1rm_from_history(history[:k + 1]) or 0.0
            ns = t2_next(T2State(target, streak, weight), h.reps, est_k,
                         fail=profile.t2_fail, incr=eff_incr,
                         reset_pct=profile.t2_reset_pct, quantum=eff_incr)
            target, streak, weight = ns.target, ns.streak, ns.weight
        return LiftState(name=lift.name, tier="t2", weight=weight, target=target,
                         streak=streak, est1rm=est, history=history)
    raise ValueError(f"recompute_state not applicable to tier {lift.tier!r}")
```

- [x] **Step 5: 运行测试，确认全绿（含既有零回归）**

Run: `conda run -n sbs python -m pytest tests/test_program.py -v`
Expected: PASS（全部，含既有 `test_advance_t3_uses_profile_target_and_incr`、`test_recompute_state_t3_replays_hits_and_misses`、`test_advance_t2_reset_uses_best_set_est1rm` 等——它们用默认 `profile.incr`/`Lift(incr=None)` → eff_incr 回退到 profile.incr，结果与旧实现一致）。

- [x] **Step 6: 提交**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "feat(engine): resolve eff_incr at advance_lift/recompute_state entry"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 4: db.py _SCHEMA lifts.incr + test_db.py 列断言

> `_SCHEMA` 的 lifts 表加 `incr REAL` 列（供新 DB / init_schema）。同步在 `test_db.py` 的列断言里加 incr（既有 `test_init_schema_has_lift_kind_and_reseeded_cycle_columns`）。

**注意：** Design Doc 把列断言记作 "test_columns.py"，但 `tests/test_columns.py` 实际测的是 spreadsheet 列（`tools/sbs_gzclp.columns`），与 DB 无关。DB 列断言真实位置是 `tests/test_db.py:30` 的 `test_init_schema_has_lift_kind_and_reseeded_cycle_columns`。

**Files:**
- Modify: `webapp/db.py:25-38`（lifts 表 DDL）、`webapp/db.py:86-104`（init_schema 无需改——CREATE TABLE IF NOT EXISTS + INSERT settings 不涉及 incr）
- Test: `tests/test_db.py:30-37`（扩展现有列断言测试）

**Interfaces:**
- Produces: lifts 表多一列 `incr REAL`（nullable）。下游 `repo.py`（Task 5）读写它；`tier.derive_state` 直接从 `repo.get_lift` 返回的 Row 读 `lift["incr"]`（Task 7）。

- [x] **Step 1: 改 `webapp/db.py` 的 lifts 表 DDL**

把：

```sql
CREATE TABLE IF NOT EXISTS lifts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    tier       TEXT NOT NULL CHECK (tier IN ('sbs','t2','t3')),
    day        INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    sets       INTEGER NOT NULL DEFAULT 3,
    max        REAL,
    intensity  REAL,
    reps       INTEGER,
    repout     INTEGER,
    start      REAL,
    lift_kind  TEXT
);
```

改为（末尾加 `incr REAL`）：

```sql
CREATE TABLE IF NOT EXISTS lifts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    tier       TEXT NOT NULL CHECK (tier IN ('sbs','t2','t3')),
    day        INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    sets       INTEGER NOT NULL DEFAULT 3,
    max        REAL,
    intensity  REAL,
    reps       INTEGER,
    repout     INTEGER,
    start      REAL,
    lift_kind  TEXT,
    incr       REAL
);
```

- [x] **Step 2: 扩展 `tests/test_db.py` 的列断言测试**

把 `tests/test_db.py` 中：

```python
def test_init_schema_has_lift_kind_and_reseeded_cycle_columns(tmp_path):
    """lifts.lift_kind and lift_state.reseeded_cycle exist with correct defaults (Task 5)."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lift_cols = {r[1] for r in conn.execute("PRAGMA table_info(lifts)").fetchall()}
    state_cols = {r[1] for r in conn.execute("PRAGMA table_info(lift_state)").fetchall()}
    assert "lift_kind" in lift_cols
    assert "reseeded_cycle" in state_cols
```

改为（追加 incr 断言；incr 是 nullable 所以无默认，仅断言列存在）：

```python
def test_init_schema_has_lift_kind_reseeded_cycle_and_incr_columns(tmp_path):
    """lifts.lift_kind + lifts.incr and lift_state.reseeded_cycle exist (Task 5 / per-lift incr)."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lift_cols = {r[1] for r in conn.execute("PRAGMA table_info(lifts)").fetchall()}
    state_cols = {r[1] for r in conn.execute("PRAGMA table_info(lift_state)").fetchall()}
    assert "lift_kind" in lift_cols
    assert "incr" in lift_cols          # per-lift t2/t3 progression step (nullable)
    assert "reseeded_cycle" in state_cols
```

- [x] **Step 3: 运行测试，确认全绿**

Run: `conda run -n sbs python -m pytest tests/test_db.py -v`
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add webapp/db.py tests/test_db.py
git commit -m "feat(db): add lifts.incr column to schema bootstrap"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 5: repo.py _LIFT_COLS + create_lift incr（TDD）

> `_LIFT_COLS` 加 `incr`（`update_lift` 经此自动支持 incr）；`create_lift` 加 `incr=None` 关键字参数与 INSERT 列。签名是 keyword-only 且新参数带默认值，所有既有调用方零改动。

**Files:**
- Modify: `webapp/repo.py:31-46`（`_LIFT_COLS` + `create_lift`）
- Test: `tests/test_repo.py`（追加测试）

**Interfaces:**
- Consumes: lifts.incr 列（Task 4）。
- Produces: `create_lift(..., incr=None) -> int`（keyword-only，默认 None）；`_LIFT_COLS` 含 incr，故 `update_lift(conn, lid, incr=...)` / `update_lift(conn, lid, incr=None)` 可用。下游：`advance._lift_from_row`（Task 6，但读 Row 不经 create_lift）、`tier.derive_state`（Task 7，经 `repo.get_lift` Row 读 `lift["incr"]`）、路由（Task 8）。

- [x] **Step 1: 写失败测试（追加到 `tests/test_repo.py` 末尾）**

```python
# ---------- per-lift incr ----------

def test_create_lift_accepts_incr_and_round_trips(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=30.0, incr=5.0)
        assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_create_lift_incr_defaults_null(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curls", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=40.0)  # no incr -> NULL -> inherit global
        assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_changes_incr(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0)
        repo.update_lift(conn, lid, incr=5.0)
        assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_update_lift_can_clear_incr_to_null(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0, incr=5.0)
        repo.update_lift(conn, lid, incr=None)
        assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_rejects_unknown_column(app):
    # _LIFT_COLS 守卫：incr 已纳入，但拼错的列名仍必须拒绝
    from webapp.db import connect
    import pytest
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0)
        with pytest.raises(ValueError):
            repo.update_lift(conn, lid, not_a_column=1)
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -k "incr or unknown_column" -v`
Expected: FAIL — `test_create_lift_accepts_incr_and_round_trips`（`create_lift` 不接受 incr kwarg）、`test_update_lift_changes_incr`（`_LIFT_COLS` 不含 incr → `update_lift` 抛 ValueError）。

- [x] **Step 3: 改 `webapp/repo.py` 的 `_LIFT_COLS` 与 `create_lift`**

把：

```python
_LIFT_COLS = ("name", "tier", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start", "lift_kind")


def create_lift(conn: sqlite3.Connection, *, name: str, tier: str, day: int,
                sort_order: int, sets: int, max, intensity, reps, repout,
                start, lift_kind=None) -> int:
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind),
    )
    lid = cur.lastrowid
    _init_lift_state(conn, lid, tier, max, start)
    conn.commit()
    return lid
```

改为：

```python
_LIFT_COLS = ("name", "tier", "day", "sort_order", "sets",
              "max", "intensity", "reps", "repout", "start", "lift_kind", "incr")


def create_lift(conn: sqlite3.Connection, *, name: str, tier: str, day: int,
                sort_order: int, sets: int, max, intensity, reps, repout,
                start, lift_kind=None, incr=None) -> int:
    cur = conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, tier, day, sort_order, sets, max, intensity, reps, repout, start, lift_kind, incr),
    )
    lid = cur.lastrowid
    _init_lift_state(conn, lid, tier, max, start)
    conn.commit()
    return lid
```

- [x] **Step 4: 运行测试，确认全绿（含既有零回归）**

Run: `conda run -n sbs python -m pytest tests/test_repo.py -v`
Expected: PASS（全部；既有 create_lift 调用因新参数带默认 None 而不受影响）。

- [x] **Step 5: 提交**

```bash
git add webapp/repo.py tests/test_repo.py
git commit -m "feat(repo): persist per-lift incr in lifts table"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 6: advance.py _lift_from_row 读 incr + recompute.py 零改动验证

> `_lift_from_row` 把行里的 `incr` 填入 `Lift`。`recompute.py` 不改一行——它经 `_lift_from_row`（接入 incr）+ `recompute_state`（Task 3 解析 eff_incr）自动继承，仅需加一个验证测试锁定该路径。

**Files:**
- Modify: `webapp/services/advance.py:8-14`（`_lift_from_row`）
- Test: `tests/test_recompute_service.py`（追加验证测试）

**Interfaces:**
- Consumes: `Lift.incr`（Task 2）、`repo.get_lift` 返回的 incr 列（Task 5）。
- Produces: `_lift_from_row` 产出的 `Lift` 携带 incr；`recompute_on_start_change` 自动按 eff_incr 重放（经 Task 3 的 `recompute_state`）。

- [x] **Step 1: 改 `webapp/services/advance.py` 的 `_lift_from_row`**

把：

```python
def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"],
    )
```

改为（末尾加 `incr=r["incr"]`）：

```python
def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], tier=r["tier"], day=r["day"], max=r["max"],
        intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"], incr=r["incr"],
    )
```

- [x] **Step 2: 写验证测试（追加到 `tests/test_recompute_service.py` 末尾）**

先读 `tests/test_recompute_service.py` 顶部确认其 import 与 fixture 风格（它用 `tmp_path` + `db.connect`/`db.init_schema` + `repo.create_lift` + `advance.advance_week` 模式）。追加：

```python
def test_recompute_on_start_change_uses_per_lift_incr(tmp_path):
    """recompute 服务经 _lift_from_row(incr) + recompute_state(eff_incr) 自动继承 per-lift incr。
    锁定 recompute.py 零改动路径（D3）：编辑 start 后重放按 lift.incr=5 累加，而非全局 2.5。"""
    from webapp.services import recompute as recompute_service
    from webapp.services import advance
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Curls", tier="t3", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=40.0, incr=5.0)
    # 一次命中 -> history；advance 用 eff_incr=5 -> 40+5=45
    advance.advance_week(conn, {lid: 16})
    repo.set_week(conn, 1)
    # 编辑 start=20 -> 重放：20 + 5（per-lift incr）= 25
    ls = recompute_service.recompute_on_start_change(conn, lid, 20.0)
    assert ls is not None and ls.weight == 25.0  # 不是 20+2.5=22.5
    assert repo.get_lift_state(conn, lid)["weight"] == 25.0
    conn.close()
```

- [x] **Step 3: 运行测试，确认全绿**

Run: `conda run -n sbs python -m pytest tests/test_recompute_service.py tests/test_advance_service.py -v`
Expected: PASS（`test_recompute_on_start_change_uses_per_lift_incr` 验证了零改动继承路径；既有 `test_advance_service.py` 因默认 incr=None→全局 而零回归）。

- [x] **Step 4: 提交**

```bash
git add webapp/services/advance.py tests/test_recompute_service.py
git commit -m "feat(advance): _lift_from_row carries incr; verify recompute auto-inherits"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 7: tier.py derive_state eff_incr snap（TDD）

> `derive_state` 把 t2/t3 起始推导的 snap 网格由全局 rounding 改为 eff_incr（`lift["incr"] if not None else settings["incr"]`）。sbs 分支不动。`apply_switch` 不加特例——incr 在 lifts 列，tier 切换只改 lifts.tier 与 lift_state，incr 自动保留（D6）。

**Files:**
- Modify: `webapp/services/tier.py:9-39`（derive_state 的 t2/t3 分支）
- Test: `tests/test_tier_service.py`（追加测试）

**Interfaces:**
- Consumes: `repo.get_lift` 返回的 Row 含 incr 列（Task 4/5）；`settings["incr"]`（既有 settings 字段）。
- Produces: `derive_state` 的 t2/t3 起始重量 snap 到 eff_incr 网格。

- [x] **Step 1: 写失败测试（追加到 `tests/test_tier_service.py` 末尾）**

```python
def test_derive_state_t2_snaps_to_eff_incr(tmp_path):
    """t2 derive：incr=5 的动作，起始重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5。"""
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn, _ = _seed_with_history(tmp_path)  # 复用既有 fixture 建一个 sbs lift+history
    # 另建一个 incr=5 的 t2 动作，灌入产生已知 est1rm 的 history
    lid = repo.create_lift(conn, name="PD", tier="t2", day=1, sort_order=1,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=100.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # 100x5 -> est1rm≈115
    settings = repo.get_settings(conn)
    preview = tier.derive_state(conn, lid, "t2", settings)
    est = _est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * settings["t2_reset_pct"], 5)   # eff_incr=5
    assert preview["weight"] != round_weight(est * settings["t2_reset_pct"], 2.5)  # 旧全局 rounding
    conn.close()


def test_derive_state_t3_snaps_to_eff_incr(tmp_path):
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.program import _est1rm_from_history
    from sbs_cli.data.schema import SetEntry
    conn = db.connect(str(tmp_path / "t2.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="FP", tier="t3", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=30.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=100.0, reps=5)  # est1rm≈115 -> *0.6≈69
    settings = repo.get_settings(conn)
    preview = tier.derive_state(conn, lid, "t3", settings)
    est = _est1rm_from_history([SetEntry(1, 100.0, 5)])
    assert preview["weight"] == round_weight(est * 0.6, 5)   # eff_incr=5 网格
    conn.close()


def test_apply_switch_preserves_incr(tmp_path):
    """D6：tier 切换不触碰 lifts.incr 列。"""
    conn = db.connect(str(tmp_path / "t3.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="PD", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None,
                           start=50.0, incr=5)
    repo.append_history(conn, lid, week=1, weight=50.0, reps=8)
    preview = tier.derive_state(conn, lid, "t3", repo.get_settings(conn))
    tier.apply_switch(conn, lid, preview)
    assert repo.get_lift(conn, lid)["incr"] == 5   # preserved across switch
    conn.close()
```

> 注：`_seed_with_history` 是 `tests/test_tier_service.py` 既有的 fixture 函数（建一个 sbs Squat + history），这里只为拿到一个 init 过 schema 的 conn；新动作 PD 重建在同一个 conn 里。

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_tier_service.py -k "snaps_to_eff_incr or preserves_incr" -v`
Expected: FAIL — `test_derive_state_t2_snaps_to_eff_incr`（旧实现 `quantum = settings["rounding"]=2.5` → snap 到 2.5 网格，断言要求 5 网格）。`test_apply_switch_preserves_incr` 应已绿（apply_switch 本就不触碰 incr 列——characterization 锁定 D6）。

- [x] **Step 3: 改 `webapp/services/tier.py` 的 `derive_state`**

把：

```python
    lift = repo.get_lift(conn, lift_id)
    quantum = settings["rounding"]

    if new_tier == "sbs":
        # See ADR 0001 — est1rm seed here is deliberate; unification with the
        # engine's max-replay is deferred. Do not "fix" without reading the ADR.
        tm = est1rm if est1rm is not None else (lift["max"] or 0.0)
        return {"tier": "sbs", "tm": tm, "weight": None, "target": None,
                "streak": 0, "est1rm": est1rm}
    if new_tier == "t2":
        if est1rm is not None:
            w = round_weight(est1rm * settings["t2_reset_pct"], quantum)
        else:
            w = lift["start"] or 0.0
        return {"tier": "t2", "tm": None, "weight": w, "target": 10,
                "streak": 0, "est1rm": est1rm}
    # t3
    if est1rm is not None:
        w = round_weight(est1rm * 0.6, quantum)
    else:
        w = lift["start"] or 0.0
    return {"tier": "t3", "tm": None, "weight": w, "target": None,
            "streak": 0, "est1rm": est1rm}
```

改为（t2/t3 用 eff_incr 作 snap 网格；sbs 分支不变）：

```python
    lift = repo.get_lift(conn, lift_id)
    # ADR 0003: t2/t3 derived start weights snap to this lift's effective-step grid
    # (per-lift incr ?? global incr), NOT the global rounding. sbs ignores incr.
    eff_incr = lift["incr"] if lift["incr"] is not None else settings["incr"]

    if new_tier == "sbs":
        # See ADR 0001 — est1rm seed here is deliberate; unification with the
        # engine's max-replay is deferred. Do not "fix" without reading the ADR.
        tm = est1rm if est1rm is not None else (lift["max"] or 0.0)
        return {"tier": "sbs", "tm": tm, "weight": None, "target": None,
                "streak": 0, "est1rm": est1rm}
    if new_tier == "t2":
        if est1rm is not None:
            w = round_weight(est1rm * settings["t2_reset_pct"], eff_incr)
        else:
            w = lift["start"] or 0.0
        return {"tier": "t2", "tm": None, "weight": w, "target": 10,
                "streak": 0, "est1rm": est1rm}
    # t3
    if est1rm is not None:
        w = round_weight(est1rm * 0.6, eff_incr)
    else:
        w = lift["start"] or 0.0
    return {"tier": "t3", "tm": None, "weight": w, "target": None,
            "streak": 0, "est1rm": est1rm}
```

（`apply_switch` 保持不变——D6：incr 在 lifts 列，apply_switch 只 update tier + lift_state。）

- [x] **Step 4: 运行测试，确认全绿（含既有零回归）**

Run: `conda run -n sbs python -m pytest tests/test_tier_service.py -v`
Expected: PASS（既有 `test_preview_tier_switch_preserves_history_basis`：sbs 默认 lift 无 incr → eff_incr=settings["incr"]=2.5=rounding，t2 weight 与旧实现一致）。

- [x] **Step 5: 提交**

```bash
git add webapp/services/tier.py tests/test_tier_service.py
git commit -m "feat(tier): derive t2/t3 start weights snap to eff_incr grid"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 8: routes/lifts.py new/edit 接 incr + 校验（TDD）

> `new`/`edit` 路由接 incr 字段。new：t2/t3 读 incr（>0 数值，空=None），sbs 强制 None。edit：incr 空=None（清除覆盖）、非空=>0 数值；≤0/非数字 → flash + 保留原值（400）。

**Files:**
- Modify: `webapp/routes/lifts.py:24-46`（new）、`webapp/routes/lifts.py:49-66`（edit）
- Test: `tests/test_routes_lifts.py`（追加测试）

**Interfaces:**
- Consumes: `repo.create_lift(..., incr=)` / `repo.update_lift(..., incr=)`（Task 5）。
- Produces: `/lifts/new` 与 `/lifts/<lid>/edit` 接受 `incr` 表单字段，校验后持久化。

- [x] **Step 1: 写失败测试（追加到 `tests/test_routes_lifts.py` 末尾）**

```python
def _t2_lift_with_incr(app, incr=None):
    from webapp.db import connect
    conn = connect(app.config["DB_PATH"])
    kwargs = dict(name="Rows", tier="t2", day=1, sort_order=0, sets=4,
                  max=None, intensity=None, reps=None, repout=None, start=85.0)
    if incr is not None:
        kwargs["incr"] = incr
    lid = repo.create_lift(conn, **kwargs)
    conn.close()
    return lid


def test_create_t2_with_incr(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Face Pull", "tier": "t3", "day": "2", "sets": "3", "start": "30", "incr": "5",
    })
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Face Pull")["incr"] == 5.0
        conn.close()


def test_create_sbs_does_not_write_incr(client, app):
    # 即使表单带了 incr，sbs 创建也必须写 None（incr 仅 t2/t3）
    rv = client.post("/lifts/new", data={
        "name": "Bench", "tier": "sbs", "day": "1", "sets": "5",
        "max": "100", "lift_kind": "main", "incr": "5",
    })
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Bench")["incr"] is None
        conn.close()


def test_create_rejects_nonpositive_incr(client, app):
    rv = client.post("/lifts/new", data={
        "name": "Bad", "tier": "t3", "day": "1", "sets": "3", "start": "30", "incr": "0",
    })
    assert rv.status_code == 400
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift_by_name(conn, "Bad") is None  # not created
        conn.close()


def test_edit_changes_incr(client, app):
    lid = _t2_lift_with_incr(app)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": "5"})
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] == 5.0
        conn.close()


def test_edit_clears_incr_to_null(client, app):
    lid = _t2_lift_with_incr(app, incr=5.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": ""})  # empty -> NULL
    assert rv.status_code == 200
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] is None
        conn.close()


def test_edit_rejects_nonpositive_incr_and_preserves_original(client, app):
    lid = _t2_lift_with_incr(app, incr=5.0)
    rv = client.post(f"/lifts/{lid}/edit", data={"incr": "-1"})
    assert rv.status_code == 400
    with app.app_context():
        from webapp.db import connect
        conn = connect(app.config["DB_PATH"])
        assert repo.get_lift(conn, lid)["incr"] == 5.0  # original preserved
        conn.close()
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -k "incr or nonpositive or clears_incr" -v`
Expected: FAIL — 路由尚未读 incr 字段，断言的 incr 值不匹配（或 `create_lift` 收到意外 kwarg 之前的旧签名——但 Task 5 已让 create_lift 接受 incr，所以这里主要是路由没传）。

- [x] **Step 3: 改 `webapp/routes/lifts.py` 的 `new`**

在文件顶部、`_f` 之后加一个 incr 解析+校验 helper（供 new/edit 共用）：

```python
def _parse_incr(raw: str):
    """Parse the incr form field. Returns (value, error).

    value: None (empty -> NULL / inherit global), a positive float, or None-with-error.
    error: None on success, a flash message string on validation failure."""
    raw = (raw or "").strip()
    if raw == "":
        return None, None
    try:
        v = float(raw)
    except ValueError:
        return None, "incr 必须是数字"
    if v <= 0:
        return None, "incr 必须大于 0"
    return v, None
```

把 `new()` 改为（t2/t3 解析 incr；sbs 强制 None；非法 → 400）：

```python
@bp.route("/lifts/new", methods=["POST"])
def new():
    conn = get_db()
    name = request.form.get("name", "").strip()
    tier = request.form.get("tier", "sbs")
    if tier not in ("sbs", "t2", "t3"):
        flash("tier 必须是 sbs / t2 / t3")
        return render_template("_lift_row.html", lift=None, error="bad tier"), 400
    if not name:
        flash("动作名不能为空")
        return render_template("_lift_row.html", lift=None, error="name required"), 400
    # incr 仅 t2/t3 生效；sbs 强制 None（D5）。空=None=继承全局；>0 数值；≤0/非数字 拒绝（D7）。
    incr, err = (None, None) if tier == "sbs" else _parse_incr(request.form.get("incr"))
    if err is not None:
        flash(err)
        return render_template("_lift_row.html", lift=None, error="bad incr"), 400
    try:
        lid = repo.create_lift(
            conn, name=name, tier=tier, day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float),
            lift_kind=_f("lift_kind") if tier == "sbs" else None, incr=incr)
    except Exception as e:
        flash(f"创建失败: {e}")
        return render_template("_lift_row.html", lift=None, error=str(e)), 400
    lift = repo.get_lift(conn, lid)
    return render_template("_lift_row.html", lift=lift)
```

- [x] **Step 4: 改 `webapp/routes/lifts.py` 的 `edit`**

把 `edit()` 改为（在通用列循环之外单独处理 incr：空→NULL、非空→>0 校验、非法→保留原值 400）：

```python
@bp.route("/lifts/<int:lid>/edit", methods=["POST"])
def edit(lid):
    conn = get_db()
    fields = {}
    for col, cast in (("name", str), ("tier", str), ("day", int), ("sets", int),
                      ("max", float), ("intensity", float), ("reps", int),
                      ("repout", int), ("start", float), ("lift_kind", str)):
        if col in request.form and request.form[col].strip() != "":
            fields[col] = cast(request.form[col])
    # incr：表单出现即处理。空串 -> NULL（清除覆盖回全局）；非空 -> 必须 >0 数字（D7）。
    # 校验在 update 之前，非法时保留原值并返回 400。
    if "incr" in request.form:
        incr, err = _parse_incr(request.form["incr"])
        if err is not None:
            flash(err)
            return render_template("_lift_row.html", lift=repo.get_lift(conn, lid),
                                   error="bad incr"), 400
        fields["incr"] = incr  # None 表示清除（update_lift 经 _LIFT_COLS 支持 incr=None）
    repo.update_lift(conn, lid, **fields)
    lift = repo.get_lift(conn, lid)
    # start is the progression basis for t2/t3: replay from the new start over
    # history to resync the working weight. Idempotent (no-op effect if start
    # unchanged). sbs has no start-based progression -> skipped.
    if lift["tier"] in ("t2", "t3") and "start" in fields:
        from ..services import recompute as recompute_service
        recompute_service.recompute_on_start_change(conn, lid, lift["start"])
    return render_template("_lift_row.html", lift=lift)
```

- [x] **Step 5: 运行测试，确认全绿（含既有零回归）**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py -v`
Expected: PASS（全部；既有 `test_create_sbs_persists_lift_kind`、`test_edit_changes_lift_kind`、`test_edit_start_t2_recomputes_weight` 等不受影响——它们的表单不带 incr 字段，edit 的 `if "incr" in request.form` 跳过）。

- [x] **Step 6: 提交**

```bash
git add webapp/routes/lifts.py tests/test_routes_lifts.py
git commit -m "feat(routes): /lifts new/edit accept incr with validation"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 9: 模板 _lift_row.html + lifts.html incr UI

> 编辑行与新建表单为 t2/t3 加 incr number 框；sbs 隐藏。清空框 = NULL = 继承全局。

**Files:**
- Modify: `webapp/templates/_lift_row.html`
- Modify: `webapp/templates/lifts.html`

**Interfaces:**
- Consumes: 路由（Task 8）读写 `incr` 表单字段；`lift.incr`（sqlite Row，经 Jinja2 getattr→getitem fallback 读 `lift["incr"]`）。

- [x] **Step 1: 改 `webapp/templates/_lift_row.html`（编辑行 + meta 行）**

把 meta 行中的 t2/t3 分支：

```jinja
    {% else %} | start {{ lift.start }}
    {% endif %}
```

改为（显示 incr 或「全局」）：

```jinja
    {% else %} | start {{ lift.start }} | incr {{ lift.incr if lift.incr is not none else '全局' }}
    {% endif %}
```

把编辑表单中的 t2/t3 分支（含 intensity/reps/repout）：

```jinja
    {% else %}
      <input name="intensity" type="number" step="0.05" value="{{ lift.intensity or '' }}" style="width:70px">
      <input name="reps" type="number" value="{{ lift.reps or '' }}" style="width:50px">
      <input name="repout" type="number" value="{{ lift.repout or '' }}" style="width:60px">
    {% endif %}
```

改为（在 repout 后加 incr 框；空值=NULL）：

```jinja
    {% else %}
      <input name="intensity" type="number" step="0.05" value="{{ lift.intensity or '' }}" style="width:70px">
      <input name="reps" type="number" value="{{ lift.reps or '' }}" style="width:50px">
      <input name="repout" type="number" value="{{ lift.repout or '' }}" style="width:60px">
      <input name="incr" type="number" step="0.5" value="{{ lift.incr if lift.incr is not none else '' }}" style="width:70px" placeholder="incr">
    {% endif %}
```

> sbs 分支（`{% if lift.tier == 'sbs' %}`）**不动**——incr 框只出现在 `{% else %}`（t2/t3）分支，sbs 行天然不渲染。

- [x] **Step 2: 改 `webapp/templates/lifts.html`（新建表单）**

把新建表单中的 start 输入：

```jinja
  <input name="start" type="number" step="0.5" placeholder="start(t2/t3)" style="width:90px">
```

之后追加一行 incr 输入（新建表单字段是静态展示，tier 在提交时才定；placeholder 标注 t2/t3 专用）：

```jinja
  <input name="start" type="number" step="0.5" placeholder="start(t2/t3)" style="width:90px">
  <input name="incr" type="number" step="0.5" placeholder="incr(t2/t3)" style="width:90px">
```

- [x] **Step 3: 跑模板相关测试确认无回归**

Run: `conda run -n sbs python -m pytest tests/test_html.py tests/test_routes_lifts.py -v`
Expected: PASS（`test_html.py` 渲染页面不涉及 incr 断言；既有 routes 测试的表单不带 incr 字段时，edit 的 `if "incr" in request.form` 跳过，new 的 t2/t3 解析到空→None）。

- [x] **Step 4: 提交**

```bash
git add webapp/templates/_lift_row.html webapp/templates/lifts.html
git commit -m "feat(ui): incr input on /lifts editor for t2/t3 (hidden for sbs)"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 10: migrate_incr.py 一次性列迁移 + 幂等测试（TDD）

> 新增 `migrate_incr.py`：`ALTER TABLE lifts ADD COLUMN incr REAL`，`PRAGMA table_info(lifts)` 守卫幂等（列已存在跳过）。沿用 `migrate_schedule.py` 的 `_column_exists`/备份/`--db`/`--backup-dir` 模式。

**Files:**
- Create: `migrate_incr.py`
- Test: `tests/test_migrate_incr.py`

**Interfaces:**
- Consumes: `webapp.db.connect` / `webapp.db.init_schema`（既有）。独立可执行脚本，不被其它模块 import。

- [x] **Step 1: 写失败测试 `tests/test_migrate_incr.py`**

```python
import sqlite3
from webapp import db


def _legacy_db(tmp_path):
    """Build a lifts table WITHOUT the incr column, mirroring a pre-migration DB."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id=1), week INTEGER NOT NULL,
            days_per_week INTEGER NOT NULL, rounding REAL NOT NULL, incr REAL NOT NULL,
            t2_reset_pct REAL NOT NULL, t2_fail INTEGER NOT NULL, t3_target INTEGER NOT NULL);
        INSERT INTO settings VALUES (1, 1, 4, 2.5, 2.5, 0.75, 3, 15);
        CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            tier TEXT NOT NULL, day INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            sets INTEGER NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INTEGER,
            repout INTEGER, start REAL, lift_kind TEXT);
        CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT NOT NULL, tm REAL,
            weight REAL, target INTEGER, streak INTEGER NOT NULL DEFAULT 0, est1rm REAL,
            reseeded_cycle INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INTEGER NOT NULL,
            week INTEGER NOT NULL, weight REAL NOT NULL, reps INTEGER NOT NULL, ts TEXT NOT NULL);
        CREATE TABLE week_log (lift_id INTEGER NOT NULL, week INTEGER NOT NULL, reps INTEGER NOT NULL,
            PRIMARY KEY (lift_id, week));
        CREATE TABLE sbs_schedule (kind TEXT NOT NULL, week INTEGER NOT NULL, intensity REAL NOT NULL,
            reps INTEGER NOT NULL, repout INTEGER NOT NULL, PRIMARY KEY (kind, week));
        INSERT INTO lifts (name, tier, day, sets, start) VALUES ('Rows', 't2', 1, 4, 85.0);
    """)
    conn.commit()
    conn.close()
    return path


def _has_incr(conn):
    return any(r[1] == "incr" for r in conn.execute("PRAGMA table_info(lifts)"))


def test_migrate_adds_incr_column(tmp_path, monkeypatch):
    path = _legacy_db(tmp_path)
    import migrate_incr
    monkeypatch.chdir(tmp_path)
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    # existing rows keep NULL incr (inherit global)
    row = conn.execute("SELECT incr FROM lifts WHERE name='Rows'").fetchone()
    assert row[0] is None
    conn.close()


def test_migrate_idempotent_on_already_migrated(tmp_path, monkeypatch):
    path = _legacy_db(tmp_path)
    import migrate_incr
    monkeypatch.chdir(tmp_path)
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))  # second run no-op
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    conn.close()


def test_migrate_idempotent_on_fresh_schema(tmp_path, monkeypatch):
    # a DB created by init_schema already has incr -> migrate is a no-op
    path = str(tmp_path / "fresh.db")
    conn = db.connect(path)
    db.init_schema(conn)
    conn.close()
    import migrate_incr
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    conn.close()
```

- [x] **Step 2: 运行测试，确认红**

Run: `conda run -n sbs python -m pytest tests/test_migrate_incr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_incr'`。

- [x] **Step 3: 创建 `migrate_incr.py`**

```python
"""One-shot migration: add the nullable ``lifts.incr REAL`` column to a live ``sbs.db``.

The per-lift t2/t3 progression step. NULL = inherit the global ``settings.incr``
(live inheritance — re-read every advance). Existing rows get NULL, so every
existing lift keeps behaving exactly as before (eff_incr falls back to the global).

Idempotent: ``PRAGMA table_info(lifts)`` guards the ALTER — re-running is a no-op
once the column exists. Does NOT touch the live ``sbs.db`` except via the explicit
``--db`` flag. New DBs get the column from ``db.init_schema`` directly.

Run:  conda run -n sbs python migrate_incr.py
      conda run -n sbs python migrate_incr.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sys
import sqlite3
from datetime import datetime, timezone

from webapp import db


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def _add_incr(conn: sqlite3.Connection) -> bool:
    """``ALTER TABLE lifts ADD COLUMN incr REAL``. Idempotent. Returns True if added."""
    if _column_exists(conn, "lifts", "incr"):
        return False
    conn.execute("ALTER TABLE lifts ADD COLUMN incr REAL")
    conn.commit()
    return True


def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-incr-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")

    conn = db.connect(db_path)
    try:
        added = _add_incr(conn)
    finally:
        conn.close()
    # existing rows are NULL by default of the new nullable column -> inherit global
    print(f"migrated incr ({'added' if added else 'already present'}) -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_incr")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
```

- [x] **Step 4: 运行测试，确认全绿**

Run: `conda run -n sbs python -m pytest tests/test_migrate_incr.py -v`
Expected: PASS（三个：legacy 加列、重复跑幂等、fresh schema 幂等）。

- [x] **Step 5: 提交**

```bash
git add migrate_incr.py tests/test_migrate_incr.py
git commit -m "feat(migrate): one-shot ALTER to add lifts.incr (idempotent)"
```

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 11: migrate.py 审计（零改动验证）

> `migrate.py` 的两处 `repo.create_lift(...)` 调用（YAML 第 29-32 行、xlsx 第 77-79 行）经 Task 5 后自动获得 `incr=None` 默认。YAML/xlsx 源（`dio.load_profile` / `import_profile`）产出的 `Lift` 无 incr 信息（新字段默认 None），故传 None 正确表达"继承全局"。无需编辑。

**Files:**
- Read-only: `migrate.py`（确认无位置参数 create_lift 调用、无 incr 来源）

- [x] **Step 1: 跑迁移相关既有测试确认零回归**

Run: `conda run -n sbs python -m pytest tests/test_migrate.py tests/test_migrate_sbs_tm.py tests/test_migrate_recompute.py tests/test_migrate_schedule.py -v`
Expected: PASS（全部；`create_lift` 加 `incr=None` 默认后，既有调用零影响）。

- [x] **Step 2: 跑全量回归测试快照（在 UI/迁移完成后、验收前）**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS（全部测试，含本变更新增的 9 个测试落点）。

- [x] **Step 3: 若 Step 1/2 全绿则本 task 无代码改动，直接进入 Task 12**

> 若发现任何 create_lift 位置参数调用（grep `create_lift(conn,` 在 migrate.py 中无位置参数——均 keyword），则按 Design Doc D4 显式补 `incr=None`。当前 `migrate.py:29-32` 与 `migrate.py:77-79` 均 keyword 且末尾为 `lift_kind=l.lift_kind`，默认 None 正确，**不编辑**。

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Task 12: 验收（全量测试 + 手动冒烟）

**Files:**
- 无（验证 only）

- [x] **Step 1: 全量测试**

Run: `conda run -n sbs python -m pytest -v`
Expected: PASS（全部；重点确认 9 个落点的新增测试与既有零回归）。

- [x] **Step 2: 手动冒烟（本地 webapp）**

启动 webapp（项目既有启动方式；通常是 `conda run -n sbs python -m webapp` 或等价——按项目 README/既有方式），在 `/lifts` 页面：

1. 编辑一个 t2/t3 动作（如 Face Pull）设 `incr=5`，保存 → 下周命中后工作重量 +5（而非 +2.5）。
2. 其他 t2/t3 动作不设 incr（留空）→ 仍按全局 `+2.5` 增长。
3. sbs 动作行无 incr 输入框；sbs 工作重量不受 incr 影响。
4. 清空一个已设 incr=5 的动作的 incr 框并保存 → 回到全局 `+2.5`。
5. 提交 `incr=0` 或 `incr=abc` → 被 flash 拒绝、原值保留。
6. 既有流程不回归：`/plan` 渲染、`/reseed`、`/schedule`、advance week 正常。

- [x] **Step 3: 若已有本地 sbs.db，跑迁移脚本验证**

```bash
conda run -n sbs python migrate_incr.py --db sbs.db --backup-dir backups
```

Expected: 输出 `backup -> ...` 与 `migrated incr (added) -> sbs.db`；重复执行输出 `already present`（幂等）。验证 lifts 表多出 `incr` 列、既有行 incr 为 NULL。

- [x] **Step 4: 最终提交（如有验收中发现的修复）**

若手动冒烟发现缺陷，回到对应 task 修复并加载 `superpowers:systematic-debugging` skill（根因定位后再改）。无缺陷则无需提交。

archived-with: 2026-07-11-per-lift-t2t3-increment
---

## Self-Review

**Spec coverage**（逐条对照 spec.md requirement）：

- 「Per-lift increment override with global fallback」→ Task 2（字段）+ Task 3（eff_incr 解析）+ Task 5（持久化）+ Task 8（路由清空回 NULL + 非法拒绝）。
- 「t2/t3 命中加重量不做 rounding」→ Task 1（progression 去 snap）+ Task 3（advance/recompute 传 eff_incr 不 snap）。
- 「t2 reset 与 tier 切换起始重量 snap 到有效步长」→ Task 3（recompute reset 用 eff_incr quantum）+ Task 7（derive_state 用 eff_incr）+ Task 0（spec 回写）。
- 「重算历史使用有效步长」→ Task 3（recompute_state）+ Task 6（recompute 服务自动继承验证）。
- 「incr 字段仅适用于 t2/t3」→ Task 3（sbs 分支不沾）+ Task 8（sbs 强制 None）+ Task 9（UI sbs 隐藏）。
- 新增「tier 切换保留 incr」场景 → Task 7（apply_switch 不动 + 测试）+ Task 0（spec 回写）。

**Placeholder 扫描**：无 TBD/TODO；每个代码 step 均含完整代码与命令。

**类型/签名一致性**：
- `t3_next` 新签名 `(weight, actual, target=15, incr=2.5)`——Task 1 定义，Task 3 调用方不再传 quantum ✓。
- `t2_next` 签名不变（保留 quantum）——Task 1 HIT 分支改、reset 不动；Task 3 调用方传 `quantum=eff_incr` ✓。
- `Lift.incr`——Task 2 定义；Task 3（program 读 `lift.incr`）、Task 5（repo 写）、Task 6（`_lift_from_row` 读 `r["incr"]`）、Task 7（tier 读 `lift["incr"]`）一致 ✓。
- `create_lift(..., incr=None)`——Task 5 定义；Task 8（路由传 incr=incr）、Task 10（迁移测试不直接用）、Task 11（migrate.py 默认 None）一致 ✓。
- `_LIFT_COLS` 含 incr——Task 5；`update_lift(incr=...)` / `update_lift(incr=None)` 经此自动支持 ✓。

