from flask import Blueprint
bp = Blueprint("lifts", __name__)


@bp.route("/lifts")
def view():
    return "lifts stub"
