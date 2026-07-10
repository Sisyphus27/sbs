# Tasks — per-lift-t2t3-increment

实现 t2/t3 per-lift 增长步长。引擎层走 TDD（先红后绿）。命令在 `D:\WorkSpace\sbs\` 下用 `conda run -n sbs` 跑。

## 0. 文档/术语先行

- [x] 0.1 回写 spec.md：MODIFY t2 reset requirement（snap 网格 rounding → effective step）+ ADD「tier 切换保留 incr」场景
- [x] 0.2 改 CONTEXT.md：rounding quantum / loaded-value 定义收窄到 sbs；加 progression step / effective step 术语
- [x] 0.3 落盘 docs/adr/0003-t2t3-progression-snap-grid.md（每动作一个 snap 网格）

## 1. Engine: progression 纯函数（TDD）

- [x] 1.1 写 `t3_next` 去 rounding 测试：命中精确累加（20+5=25）、非 rounding 倍数不 snap（50+3=53）、默认配置 no-op（50+2.5=52.5）；改 `sbs_cli/engine/progression.py` 的 `t3_next` 移除 `quantum` 参数与 `round_weight`，直接 `weight + incr`
- [x] 1.2 写 `t2_next` 测试：HIT 分支精确累加（去 rounding）、reset 分支仍 `round_weight(est1rm×reset_pct, quantum)`；改 `t2_next` 仅 HIT 分支去 `round_weight`，reset 分支与签名保留 `quantum`
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
- [ ] 4.4 `webapp/services/tier.py` 的 `derive_state`：t2/t3 起始重量 snap 网格由 rounding 改为 eff_incr（`lift["incr"] if not None else settings["incr"]`）；`apply_switch` 不动（incr 在 lifts 列，tier 切换不触碰）
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
