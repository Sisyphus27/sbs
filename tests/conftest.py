import pytest
from webapp.app import create_app
from webapp import db, repo


@pytest.fixture()
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    backup_dir = str(tmp_path / "backups")
    app = create_app(db_path=db_path, backup_dir=backup_dir,
                     test_config={"TESTING": True})
    with app.app_context():
        conn = db.connect(db_path)
        db.init_schema(conn)
        conn.close()
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
    """Factory: create a lift row and return its id.

    Keyword args pass straight through to repo.create_lift; sensible defaults
    mirror the canonical barbell lift so tests only state what they override.
    Usage: make_lift(name="Squat", mode="sbs", max=135.0, lift_kind="main")."""
    def _make(**kwargs):
        defaults = dict(name="Lift", load_model="barbell", mode="linear_t3",
                        day=1, sort_order=0, sets=3, max=None, intensity=None,
                        reps=None, repout=None, start=30.0)
        defaults.update(kwargs)
        return repo.create_lift(db_conn, **defaults)
    return _make
