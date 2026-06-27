from flask import Blueprint
bp = Blueprint("settings", __name__)


@bp.route("/settings")
def view():
    return "settings stub"
