import os
import yaml
from webapp import db, repo
import migrate

SRC_XLSX = r"D:\WorkSpace\sbs\backup\00_cold_backup.xlsx"


def _write_yaml(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


def test_migrate_from_yaml(tmp_path, monkeypatch):
    profile = {
        "rounding": 2.5, "days_per_week": 4, "incr": 2.5,
        "t2_reset_pct": 0.7, "t2_fail": 3, "t3_target": 15,
        "lifts": [
            {"name": "Squat", "load_model": "barbell", "mode": "sbs", "day": 1,
             "max": 135.0, "intensity": 0.7, "reps": 5, "repout": 10, "sets": 5},
            {"name": "Rows", "load_model": "barbell", "mode": "linear_t2", "day": 1,
             "sets": 3, "start": 85.0},
        ],
    }
    state = {"week": 2, "lifts": {
        "Squat": {"mode": "sbs", "tm": 137.5, "history": [{"week": 1, "weight": 95.0, "reps": 11}]},
        "Rows": {"mode": "linear_t2", "weight": 87.5, "target": 10, "streak": 0, "history": []},
    }}
    p = tmp_path / "profile.yaml"; _write_yaml(str(p), profile)
    s = tmp_path / "state.yaml"; _write_yaml(str(s), state)
    dbp = str(tmp_path / "out.db")
    migrate.migrate_from_yaml(dbp, str(p), str(s))
    conn = db.connect(dbp); db.init_schema(conn)
    assert repo.get_settings(conn)["week"] == 2
    assert len(repo.list_lifts(conn)) == 2
    squat = repo.get_lift_by_name(conn, "Squat")
    squat_id = squat["id"]
    # sbs lifts must carry a non-NULL lift_kind so lookup_schedule doesn't KeyError on /plan.
    assert squat["lift_kind"] == "main"
    assert repo.get_lift_state(conn, squat_id)["tm"] == 137.5
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_migrate_refuses_overwrite(tmp_path):
    dbp = str(tmp_path / "out.db")
    db.connect(dbp).close()
    import pytest
    with pytest.raises(SystemExit):
        migrate.migrate_from_yaml(dbp, "profile.yaml", "state.yaml")


def test_migrate_seeds_bodyweight_and_lift_bodyweight_fields(tmp_path):
    # Task 14: seed(conn, p) must sync Profile.bodyweight -> settings.bodyweight
    # and Lift.bodyweight_pct/load_model/mode -> lifts.columns from profile.yaml.
    import migrate
    from webapp.db import init_schema
    import sqlite3
    profile_yaml = tmp_path / "profile.yaml"
    profile_yaml.write_text(
        "bodyweight: 75.0\nrounding: 2.5\nlifts:\n"
        "- name: Chin-ups\n  load_model: pure_bodyweight\n  mode: none\n"
        "  day: 2\n  start: 0.0\n  bodyweight_pct: 1.0\n",
        encoding="utf-8")
    db_path = tmp_path / "sbs.db"
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    init_schema(conn)
    from sbs_cli.data.io import load_profile
    p = load_profile(str(profile_yaml))
    migrate.seed(conn, p)
    from webapp.repo import get_settings, list_lifts
    assert get_settings(conn)["bodyweight"] == 75.0
    chin = next(r for r in list_lifts(conn) if r["name"] == "Chin-ups")
    assert chin["bodyweight_pct"] == 1.0
    assert chin["load_model"] == "pure_bodyweight"
    assert chin["mode"] == "none"
    conn.close()


def test_migrate_from_xlsx_sets_sbs_lift_kind(tmp_path):
    # Regression: migrate_from_xlsx must pass the importer's lift_kind through to
    # the DB, else every sbs read path KeyErrors on lookup_schedule.
    if not os.path.exists(SRC_XLSX):
        import pytest
        pytest.skip("cold-backup xlsx fixture not available")
    dbp = str(tmp_path / "out.db")
    migrate.migrate_from_xlsx(dbp, SRC_XLSX, force=True)
    conn = db.connect(dbp)
    sbs_kinds = {row["name"]: row["lift_kind"] for row in repo.list_lifts(conn)
                 if row["mode"] == "sbs"}
    conn.close()
    assert sbs_kinds, "expected at least one sbs lift from xlsx import"
    assert sbs_kinds["Squat"] == "main"      # QS main row
    for name, kind in sbs_kinds.items():
        assert kind in ("main", "aux"), f"{name} has NULL/invalid lift_kind={kind!r}"
