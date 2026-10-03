import sqlite3
from contextlib import closing

import pytest

from sbs_cli.data.schema import LEGAL_COMBOS
from sbs_cli.engine.modes import Mode
from webapp import db, repo
from webapp.app import create_app
from webapp.migration import migrate_to_v3
from webapp.routes import plan as plan_routes
from webapp.services import training


@pytest.mark.parametrize("load_model,mode", sorted(LEGAL_COMBOS))
@pytest.mark.parametrize("reps", [0, 1, 10, 11, 20, 21, 37])
def test_rep_boundaries_finalize_without_legacy_history(tmp_path, monkeypatch,
                                                        load_model, mode, reps):
    def unexpected_record(*args, **kwargs):
        raise AssertionError("new training facts must not use legacy history")

    monkeypatch.setattr(Mode, "_record", unexpected_record)
    with closing(db.connect(":memory:")) as conn:
        migrate_to_v3(conn, db_path=":memory:", backup_dir=str(tmp_path))
        slot_id = repo.create_training_slot(
            conn, name="High-rep lift", load_model=load_model, mode=mode,
            day=1, sort_order=0, sets=3, max=100, start=30,
            lift_kind="main" if mode == "sbs" else None,
            bodyweight_pct=0 if load_model == "barbell" else 1,
        )
        training.save_draft_set(
            conn, expected_week=1, slot_id=slot_id, set_number=3,
            actual_added_weight=0 if mode == "none" else 30,
            reps=reps, bodyweight_kg=75, drives_progression=True,
        )
        assert training.finalize_week(conn, expected_week=1) == 2
        fact, = training.training_history(conn)
        assert fact["reps"] == reps
        assert (fact["canonical_e1rm"] is not None) == (1 <= reps <= 10)
        assert (fact["display_e1rm"] is not None) == (1 <= reps <= 20)
        assert fact["finalized_at"] is not None


@pytest.mark.parametrize("calibrate", [False, True])
def test_review_copies_and_settles_once_without_changing_source(tmp_path, monkeypatch,
                                                               calibrate):
    class CountedConnection(sqlite3.Connection):
        copies = 0

        def backup(self, target, **kwargs):
            self.copies += 1
            return super().backup(target, **kwargs)

    with closing(sqlite3.connect(":memory:", factory=CountedConnection)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        migrate_to_v3(conn, db_path=":memory:", backup_dir=str(tmp_path))
        slots = [repo.create_training_slot(
            conn, name=name, mode=mode, load_model="barbell", day=1,
            sort_order=index, sets=3, start=30, max=100,
            lift_kind="main" if mode == "sbs" else None,
        ) for index, (name, mode) in enumerate([
            ("Curl", "linear_t3"), ("Squat", "sbs"), ("Skipped", "linear_t2"),
        ])]
        for slot_id, reps in zip(slots, (0, 13)):
            training.save_draft_set(
                conn, expected_week=1, slot_id=slot_id, set_number=3,
                actual_added_weight=30, reps=reps, drives_progression=True,
            )
        before = conn.serialize()
        real_finalize = training.finalize_week
        settlements = []

        def count_finalize(preview_conn, **kwargs):
            assert preview_conn is not conn
            settlements.append(1)
            return real_finalize(preview_conn, **kwargs)

        monkeypatch.setattr(training, "finalize_week", count_finalize)
        calibration_ids = [slots[1]] if calibrate else []
        review = training.review_week_settlement(
            conn, expected_week=1, skipped_slot_ids=[slots[2]],
            calibrate_tm_slot_ids=calibration_ids,
        )
        assert conn.copies == 1
        assert len(settlements) == 1
        assert conn.serialize() == before
        assert (review["logged_count"], review["skipped_count"],
                review["failed_zero_count"]) == (2, 1, 1)
        assert [row["status"] for row in review["rows"]] == ["logged", "logged", "skipped"]

        assert real_finalize(conn, expected_week=1, skipped_slot_ids=[slots[2]],
                             calibrate_tm_slot_ids=calibration_ids) == 2
        for row in review["rows"][:2]:
            assert row["preview"]["after"] == dict(repo.get_training_state(conn, row["slot_id"]))
        assert [row["preview"]["next_plan"] for row in review["rows"][:2]] == (
            training.training_plan(conn)["slots"][:2]
        )


def test_submit_revalidates_changes_after_review_without_another_preview(tmp_path,
                                                                        monkeypatch):
    app = create_app(
        db_path=str(tmp_path / "training.db"), backup_dir=str(tmp_path / "backups"),
        test_config={"TESTING": True},
    )
    with closing(db.connect(app.config["DB_PATH"])) as conn, app.test_client() as client:
        slot_id = repo.create_pure_bodyweight_training_slot(
            conn, name="Push-up", day=1, sort_order=0, sets=3,
        )
        training.save_draft_set(
            conn, expected_week=1, slot_id=slot_id, set_number=3,
            actual_added_weight=0, reps=37, bodyweight_kg=75, drives_progression=True,
        )
        assert client.post("/log/review", data={"expected_week": "1"}).status_code == 200
        new_slot = repo.create_pure_bodyweight_training_slot(
            conn, name="New unresolved lift", day=1, sort_order=1, sets=3,
        )

        def unexpected_review(*args, **kwargs):
            raise AssertionError("submission must not compute a discarded preview")

        monkeypatch.setattr(plan_routes, "review_week_settlement", unexpected_review)
        response = client.post("/log", data={"expected_week": "1"})
        assert response.status_code == 400
        assert b"unresolved training slots" in response.data
        assert repo.get_settings(conn)["week"] == 1
        assert repo.get_training_session(conn, program_week=1, day=1)["finalized_at"] is None
        assert not list((tmp_path / "backups").glob("*.db.bak"))
        training.save_week_skip(conn, expected_week=1, slot_id=new_slot, skipped=True)
        assert client.post("/log", data={"expected_week": "1"}).status_code == 302
        assert repo.get_settings(conn)["week"] == 2
