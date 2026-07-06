import json
from sbs_cli import cli

def test_full_flow_init_week_next_show(tmp_path, monkeypatch):
    prof = tmp_path / "profile.yaml"; st = tmp_path / "state.yaml"
    monkeypatch.chdir(tmp_path)

    # init from cold backup
    cli.run(["init", "--from", r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx",
             "--profile", str(prof), "--state", str(st)])
    assert prof.exists()
    # week 1 html
    cli.run(["week", "--profile", str(prof), "--state", str(st), "--out", "week-1.html"])
    assert (tmp_path / "week-1.html").exists()
    # synthesize a log: Squat beats repout, Barbell rows hits, Leg Extension hits
    log = {"week": 1, "logs": {"Squat": 11, "Barbell rows": 10, "Leg Extension": 15}}
    logp = tmp_path / "week-1-log.json"; logp.write_text(json.dumps(log))
    # next
    cli.run(["next", str(logp), "--profile", str(prof), "--state", str(st), "--out", "week-2.html"])
    assert (tmp_path / "week-2.html").exists()
    # state advanced
    from sbs_cli.data import io as dio
    s = dio.load_state(str(st))
    assert s.week == 2
    # Squat beat repout 8 by 3 -> +1.5% on TM 135 -> 137.025 (raw, no MROUND)
    assert s.lifts["Squat"].tm == 137.025
    # Barbell rows hit (10 >= target 10) -> +2.5 on 85
    assert s.lifts["Barbell rows"].weight == 87.5
    # show runs without error
    cli.run(["show", "--profile", str(prof), "--state", str(st)])


def test_week_default_out_uses_current_week(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.run(["init", "--from", r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx",
             "--profile", str(tmp_path/"profile.yaml"), "--state", str(tmp_path/"state.yaml")])
    cli.run(["week", "--profile", str(tmp_path/"profile.yaml"), "--state", str(tmp_path/"state.yaml")])
    # default --out should produce week-1.html (substituted), NOT a literal "week-N.html"
    assert (tmp_path / "week-1.html").exists()
    assert not (tmp_path / "week-N.html").exists()
