"""Flask app factory + launch."""
import os
import webbrowser
from threading import Timer
from flask import Flask
from .db import close_db, connect, DEFAULT_DB_PATH
from .migration import migrate_to_v2


def create_app(db_path: str | None = None, backup_dir: str | None = None,
               test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config["DB_PATH"] = db_path or DEFAULT_DB_PATH
    app.config["BACKUP_DIR"] = backup_dir or os.path.join(
        os.path.dirname(app.config["DB_PATH"]), "backups")
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    if test_config:
        app.config.update(test_config)

    # ADR 0009: bootstrap schema once at startup (out of the per-request get_db()).
    _bootstrap = connect(app.config["DB_PATH"])
    try:
        migrate_to_v2(
            _bootstrap,
            db_path=app.config["DB_PATH"],
            backup_dir=app.config["BACKUP_DIR"],
        )
    finally:
        _bootstrap.close()

    from .routes.plan import bp as plan_bp
    app.register_blueprint(plan_bp)
    from .routes.lifts import bp as lifts_bp
    from .routes.settings import bp as settings_bp
    app.register_blueprint(lifts_bp)
    app.register_blueprint(settings_bp)
    from .routes.schedule import bp as schedule_bp
    app.register_blueprint(schedule_bp)
    from .routes.reseed import bp as reseed_bp
    app.register_blueprint(reseed_bp)
    from .routes.training import bp as training_bp
    app.register_blueprint(training_bp)

    from .services.reseed import due_lifts
    from sbs_cli.data.schema import LEGAL_COMBOS, LOAD_MODELS, MODES

    @app.context_processor
    def inject_globals():
        from .db import get_db
        conn = get_db()
        try:
            due, _ = due_lifts(conn)
            reseed_count = len(due)
        except Exception:
            reseed_count = 0
        legal_map = {lm: [m for m in MODES if (lm, m) in LEGAL_COMBOS]
                     for lm in LOAD_MODELS}
        return {"reseed_count": reseed_count, "legal_map": legal_map}

    app.teardown_appcontext(close_db)
    return app


def run(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    app = create_app()
    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    app.run(host=host, port=port)
