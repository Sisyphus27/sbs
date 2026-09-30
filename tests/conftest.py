import pytest
from webapp.app import create_app
from webapp import db, repo


@pytest.fixture()
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    backup_dir = str(tmp_path / "backups")
    app = create_app(db_path=db_path, backup_dir=backup_dir,
                     test_config={"TESTING": True})
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_conn(app):
    """Yield an open connection to the test DB; close on teardown.

    Replaces the repeated `with app.app_context(): conn = connect(...); ...;
    conn.close()` boilerplate. Caller still wraps writes in app context where a
    route/request needs it, but plain seed+assert blocks just use this."""
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        yield conn
        conn.close()


@pytest.fixture()
def make_lift(db_conn):
    """Create a slot using the same current schema as normal app startup."""
    def _make(**kwargs):
        defaults = dict(name="Lift", load_model="barbell", mode="linear_t3",
                        day=1, sort_order=0, sets=3, max=None, intensity=None,
                        reps=None, repout=None, start=30.0)
        defaults.update(kwargs)
        lift_id = repo.create_training_slot(db_conn, **defaults)
        return lift_id
    return _make


@pytest.fixture()
def legacy_conn(tmp_path):
    """The old schema is only for explicit legacy repository/tool tests."""
    conn = db.connect(str(tmp_path / "legacy.db"))
    db.init_schema(conn)
    yield conn
    conn.close()
