import os
import yaml
from webapp import db, repo
import migrate


def _write_yaml(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


def test_migrate_from_yaml(tmp_path, monkeypatch):
    profile = {
        "rounding": 2.5, "days_per_week": 4, "incr": 2.5,
        "t2_reset_pct": 0.7, "t2_fail": 3, "t3_target": 15,
        "lifts": [
            {"name": "Squat", "tier": "sbs", "day": 1, "max": 135.0,
             "intensity": 0.7, "reps": 5, "repout": 10, "sets": 5},
            {"name": "Rows", "tier": "t2", "day": 1, "sets": 3, "start": 85.0},
        ],
    }
    state = {"week": 2, "lifts": {
        "Squat": {"tier": "sbs", "tm": 137.5, "history": [{"week": 1, "weight": 95.0, "reps": 11}]},
        "Rows": {"tier": "t2", "weight": 87.5, "target": 10, "streak": 0, "history": []},
    }}
    p = tmp_path / "profile.yaml"; _write_yaml(str(p), profile)
    s = tmp_path / "state.yaml"; _write_yaml(str(s), state)
    dbp = str(tmp_path / "out.db")
    migrate.migrate_from_yaml(dbp, str(p), str(s))
    conn = db.connect(dbp); db.init_schema(conn)
    assert repo.get_settings(conn)["week"] == 2
    assert len(repo.list_lifts(conn)) == 2
    squat_id = repo.get_lift_by_name(conn, "Squat")["id"]
    assert repo.get_lift_state(conn, squat_id)["tm"] == 137.5
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_migrate_refuses_overwrite(tmp_path):
    dbp = str(tmp_path / "out.db")
    db.connect(dbp).close()
    import pytest
    with pytest.raises(SystemExit):
        migrate.migrate_from_yaml(dbp, "profile.yaml", "state.yaml")
