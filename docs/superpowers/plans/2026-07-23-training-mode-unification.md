# 训练模式统一重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把训练行为从 tier+progression+bodyweight_pct 三字段重叠模型， 重构为 `load_model` × `mode` 双正交枚举 + 注册表分派， 并给纯自重动作一等位置。

**Architecture:** 引擎新增 `sbs_cli/engine/modes.py`, 每个 progression mode 一个 handler (实现 initial_state / advance / plan_item / derive_on_switch 四接口), 经 `PROGRESSION_REGISTRY` 单点查表分派。载荷仍走 `working_weight()` seam (ADR 0004)。`Lift`/`LiftState`/DB 用 `load_model`+`mode` 取代 `tier`+`progression`。一次性迁移脚本重建 lifts 表。

**Tech Stack:** Python 3, Flask + HTMX + SQLite (webapp), PyYAML (CLI), pytest。

## Global Constraints

- 测试一律 `conda run -n sbs python -m pytest tests/ -x -q` (env 名 `sbs`)。
- `load_model` ∈ {`barbell`, `bodyweight`, `pure_bodyweight`}; `mode` ∈ {`sbs`, `linear_t2`, `linear_t3`, `none`}。
- 合法组合 (引擎+表单强制， 非法拒绝): `barbell`→{sbs, linear_t2, linear_t3}; `bodyweight`→{linear_t2, linear_t3}; `pure_bodyweight`→{none}。`none`↔`pure_bodyweight` 一对一绑定。
- `mode=none` = 纯记录： advance 只 append history + 重算 est1rm, 不改 weight/target。
- `load_model` 创建后不可切换； 仅 `mode` 可在同 load_model 家族内切换。
- 纯自重视图显示 `bodyweight × bodyweight_pct`, 统一走 seam, 无视图特判。
- `bodyweight_pct` 保留为载荷参数 (非 mode 标志), 创建时手填默认 1.0。
- ADR 0001 (TM 全精度)、0002 (cycle reseed)、0003 (eff_incr snap grid)、0004 (working-weight seam) 语义全部保留。
- 迁移删除 `tier`/`progression` 列， `lift_state.tier` → `mode`; history 表不动。

---

### Task 1: schema — Lift/LiftState 双枚举字段

**Files:**
- Modify: `sbs_cli/data/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: 无 (叶子 dataclass)
- Produces: `Lift(load_model: str, mode: str, bodyweight_pct: float)` (删 `tier`, `progression`); `LiftState(mode: str)` (改自 `tier`); 模块级常量 `LOAD_MODELS`, `MODES`, `LEGAL_COMBOS: frozenset[tuple[str,str]]`, 校验函数 `is_legal_combo(load_model, mode) -> bool`

- [ ] **Step 1: 写失败测试**

`tests/test_schema.py` 追加:
```python
from sbs_cli.data.schema import (Lift, LiftState, LOAD_MODELS, MODES,
                                 LEGAL_COMBOS, is_legal_combo)

def test_lift_has_load_model_and_mode():
    l = Lift(name="Pull-up", load_model="pure_bodyweight", mode="none", day=1)
    assert l.load_model == "pure_bodyweight"
    assert l.mode == "none"
    assert l.bodyweight_pct == 0.0

def test_lift_defaults():
    l = Lift(name="Bench", day=1)
    assert l.load_model == "barbell"
    assert l.mode == "none"  # default; caller sets a legal one

def test_liftstate_mode_field():
    s = LiftState(name="x", mode="sbs", tm=100.0)
    assert s.mode == "sbs"

def test_legal_combos():
    assert is_legal_combo("barbell", "sbs")
    assert is_legal_combo("barbell", "linear_t2")
    assert is_legal_combo("barbell", "linear_t3")
    assert is_legal_combo("bodyweight", "linear_t2")
    assert is_legal_combo("bodyweight", "linear_t3")
    assert is_legal_combo("pure_bodyweight", "none")
    # illegal
    assert not is_legal_combo("barbell", "none")
    assert not is_legal_combo("bodyweight", "none")
    assert not is_legal_combo("bodyweight", "sbs")
    assert not is_legal_combo("pure_bodyweight", "sbs")
    assert not is_legal_combo("pure_bodyweight", "linear_t2")
    assert not is_legal_combo("pure_bodyweight", "linear_t3")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_schema.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'LOAD_MODELS'` 或 `TypeError: unexpected keyword 'load_model'`

- [ ] **Step 3: 改 schema**

`sbs_cli/data/schema.py` — `Lift` 替换字段定义, 文件顶部加常量:
```python
LOAD_MODELS = ("barbell", "bodyweight", "pure_bodyweight")
MODES = ("sbs", "linear_t2", "linear_t3", "none")

# Legal (load_model, mode) combos (ADR 0005). none↔pure_bodyweight bound 1:1;
# barbell/bodyweight must follow some progression; sbs is barbell-only.
LEGAL_COMBOS = frozenset({
    ("barbell", "sbs"), ("barbell", "linear_t2"), ("barbell", "linear_t3"),
    ("bodyweight", "linear_t2"), ("bodyweight", "linear_t3"),
    ("pure_bodyweight", "none"),
})

def is_legal_combo(load_model: str, mode: str) -> bool:
    return (load_model, mode) in LEGAL_COMBOS
```
`Lift`:
```python
@dataclass
class Lift:
    """A lift definition in profile.yaml (static)."""
    name: str
    day: int
    load_model: str = "barbell"   # "barbell" | "bodyweight" | "pure_bodyweight"
    mode: str = "none"            # "sbs" | "linear_t2" | "linear_t3" | "none"
    max: Optional[float] = None
    intensity: float = 0.0
    reps: int = 0
    repout: int = 0
    sets: int = 3
    start: Optional[float] = None
    lift_kind: Optional[str] = None   # "main" | "aux" for sbs; None otherwise
    incr: Optional[float] = None      # linear_t2/t3 per-lift step; None = inherit global
    # Load parameter (ADR 0004), NOT a mode marker. 0.0 barbell; >0 bodyweight
    # fraction (1.0 pull-up/dip, ~0.64 push-up). Hand-entered, default 1.0 for pure.
    bodyweight_pct: float = 0.0
```
`LiftState`: 字段 `tier: str` → `mode: str` (位置/类型不变)。

- [ ] **Step 4: 跑测试确认过**

Run: `conda run -n sbs python -m pytest tests/test_schema.py -x -q`
Expected: PASS (其余旧测试此时会因 tier/progression 引用失败 — 本任务只要求新增 4 个测试过; 旧测试在后续任务逐个修。用 `-k` 只跑新测试: `pytest tests/test_schema.py -k "load_model or defaults or legal or liftstate_mode" -q`)

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/data/schema.py tests/test_schema.py
git commit -m "feat(schema): dual load_model/mode enums + legal-combo table (ADR 0005)"
```

---

### Task 2: 引擎 modes 注册表

**Files:**
- Create: `sbs_cli/engine/modes.py`
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: `engine.progression.{sbs_next, t2_next, t3_next, T2State, round_weight, lookup_schedule}`, `engine.load.working_weight`, `program._est1rm_from_history`, schema `Lift/LiftState/Profile/is_legal_combo`
- Produces: `Mode` (base, 四方法), `SbsMode`, `LinearT2Mode`, `LinearT3Mode`, `RecordOnlyMode`, `PROGRESSION_REGISTRY: dict[str, Mode]`, `get_mode(name) -> Mode`

注: `plan_item` 返回类型复用 `program.PlanItem`。为避免循环 import, `modes.py` 不 import `program`; `PlanItem` 由调用方构造, handler 返回 dict 或让 `program` 传入构造函数。简化: handler 返回 `PlanItem` 所需字段的命名元组/dict, `program.week_plan` 负责包成 `PlanItem`。

- [ ] **Step 1: 写失败测试**

`tests/test_modes.py`:
```python
import pytest
from sbs_cli.data.schema import Lift, LiftState, Profile, ScheduleRow
from sbs_cli.engine.modes import PROGRESSION_REGISTRY, get_mode

def _sched():
    return [ScheduleRow(kind="main", week=1, intensity=0.70, reps=5, repout=10)]

def test_registry_keys():
    assert set(PROGRESSION_REGISTRY) == {"sbs", "linear_t2", "linear_t3", "none"}

def test_get_mode_unknown_raises():
    with pytest.raises(KeyError):
        get_mode("bogus")

def test_sbs_initial_state():
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", max=100.0)
    s = get_mode("sbs").initial_state(l, None)
    assert s.mode == "sbs" and s.tm == 100.0

def test_t2_initial_state():
    l = Lift(name="Bp", day=1, load_model="barbell", mode="linear_t2", start=60.0)
    s = get_mode("linear_t2").initial_state(l, None)
    assert s.mode == "linear_t2" and s.weight == 60.0 and s.target == 8

def test_t3_initial_state():
    l = Lift(name="Curl", day=1, load_model="barbell", mode="linear_t3", start=20.0)
    s = get_mode("linear_t3").initial_state(l, None)
    assert s.mode == "linear_t3" and s.weight == 20.0 and s.target is None

def test_none_initial_state():
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none")
    s = get_mode("none").initial_state(l, None)
    assert s.mode == "none" and s.target is None

def test_none_advance_records_only():
    p = Profile(bodyweight=75.0, schedule=_sched())
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none", bodyweight_pct=1.0)
    s = LiftState(name="Pu", mode="none", weight=0.0)
    get_mode("none").advance(p, l, s, 12, week=1)
    assert s.weight == 0.0            # no progression
    assert len(s.history) == 1        # recorded
    assert s.est1rm is not None       # est1rm recomputed (bw×pct=75 @12 reps)

def test_sbs_advance_tm():
    p = Profile(rounding=2.5, schedule=_sched())
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", lift_kind="main")
    s = LiftState(name="Sq", mode="sbs", tm=100.0)
    get_mode("sbs").advance(p, l, s, 12, week=1)   # repout=10, beat by 2 -> +1%
    assert s.tm == pytest.approx(101.0)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_modes.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sbs_cli.engine.modes'`

- [ ] **Step 3: 实现 modes.py**

`sbs_cli/engine/modes.py`:
```python
"""Progression-mode registry: single dispatch point for per-mode behaviour.

Each mode implements four operations: initial_state / advance / plan_item /
derive_on_switch. All load computation routes through the working_weight seam
(ADR 0004); progression through the pure functions in engine.progression.
Adding a mode = one handler class + one PROGRESSION_REGISTRY line. See ADR 0005.
"""
from ..data.schema import LiftState, SetEntry, is_legal_combo
from ..program import _est1rm_from_history
from .progression import (sbs_next, t2_next, t3_next, T2State,
                          round_weight, lookup_schedule)
from .load import working_weight


class Mode:
    """Base progression-mode handler. Subclasses override the four ops."""
    name = ""

    def initial_state(self, lift, settings) -> LiftState:
        raise NotImplementedError

    def advance(self, profile, lift, state, actual, week) -> None:
        raise NotImplementedError

    def plan_fields(self, profile, lift, state, week) -> dict:
        """Return {weight, reps, repout, target, streak} for week_plan display."""
        raise NotImplementedError

    def derive_on_switch(self, lift, history, settings, est1rm) -> dict:
        """Return the new-mode starting state dict (tm/weight/target/streak)."""
        raise NotImplementedError

    # shared helper: append history + recompute est1rm (used by every advance)
    def _record(self, profile, lift, state, actual, week, w) -> None:
        if actual is not None:
            from ..program import _est1rm_from_history
            state.history.append(type(state.history[0])(week=week, weight=w, reps=actual)
                                 if state.history else
                                 __import__("sbs_cli.data.schema", fromlist=["SetEntry"]).SetEntry(week, w, actual))
            state.est1rm = _est1rm_from_history(state.history,
                                                profile.bodyweight, lift.bodyweight_pct)


class SbsMode(Mode):
    name = "sbs"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="sbs", tm=lift.max)

    def advance(self, profile, lift, state, actual, week):
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
        self._record(profile, lift, state, actual, week, w)
        state.tm = sbs_next(state.tm, sc.repout, actual)

    def plan_fields(self, profile, lift, state, week):
        sc = lookup_schedule(profile.schedule, lift.lift_kind, week)
        w = round_weight((state.tm or 0) * sc.intensity, profile.rounding)
        return {"weight": w, "reps": sc.reps, "repout": sc.repout,
                "target": None, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        tm = est1rm if est1rm is not None else (lift.max or 0.0)  # ADR 0001
        return {"mode": "sbs", "tm": tm, "weight": None, "target": None, "streak": 0}


class LinearT2Mode(Mode):
    name = "linear_t2"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="linear_t2", weight=lift.start,
                         target=8, streak=0)

    def advance(self, profile, lift, state, actual, week):
        w = state.weight
        self._record(profile, lift, state, actual, week, w)
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        est = state.est1rm if state.est1rm is not None else 0.0
        ns = t2_next(T2State(state.target, state.streak, state.weight), actual, est,
                     fail=profile.t2_fail, incr=eff_incr,
                     reset_pct=profile.t2_reset_pct, quantum=eff_incr)
        state.target, state.streak, state.weight = ns.target, ns.streak, ns.weight

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        return {"weight": w, "reps": state.target, "repout": None,
                "target": state.target, "streak": state.streak}

    def derive_on_switch(self, lift, history, settings, est1rm):
        eff_incr = lift.incr if lift.incr is not None else settings["incr"]
        w = round_weight(est1rm * settings["t2_reset_pct"], eff_incr) \
            if est1rm is not None else (lift.start or 0.0)
        return {"mode": "linear_t2", "tm": None, "weight": w, "target": 8, "streak": 0}


class LinearT3Mode(Mode):
    name = "linear_t3"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="linear_t3", weight=lift.start)

    def advance(self, profile, lift, state, actual, week):
        w = state.weight
        self._record(profile, lift, state, actual, week, w)
        eff_incr = lift.incr if lift.incr is not None else profile.incr
        state.weight = t3_next(state.weight, actual,
                               target=profile.t3_target, incr=eff_incr)

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        return {"weight": w, "reps": profile.t3_target, "repout": None,
                "target": profile.t3_target, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        eff_incr = lift.incr if lift.incr is not None else settings["incr"]
        w = round_weight(est1rm * 0.6, eff_incr) \
            if est1rm is not None else (lift.start or 0.0)
        return {"mode": "linear_t3", "tm": None, "weight": w, "target": None, "streak": 0}


class RecordOnlyMode(Mode):
    """Pure-bodyweight record-only mode: no automatic progression (ADR 0005)."""
    name = "none"

    def initial_state(self, lift, settings):
        return LiftState(name=lift.name, mode="none", weight=lift.start)

    def advance(self, profile, lift, state, actual, week):
        # added weight stays 0 for pure bodyweight; only record + est1rm.
        w = state.weight or 0.0
        self._record(profile, lift, state, actual, week, w)
        # no weight/target mutation — record only

    def plan_fields(self, profile, lift, state, week):
        w = working_weight(state.weight or 0.0, profile.bodyweight, lift.bodyweight_pct)
        last = state.history[-1].reps if state.history else None
        return {"weight": w, "reps": last, "repout": None, "target": None, "streak": 0}

    def derive_on_switch(self, lift, history, settings, est1rm):
        return {"mode": "none", "tm": None, "weight": lift.start or 0.0,
                "target": None, "streak": 0}


PROGRESSION_REGISTRY = {m.name: m for m in
                        (SbsMode(), LinearT2Mode(), LinearT3Mode(), RecordOnlyMode())}


def get_mode(name: str) -> Mode:
    return PROGRESSION_REGISTRY[name]
```

注: `_record` 的 SetEntry 构造写得绕。更干净: 文件顶部 `from ..data.schema import SetEntry`, `_record` 直接 `state.history.append(SetEntry(week=week, weight=w, reps=actual))`。用这个版本替换上面 `_record` 体。

- [ ] **Step 4: 跑测试确认过**

Run: `conda run -n sbs python -m pytest tests/test_modes.py -x -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add sbs_cli/engine/modes.py tests/test_modes.py
git commit -m "feat(engine): progression-mode registry + 4 handlers (ADR 0005)"
```

---

### Task 3: program.py 接线注册表

**Files:**
- Modify: `sbs_cli/program.py`
- Test: `tests/test_program.py`

**Interfaces:**
- Consumes: `engine.modes.{PROGRESSION_REGISTRY, get_mode}`, schema 新字段
- Produces: `advance_lift`, `week_plan`, `initial_state`, `recompute_state` 全部经注册表/新字段; 签名不变 (外部调用方不动)

- [ ] **Step 1: 改 program.py**

- `initial_state`: 循环里 `if l.tier == "sbs"...` → `lifts[l.name] = get_mode(l.mode).initial_state(l, None)`
- `advance_lift`: 整体替换为:
```python
def advance_lift(profile, lift, state, actual_reps, week):
    get_mode(lift.mode).advance(profile, lift, state, actual_reps, week)
```
- `week_plan`: 循环里三分支 →
```python
f = get_mode(l.mode).plan_fields(profile, l, ls, state.week)
out.append(PlanItem(l.name, l.mode, f["weight"], f["reps"], l.sets,
                    f["repout"], f["target"], f["streak"], ls.est1rm))
```
- `recompute_state`: `lift.tier` 引用 → `lift.mode`; `LiftState(... tier=...)` → `mode=`; `raise ValueError(f"... mode {lift.mode!r}")`; 内部 `t2`/`t3` 字符串 → `linear_t2`/`linear_t3`
- `recompute_sbs_tm`: 不变 (无 tier 引用)
- `PlanItem` (program.py:74-79): `__slots__` 与 `__init__` 里 `tier` → `mode` (week_plan 构造处同步传 `l.mode`)。CLI view (Task 7) 读 `it.mode`。
- 顶部 import: `from .engine.modes import get_mode`

- [ ] **Step 2: 改测试 test_program.py**

全文 `tier=` → `mode=` (构造 Lift/LiftState); `"t2"`→`"linear_t2"`, `"t3"`→`"linear_t3"` (断言/构造里的 tier 值); `LiftState(name=..., tier=...)` → `mode=`。

- [ ] **Step 3: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_program.py tests/test_progression.py tests/test_modes.py -x -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add sbs_cli/program.py tests/test_program.py
git commit -m "refactor(program): dispatch progression via mode registry"
```

---

### Task 4: webapp schema (db.py) + repo 新列

**Files:**
- Modify: `webapp/db.py`, `webapp/repo.py`
- Test: `tests/test_db.py`, `tests/test_repo.py`

**Interfaces:**
- Consumes: schema 常量
- Produces: `lifts.load_model`, `lifts.mode` 列 (删 `tier`, `progression`); `lift_state.mode`; `repo.create_lift(..., load_model, mode, ...)` (删 `tier`/`progression` 参数), `_init_lift_state` 经注册表

- [ ] **Step 1: 改 db.py `_SCHEMA`**

`lifts` 表: 删 `tier ... CHECK`, `progression ... CHECK`; 加:
```
    load_model     TEXT NOT NULL DEFAULT 'barbell' CHECK (load_model IN ('barbell','bodyweight','pure_bodyweight')),
    mode           TEXT NOT NULL DEFAULT 'none' CHECK (mode IN ('sbs','linear_t2','linear_t3','none')),
```
`lift_state` 表: `tier TEXT NOT NULL` → `mode TEXT NOT NULL`。
`init_schema` 旧 `_add_column_if_missing` bodyweight 行保留 (老库仍可能缺), 但本重构迁移脚本 (Task 8) 负责重建表 — init_schema 不再加 tier/progression 列。删 init_schema 里 `_add_column_if_missing(conn,"lifts","progression",...)` 行; 保留 bodyweight_pct。

- [ ] **Step 2: 改 repo.py**

- `_LIFT_COLS`: `"tier"`→`"load_model","mode"`, 删 `"progression"`
- `create_lift`: 签名 `tier` → `load_model: str, mode: str`, 删 `progression`; INSERT 列同步; 加合法校验:
```python
from sbs_cli.data.schema import is_legal_combo
if not is_legal_combo(load_model, mode):
    raise ValueError(f"illegal load_model/mode: {load_model}/{mode}")
```
- `_init_lift_state`: 删 if/elif/else, 改经注册表:
```python
def _init_lift_state(conn, lid, lift):
    from sbs_cli.engine.modes import get_mode
    s = get_mode(lift.mode).initial_state(lift, None)
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, tm, weight, target, streak, est1rm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lid, s.mode, s.tm, s.weight, s.target, s.streak, s.est1rm))
```
`create_lift` 调用处改为先构造临时 Lift 或直接传参。简化: `_init_lift_state(conn, lid, mode, max, start)` 内联三分支→注册表:
```python
def _init_lift_state(conn, lid, mode, max, start):
    from sbs_cli.data.schema import Lift
    from sbs_cli.engine.modes import get_mode
    tmp = Lift(name="", day=1, load_model="barbell", mode=mode, max=max, start=start)
    s = get_mode(mode).initial_state(tmp, None)
    conn.execute(
        "INSERT INTO lift_state (lift_id, mode, tm, weight, target, streak, est1rm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lid, s.mode, s.tm, s.weight, s.target, s.streak, s.est1rm))
```
- `_STATE_COLS`: `"tier"`→`"mode"`; `save_lift_state` 参数 `tier` → `mode`, SQL 同步
- `set_reseed`: SQL `lift_state` 无 tier 引用 (只有 reseeded_cycle/max/tm) — 不变

- [ ] **Step 3: 改测试**

`tests/test_db.py`, `tests/test_repo.py`: `tier`→`mode`/`load_model`, `create_lift(tier="sbs")`→`create_lift(load_model="barbell", mode="sbs")` 等; `save_lift_state(tier=...)`→`mode=`; 断言列名。

- [ ] **Step 4: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_db.py tests/test_repo.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/db.py webapp/repo.py tests/test_db.py tests/test_repo.py
git commit -m "feat(webapp): lifts/load_model+mode columns, repo dispatch via registry"
```

---

### Task 5: webapp services (advance / tier→mode / preview / volume / recompute)

**Files:**
- Modify: `webapp/services/advance.py`, `webapp/services/tier.py`→`mode.py`, `webapp/services/preview.py`, `webapp/services/volume.py`, `webapp/services/recompute.py`
- Test: `tests/test_advance_service.py`, `tests/test_tier_service.py`→`test_mode_service.py`, `tests/test_preview_service.py`, `tests/test_volume_service.py`, `tests/test_recompute_service.py`

**Interfaces:**
- Consumes: repo 新签名, engine registry, schema 新字段
- Produces: `advance._lift_from_row` 读 `load_model`/`mode`; `mode.derive_state(conn, lift_id, new_mode, settings)` (校验合法组合 + 调 handler.derive_on_switch); `mode.apply_switch`; preview/volume 经 seam 不变

- [ ] **Step 1: advance.py `_lift_from_row`**

```python
def _lift_from_row(r) -> Lift:
    return Lift(
        name=r["name"], day=r["day"],
        load_model=r["load_model"], mode=r["mode"],
        max=r["max"], intensity=r["intensity"] or 0.0, reps=r["reps"] or 0,
        repout=r["repout"] or 0, sets=r["sets"] or 3, start=r["start"],
        lift_kind=r["lift_kind"],
        incr=r["incr"] if "incr" in r.keys() else None,
        bodyweight_pct=r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0,
    )
```
(删 `tier`, `progression`)。`advance_week` 里 `save_lift_state(tier=ls.tier...)` → `mode=ls.mode`。

- [ ] **Step 2: tier.py → mode.py**

重命名文件 + 重写 `derive_state`:
```python
"""Mode switch: keep history, recompute est1rm, derive new-mode start state. Read-only."""
import sqlite3
from sbs_cli.data.schema import SetEntry, is_legal_combo
from sbs_cli.program import _est1rm_from_history
from sbs_cli.engine.modes import get_mode
from .. import repo


def derive_state(conn, lift_id, new_mode, settings):
    lift = repo.get_lift(conn, lift_id)
    if not is_legal_combo(lift["load_model"], new_mode):
        raise ValueError(f"illegal mode {new_mode} for load_model {lift['load_model']}")
    hist = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
            for h in repo.list_history(conn, lift_id)]
    pct = lift["bodyweight_pct"] if "bodyweight_pct" in lift.keys() else 0.0
    bw = settings["bodyweight"] if "bodyweight" in settings.keys() else 0.0
    est1rm = _est1rm_from_history(hist, bw, pct)
    from . import advance as advance_service
    lift_dc = advance_service._lift_from_row(lift)
    state = get_mode(new_mode).derive_on_switch(lift_dc, hist, settings, est1rm)
    state["est1rm"] = est1rm
    return state


def apply_switch(conn, lift_id, state):
    repo.update_lift(conn, lift_id, mode=state["mode"])
    repo.save_lift_state(conn, lift_id, mode=state["mode"], tm=state["tm"],
                         weight=state["weight"], target=state["target"],
                         streak=state["streak"], est1rm=state["est1rm"])
```

- [ ] **Step 3: preview.py / volume.py / recompute.py**

- `preview._working_weight`: `lift["tier"] == "sbs"` → `lift["mode"] == "sbs"`; 其余不变 (已走 seam)
- `volume.lift_week_volume`: `tier = lift["tier"]` → `mode = lift["mode"]`; `"t2"`→`"linear_t2"`, `"t3"`→`"linear_t3"`, `if mode=="sbs"/elif mode=="linear_t3"/else linear_t2`
- `volume._t2_target_as_of`: 无 tier 引用, 不变
- `recompute.recompute_on_start_change`: `lift_row["tier"] not in ("t2","t3")` → `lift_row["mode"] not in ("linear_t2","linear_t3")`; `save_lift_state(tier=...)`→`mode=ls.mode`
- `recompute.recompute_sbs_tm`: `lift_row["tier"] != "sbs"` → `mode != "sbs"`; `save_lift_state(tier="sbs")`→`mode="sbs"`

- [ ] **Step 4: 改测试**

对应 5 个测试文件: `tier`→`mode`, `"t2"/"t3"`→`"linear_t2"/"linear_t3"`, `save_lift_state(tier=`→`mode=`, `create_lift(tier=`→`load_model=/mode=`, import `services.tier`→`services.mode`, `test_tier_service.py` 重命名 `test_mode_service.py`。

- [ ] **Step 5: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_advance_service.py tests/test_mode_service.py tests/test_preview_service.py tests/test_volume_service.py tests/test_recompute_service.py -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/services/ tests/
git commit -m "refactor(services): mode dispatch + legal-combo guard, tier→mode rename"
```

---

### Task 6: webapp routes + templates

**Files:**
- Modify: `webapp/routes/lifts.py`, `webapp/routes/plan.py`, `webapp/routes/reseed.py`, `webapp/templates/lifts.html`, `webapp/templates/_lift_row.html`, `webapp/templates/plan.html`, `webapp/templates/week_export.html`, `webapp/templates/tier_preview.html`→`mode_preview.html`
- Test: `tests/test_routes_lifts.py`, `tests/test_routes_plan.py`, `tests/test_routes_reseed.py`

**Interfaces:**
- Consumes: `services.mode.{derive_state, apply_switch}`, repo 新签名, schema 常量
- Produces: `/lifts/new` `/lifts/edit` 接受 `load_model`+`mode` (校验合法); `/lifts/<lid>/mode` GET/POST (原 tier 路由改名); `plan._by_day` 按 mode 分派显示行

- [ ] **Step 1: lifts.py new()**

```python
@bp.route("/lifts/new", methods=["POST"])
def new():
    conn = get_db()
    name = request.form.get("name", "").strip()
    load_model = request.form.get("load_model", "barbell")
    mode = request.form.get("mode", "")
    from sbs_cli.data.schema import is_legal_combo, LOAD_MODELS
    if load_model not in LOAD_MODELS:
        flash("load_model 非法")
        return render_template("_lift_row.html", lift=None, error="bad load_model"), 400
    if not is_legal_combo(load_model, mode):
        flash("load_model 与 mode 组合非法")
        return render_template("_lift_row.html", lift=None, error="bad combo"), 400
    if not name:
        flash("动作名不能为空")
        return render_template("_lift_row.html", lift=None, error="name required"), 400
    # incr 仅 linear_t2/t3 生效；sbs/none 强制 None
    incr, err = (None, None) if mode in ("sbs", "none") else _parse_incr(request.form.get("incr"))
    if err is not None:
        flash(err)
        return render_template("_lift_row.html", lift=None, error="bad incr"), 400
    # pure_bodyweight: pct 手填默认 1.0；barbell 强制 0；bodyweight 手填
    if load_model == "barbell":
        pct = 0.0
    elif load_model == "pure_bodyweight":
        pct = _f("bodyweight_pct", 1.0, float) or 1.0
    else:
        pct = _f("bodyweight_pct", 0.0, float) or 0.0
    try:
        lid = repo.create_lift(
            conn, name=name, load_model=load_model, mode=mode,
            day=_f("day", 1, int), sort_order=999,
            sets=_f("sets", 3, int), max=_f("max", cast=float),
            intensity=_f("intensity", cast=float), reps=_f("reps", cast=int),
            repout=_f("repout", cast=int), start=_f("start", cast=float),
            lift_kind=_f("lift_kind") if mode == "sbs" else None, incr=incr,
            bodyweight_pct=pct)
    except Exception as e:
        flash(f"创建失败: {e}")
        return render_template("_lift_row.html", lift=None, error=str(e)), 400
    lift = repo.get_lift(conn, lid)
    return render_template("_lift_row.html", lift=lift)
```

- [ ] **Step 2: lifts.py edit() + mode 路由**

- `edit()`: 列映射 `"tier"`→删除, 加 `("mode", str)`; **禁止改 load_model** (列映射不收 `load_model`); incr 校验保留; mode 改动需校验合法:
```python
if "mode" in fields:
    cur = repo.get_lift(conn, lid)
    from sbs_cli.data.schema import is_legal_combo
    if not is_legal_combo(cur["load_model"], fields["mode"]):
        flash("load_model 与 mode 组合非法")
        return render_template("_lift_row.html", lift=cur, error="bad combo"), 400
```
start-recompute 触发条件: `lift["mode"] in ("linear_t2","linear_t3") and "start" in fields`
- `tier_preview`/`tier_apply` → `mode_preview`/`mode_apply`: URL `/lifts/<lid>/mode`, 参数 `tier`→`mode`, `new_tier`→`new_mode`, import `services.mode as mode_service`, 模板 `mode_preview.html`。derive_state 抛 ValueError 时 flash + redirect。

- [ ] **Step 3: 模板**

- `lifts.html`: tier 下拉 → 两个下拉 `load_model`(barbell/bodyweight/pure_bodyweight) + `mode`(sbs/linear_t2/linear_t3/none); 行内显示 `load_model`/`mode`
- `_lift_row.html`: 同上, 编辑表单 mode 下拉 (load_model 只读显示); tier_preview 链接 → mode
- `tier_preview.html` → `mode_preview.html`: 文案 tier→mode

- [ ] **Step 4: 改测试 test_routes_lifts.py**

POST 数据 `tier=sbs`→`load_model=barbell&mode=sbs`; 断言 tier→mode; 新增非法组合 400 测试:
```python
def test_new_rejects_illegal_combo(client):
    r = client.post("/lifts/new", data={"name": "X", "load_model": "bodyweight",
                                        "mode": "sbs", "day": 1})
    assert r.status_code == 400
```

- [ ] **Step 4b: plan.py `_by_day()` + reseed.py**

`webapp/routes/plan.py`:
- L5 `from ..services import advance, tier` → `from ..services import advance` (tier 引用已迁 mode.py)
- `_by_day()` L62-92 循环体按 `r["mode"]` 分派, 复用 engine registry 的 plan_fields, 但保留 per-row id/working_weight/is_bodyweight/logged/live_html 逻辑。改法: 分支条件 `r["tier"]=="sbs"/"t2"/else` → `r["mode"]=="sbs"/"linear_t2"/"linear_t3"/"none"`; `SimpleNamespace(... tier="sbs" ...)` → `mode=r["mode"]`; `is_bodyweight=pct>0` → `is_bodyweight=r["load_model"] in ("bodyweight","pure_bodyweight")`。`none` 分支新增:
```python
else:  # none (pure bodyweight, record-only)
    added = st["weight"] or 0.0
    last = repo.list_history(conn, r["id"])
    last_reps = last[-1]["reps"] if last else None
    item = SimpleNamespace(id=r["id"], name=r["name"], mode="none", weight=added,
                           working_weight=working_weight(added, bw, pct),
                           is_bodyweight=True,
                           reps=last_reps, sets=r["sets"], repout=None,
                           target=None, streak=0, est1rm=est1rm)
```
模板 `plan.html`/`week_export.html` 读 `it.tier`→`it.mode`, `tier=='t2'/'t3'`→`mode=='linear_t2'/'linear_t3'`。

`webapp/routes/reseed.py` L25 `if r["tier"] != "sbs"` → `if r["mode"] != "sbs"`。

- [ ] **Step 4c: 改测试 test_routes_plan.py / test_routes_reseed.py**

fixture/断言里 `tier`→`mode`, `"t2"/"t3"`→`"linear_t2"/"linear_t3"`, `create_lift(tier=`→`load_model=/mode=`。

- [ ] **Step 5: 跑测试**

Run: `conda run -n sbs python -m pytest tests/test_routes_lifts.py tests/test_routes_plan.py tests/test_routes_reseed.py -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/routes/ webapp/templates/ tests/test_routes_lifts.py tests/test_routes_plan.py tests/test_routes_reseed.py
git commit -m "feat(routes): load_model+mode form fields, plan/reseed mode dispatch, mode switch"
```

---

### Task 7: CLI io + view + importer + migrate.py

**Files:**
- Modify: `sbs_cli/data/io.py`, `sbs_cli/view/terminal.py`, `sbs_cli/view/templates/week.html.j2`, `sbs_cli/importer.py`, `migrate.py`
- Test: `tests/test_io.py`, `tests/test_terminal.py`, `tests/test_html.py`, `tests/test_importer.py`, `tests/test_migrate.py`

**Interfaces:**
- Consumes: schema 新字段, `PlanItem.mode`
- Produces: YAML profile/state 序列化 `load_model`/`mode` (删 `tier`/`progression`); CLI view/importer/migrate 用新字段

- [ ] **Step 1: io.py**

- `profile_to_dict`: lift dict `"tier"`→`"load_model","mode"`, 删 `"progression"`
- `profile_from_dict`: 构造 `Lift(... load_model=x.get("load_model","barbell"), mode=x.get("mode","none"), ...)`; 删 `tier`/`progression`; lift_kind 默认逻辑 `"main" if x.get("mode")=="sbs" else None`
- `state_to_dict`/`state_from_dict`: `"tier": ls.tier`→`"mode": ls.mode`; `LiftState(... mode=x.get("mode") ...)`

- [ ] **Step 2: view terminal.py + week.html.j2**

`terminal.py`: L14 `if it.tier == "sbs"` → `it.mode`; L16 `elif it.tier == "t2"` → `it.mode == "linear_t2"`; L31/33 同 (`l.tier`→`l.mode`, `t2`→`linear_t2`)。
`week.html.j2`: L21 `{{ it.tier }}`→`{{ it.mode }}`; L22 `it.tier == 'sbs'`→`it.mode == 'sbs'`; L23 `it.tier == 't2'`→`it.mode == 'linear_t2'`。

- [ ] **Step 3: importer.py**

生成 Lift 处: `Lift(... tier="sbs" ...)` → `load_model="barbell", mode="sbs"`; `tier="t2"`→`load_model="barbell", mode="linear_t2"`; `tier="t3"`→`load_model="barbell", mode="linear_t3"`。L71 `sbs_lifts = [l for l in lifts if l.tier == "sbs"]` → `l.mode == "sbs"`。

- [ ] **Step 4: migrate.py**

L27 `tier=l.tier` → `load_model=l.load_model, mode=l.mode`; L30 删 `progression=l.progression`; L64 `if l.tier == "sbs"` → `l.mode`; L67 `l.tier in ("t2","t3")` → `l.mode in ("linear_t2","linear_t3")`; L71 `save_lift_state(tier=ls.tier...)` → `mode=ls.mode`。

- [ ] **Step 5: 改测试 + 跑**

`test_io.py`/`test_terminal.py`/`test_html.py`/`test_importer.py`/`test_migrate.py`: tier→mode 同步, `"t2"/"t3"`→`"linear_t2"/"linear_t3"`。
Run: `conda run -n sbs python -m pytest tests/test_io.py tests/test_terminal.py tests/test_html.py tests/test_importer.py tests/test_migrate.py -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add sbs_cli/data/io.py sbs_cli/view/ sbs_cli/importer.py migrate.py tests/
git commit -m "refactor(cli): yaml/view/importer/migrate use load_model+mode"
```

---

### Task 8: 迁移脚本 migrate_modes.py

**Files:**
- Create: `migrate_modes.py`
- Test: `tests/test_migrate_modes.py`

**Interfaces:**
- Consumes: `webapp.db`, schema 常量
- Produces: `migrate_modes(conn) -> int` (幂等, 重建 lifts 表 + 改 lift_state.mode); CLI `__main__`

- [ ] **Step 1: 写失败测试**

`tests/test_migrate_modes.py`:
```python
import sqlite3
from webapp import db
from migrate_modes import migrate_modes

def _old_schema_db(tmp_path):
    """Build a pre-refactor DB with tier/progression columns + sample rows."""
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), week INT NOT NULL,
      days_per_week INT NOT NULL, rounding REAL NOT NULL, incr REAL NOT NULL,
      t2_reset_pct REAL NOT NULL, t2_fail INT NOT NULL, t3_target INT NOT NULL,
      bodyweight REAL NOT NULL DEFAULT 0);
    INSERT INTO settings VALUES (1,1,4,2.5,2.5,0.75,3,15,75.0);
    CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      tier TEXT NOT NULL, day INT NOT NULL, sort_order INT NOT NULL DEFAULT 0,
      sets INT NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INT, repout INT,
      start REAL, lift_kind TEXT, incr REAL,
      bodyweight_pct REAL NOT NULL DEFAULT 0.0,
      progression TEXT NOT NULL DEFAULT 'weight');
    CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT NOT NULL,
      tm REAL, weight REAL, target INT, streak INT NOT NULL DEFAULT 0,
      est1rm REAL, reseeded_cycle INT NOT NULL DEFAULT 0);
    CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INT NOT NULL,
      week INT NOT NULL, weight REAL NOT NULL, reps INT NOT NULL, ts TEXT NOT NULL);
    """)
    # sbs barbell, t2 barbell, t2 bodyweight(weighted pull-up), pure-bodyweight crunch
    conn.execute("INSERT INTO lifts (name,tier,day,max,lift_kind) VALUES ('Squat','sbs',1,100,'main')")
    conn.execute("INSERT INTO lifts (name,tier,day,start) VALUES ('Bench','t2',1,60)")
    conn.execute("INSERT INTO lifts (name,tier,day,start,bodyweight_pct) VALUES ('Pull-up','t2',2,10,1.0)")
    conn.execute("INSERT INTO lifts (name,tier,day,bodyweight_pct,progression) VALUES ('Crunch','t3',2,1.0,'none')")
    conn.execute("INSERT INTO lift_state VALUES (1,'sbs',100,NULL,NULL,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (2,'t2',NULL,60,8,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (3,'t2',NULL,10,8,0,NULL,0)")
    conn.execute("INSERT INTO lift_state VALUES (4,'t3',NULL,NULL,NULL,0,NULL,0)")
    conn.commit()
    return p, conn

def test_migrate_maps_rows(tmp_path):
    p, conn = _old_schema_db(tmp_path)
    migrate_modes(conn)
    rows = {r["name"]: (r["load_model"], r["mode"]) for r in
            conn.execute("SELECT name, load_model, mode FROM lifts")}
    assert rows["Squat"] == ("barbell", "sbs")
    assert rows["Bench"] == ("barbell", "linear_t2")
    assert rows["Pull-up"] == ("bodyweight", "linear_t2")
    assert rows["Crunch"] == ("pure_bodyweight", "none")
    # lift_state tier -> mode
    st = {r["lift_id"]: r["mode"] for r in conn.execute("SELECT lift_id, mode FROM lift_state")}
    assert st[1] == "sbs" and st[2] == "linear_t2" and st[4] == "none"
    # old columns gone
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(lifts)")}
    assert "tier" not in cols and "progression" not in cols
    conn.close()

def test_migrate_idempotent(tmp_path):
    p, conn = _old_schema_db(tmp_path)
    migrate_modes(conn)
    n = migrate_modes(conn)   # second run no-op
    assert n == 0
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n sbs python -m pytest tests/test_migrate_modes.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_modes'`

- [ ] **Step 3: 实现 migrate_modes.py**

```python
"""One-shot: rebuild lifts table with load_model/mode, rename lift_state.tier->mode.

Maps the old (tier, progression, bodyweight_pct) triple to the new dual enums
(ADR 0005). History table untouched. Idempotent: no-op once lifts.load_model
exists. Backs up the DB before touching it (run via --db / --backup-dir).

Run:  conda run -n sbs python migrate_modes.py --db sbs.db --backup-dir backups
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone


def _has_col(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})"))


_MAP = {
    # (tier, progression, pct>0) -> (load_model, mode)
    ("sbs", False): ("barbell", "sbs"),
    ("t2", False): ("barbell", "linear_t2"),
    ("t2", True):  ("bodyweight", "linear_t2"),
    ("t3", False): ("barbell", "linear_t3"),
    ("t3", True):  ("bodyweight", "linear_t3"),
}

def _derive(tier, progression, pct):
    if progression == "none":
        return ("pure_bodyweight", "none")
    return _MAP[(tier, pct > 0)]


def migrate_modes(conn) -> int:
    """Rebuild lifts with load_model/mode. Returns rows migrated (0 if already done)."""
    if _has_col(conn, "lifts", "load_model"):
        return 0
    rows = conn.execute("SELECT * FROM lifts").fetchall()
    conn.executescript("""
    CREATE TABLE lifts_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        load_model TEXT NOT NULL DEFAULT 'barbell'
          CHECK (load_model IN ('barbell','bodyweight','pure_bodyweight')),
        mode TEXT NOT NULL DEFAULT 'none'
          CHECK (mode IN ('sbs','linear_t2','linear_t3','none')),
        day INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
        sets INTEGER NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INT,
        repout INT, start REAL, lift_kind TEXT, incr REAL,
        bodyweight_pct REAL NOT NULL DEFAULT 0.0);
    """)
    for r in rows:
        pct = r["bodyweight_pct"] if "bodyweight_pct" in r.keys() else 0.0
        prog = r["progression"] if "progression" in r.keys() else "weight"
        lm, mode = _derive(r["tier"], prog, pct)
        conn.execute(
            "INSERT INTO lifts_new (id,name,load_model,mode,day,sort_order,sets,max,"
            "intensity,reps,repout,start,lift_kind,incr,bodyweight_pct) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["name"], lm, mode, r["day"], r["sort_order"], r["sets"],
             r["max"], r["intensity"], r["reps"], r["repout"], r["start"],
             r["lift_kind"], r["incr"] if "incr" in r.keys() else None, pct))
    conn.execute("DROP TABLE lifts")
    conn.execute("ALTER TABLE lifts_new RENAME TO lifts")
    # lift_state.tier -> mode (rebuild; SQLite can't rename column pre-3.25 reliably)
    st = conn.execute("SELECT * FROM lift_state").fetchall()
    conn.executescript("""
    CREATE TABLE lift_state_new (
        lift_id INTEGER PRIMARY KEY REFERENCES lifts(id) ON DELETE CASCADE,
        mode TEXT NOT NULL, tm REAL, weight REAL, target INT,
        streak INTEGER NOT NULL DEFAULT 0, est1rm REAL,
        reseeded_cycle INTEGER NOT NULL DEFAULT 0);
    """)
    for s in st:
        pct_row = conn.execute("SELECT mode FROM lifts WHERE id=?", (s["lift_id"],)).fetchone()
        conn.execute(
            "INSERT INTO lift_state_new (lift_id,mode,tm,weight,target,streak,est1rm,reseeded_cycle) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (s["lift_id"], pct_row["mode"], s["tm"], s["weight"], s["target"],
             s["streak"], s["est1rm"],
             s["reseeded_cycle"] if "reseeded_cycle" in s.keys() else 0))
    conn.execute("DROP TABLE lift_state")
    conn.execute("ALTER TABLE lift_state_new RENAME TO lift_state")
    conn.commit()
    return len(rows)


def main(db_path="sbs.db", backup_dir="backups"):
    if not os.path.exists(db_path):
        sys.exit(f"db not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak = os.path.join(backup_dir, f"sbs-modes-{ts}.db.bak")
    shutil.copy2(db_path, bak)
    print(f"backup -> {bak}")
    from webapp import db
    conn = db.connect(db_path)
    try:
        n = migrate_modes(conn)
    finally:
        conn.close()
    print(f"migrated {n} lift(s) -> {db_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="migrate_modes")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--backup-dir", default="backups")
    a = ap.parse_args()
    main(a.db, a.backup_dir)
```

- [ ] **Step 4: 跑测试确认过**

Run: `conda run -n sbs python -m pytest tests/test_migrate_modes.py -x -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add migrate_modes.py tests/test_migrate_modes.py
git commit -m "feat(migrate): one-shot lifts/lift_state rebuild to load_model/mode"
```

---

### Task 9: 守卫测试 + 全量回归

**Files:**
- Modify: `tests/test_bodyweight_guard.py`, 其余受影响测试
- Test: 全量

**Interfaces:**
- Consumes: 全部
- Produces: 绿全量测试

- [ ] **Step 1: 修 test_bodyweight_guard.py + 残留 tier 引用**

`test_bodyweight_guard.py`: `tier`→`mode`, `"t2"/"t3"`→`"linear_t2"/"linear_t3"`, `progression="none"`→`load_model="pure_bodyweight", mode="none"`。
全 tests/ grep `tier`/`progression`/`"t2"/"t3"` 残留逐个改 (test_routes_plan, test_routes_reseed, test_migrate*, test_builder, test_schedule, test_volume_service 等)。

- [ ] **Step 2: 全量回归**

Run: `conda run -n sbs python -m pytest tests/ -q`
Expected: 全 PASS。逐个修残留直到绿。

- [ ] **Step 3: 更新 graphify**

Run: `graphify update .`

- [ ] **Step 4: Commit**

```bash
git add tests/ graphify-out/
git commit -m "test: mode-unification regression net green"
```

---

## Self-Review

- **Spec coverage**: 双枚举✅(T1) 注册表✅(T2) 四调用点收拢✅(T2/T3/T4) 合法组合强制✅(T1/T4/T5/T6) none纯记录✅(T2) load_model不可切✅(T6 edit不收) 纯自重显示bw×pct✅(T2 RecordOnly.plan_fields+seam+T6 plan none分支) pct手填默认1.0✅(T6) 迁移删列重建✅(T8) ADR0001-4保留✅(handler复用纯函数+seam)。
- **依赖适配 (codegraph 全量核查)**: routes lifts/plan/reseed✅(T6) services advance/mode/preview/volume/recompute✅(T5) io/view terminal+j2/importer✅(T7) migrate.py✅(T7) PlanItem.mode slot✅(T3)。
- **Placeholder scan**: 无 TBD/TODO。每步含完整代码/命令。
- **Type consistency**: `LiftState.mode`/`Lift.mode`/`Lift.load_model` 全程一致; `get_mode`/`PROGRESSION_REGISTRY`/`is_legal_combo`/`derive_state`/`apply_switch`/`plan_fields` 命名统一; `save_lift_state(mode=)` 统一; handler `derive_on_switch` 返回 dict 含 `mode` 键, `apply_switch` 读 `state["mode"]` 对齐; 迁移 `_MAP`/`_derive`/`migrate_modes` 一致。

## 执行顺序与风险

- T1→T9 严格顺序 (依赖链: schema→engine→program→webapp schema→services→routes→cli→migrate→回归)。
- T8 迁移 destructive (DROP TABLE), 先备份; 仅 `--db` 显式指定才碰生产库。
- webapp `_by_day` 不复用 `week_plan` (per-row id 需要), 自建 SimpleNamespace — 与 CLI `week_plan` 是两套显示路径, 都需改 (T3 PlanItem + T6 _by_day)。
