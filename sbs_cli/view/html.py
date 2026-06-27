"""Render week-N.html (form + JS export) and parse exported log JSON."""
import json
import os
from jinja2 import Environment, FileSystemLoader
from ..program import week_plan

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=False)


def render_week_html(profile, state, week: int) -> str:
    by_day = []
    for day in range(1, profile.days_per_week + 1):
        items = week_plan(profile, state, day=day)
        if items:
            by_day.append((day, items))
    tmpl = _env.get_template("week.html.j2")
    return tmpl.render(week=week, by_day=by_day)


def parse_log_json(text: str) -> dict:
    """Parse a week-N-log.json. Returns {week: int, logs: {lift_name: reps}}."""
    data = json.loads(text)
    return {"week": int(data["week"]), "logs": {k: int(v) for k, v in data.get("logs", {}).items()}}
