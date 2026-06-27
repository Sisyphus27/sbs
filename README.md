# SBS/GZCLP 训练 Web App

替代旧 CLI + YAML + JSON 搬运的**本地浏览器 app**。打开就是当周计划页,填末组次数点提交,自动算下周。引擎复用旧的纯函数引擎(SBS 自调节 + GZCLP T2 状态机 + T3 阈值),数据全进一个 SQLite 文件,不再跟两个 YAML / JSON 文件搏斗。

旧 CLI(`python -m sbs_cli`)仍可用作引擎/测试参考,见 `README_sbs_cli.md`。

---

## 快速开始

环境:conda 环境 **`sbs`**(Python 3.12,装了 `flask`/`pyyaml`/`jinja2`/`openpyxl`/`pytest`)。所有命令在 `D:\WorkSpace\sbs\` 下跑。

### 首次:把现有数据迁进 SQLite

```bash
conda run -n sbs python migrate.py
```

读 `profile.yaml` + `state.yaml` → 生成 `sbs.db`(单文件)。同名动作跨多天(如 Leg Curl day1+day3、Face Pull day2+day4)按独立实例存。已存在 `sbs.db` 时拒绝覆盖,加 `--force` 强制。

### 启动

```bash
conda run -n sbs python -m webapp
```

→ 起 `127.0.0.1:5000`,自动开浏览器。单用户、无登录、纯本地。

或双击 `run_sbs.bat`(等价上面命令)。

---

## 每周流程

```
打开首页  →  看当周计划(按天列出每个动作:重量×次数×组数 + 目标)
练完填末组次数  →  点「提交并算下周」
→  引擎按三层规则更新每个动作,week+1,渲染下周
```

不再导出 JSON、不再传文件、不再开终端。提交前自动给 `sbs.db` 存一份快照到 `backups/`。

---

## 三层进阶规则

引擎同旧 CLI,见 `README_sbs_cli.md` 的「进阶规则(三层)」:
- **sbs**:TM 按末组表现自调节(超目标几次 → 多涨,差几次 → 降)。
- **t2**:GZCLP 状态机 3×10 → 3×8 → 3×6,连败降级,到底重置。
- **t3**:末组 ≥ 目标(默认 15)→ +incr。

est1RM 三式平均(Epley/Brzycki/Wathan),从历史最佳组算,tier 无关。

---

## 动作管理(`/lifts`)

UI 直接 CRUD,不再手编 YAML:
- 增/删/改名。
- 改 day、sets、强度(intensity)、reps、repout、start/max —— 每行内联编辑,HTMX 局部刷新。
- **换 tier**:保留历史,从 est1RM 推新 tier 起点状态,弹预览页可改后确认。
- 同名动作可跨多天(各自独立行,按 id 区分,日志按 id 填)。

## 全局参数(`/settings`)

rounding(取整粒度)、days_per_week、incr、t2_reset_pct、t2_fail、t3_target。

---

## 备份 / 回滚

- 每次「提交并算下周」前自动快照 `backups/sbs-w<N>-<时间戳>.db.bak`。
- 手动备份:拷 `sbs.db`。
- 回滚:从 `backups/` 拷回某份 `.db.bak` 覆盖 `sbs.db`(关掉 app 再操作)。

---

## 开发 / 测试

```bash
conda run -n sbs python -m pytest tests/ -q      # 108 个测试(引擎 74 + repo/service/route/migrate)
conda run -n sbs python -m pip install -r requirements.txt
```

设计与实现文档:
- 设计 spec:`docs/superpowers/specs/2026-06-27-sbs-local-webapp-redesign-design.md`
- 实现计划:`docs/superpowers/plans/2026-06-27-sbs-local-webapp-redesign.md`

---

## 文件结构(新)

```
D:\WorkSpace\sbs\
├─ webapp/                  # 本地浏览器 app
│   ├─ app.py               # Flask 工厂 + 启动(自动开浏览器)
│   ├─ __main__.py          # python -m webapp 入口
│   ├─ db.py                # SQLite 连接 + 建表
│   ├─ repo.py              # Repository: settings/lifts/lift_state/history
│   ├─ backup.py            # 提交前快照
│   ├─ services/
│   │   ├─ advance.py       # 引擎适配器: DB→dataclass→引擎→DB
│   │   └─ tier.py          # 换 tier(保留历史)
│   ├─ routes/              # plan / lifts / settings 蓝图
│   └─ templates/ + static/  # Jinja + htmx(离线)
├─ sbs_cli/                 # 引擎(复用,不动)
├─ migrate.py               # YAML/xlsx → SQLite
├─ run_sbs.bat              # 双击启动
├─ sbs.db                   # 唯一数据文件(别提交)
├─ backups/                 # 自动快照
├─ profile.yaml / state.yaml  # 旧数据(migrate 读一次)
└─ tests/                   # 108 测试
```

## 打包成 exe(可选)

```bash
conda run -n sbs python -m pip install pyinstaller
conda run -n sbs python -m PyInstaller sbs_webapp.spec --clean
```

→ `dist/sbs_webapp.exe`,双击即跑(DB 放 exe 同级)。
