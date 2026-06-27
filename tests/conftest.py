import os
import pytest
from webapp.app import create_app
from webapp import db


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
