"""Unit tests for routes._forms.present_fields — the shared cast-or-reject helper."""
from webapp.routes._forms import present_fields, LIFT_FIELD_CASTS


def test_parses_present_fields(client, app):
    with app.test_request_context("/", method="POST",
                                  data={"day": "3", "sets": "5"}):
        fields, bad = present_fields({"day": int, "sets": int, "max": float})
    assert fields == {"day": 3, "sets": 5}
    assert bad is None


def test_empty_string_treated_as_absent(client, app):
    with app.test_request_context("/", method="POST",
                                  data={"day": "", "sets": "4"}):
        fields, bad = present_fields({"day": int, "sets": int})
    assert fields == {"sets": 4}  # empty day skipped, not an error
    assert bad is None


def test_bad_value_reports_column(client, app):
    with app.test_request_context("/", method="POST",
                                  data={"day": "abc", "sets": "4"}):
        fields, bad = present_fields({"day": int, "sets": int})
    assert fields is None and bad == "day"


def test_missing_column_skipped(client, app):
    with app.test_request_context("/", method="POST", data={}):
        fields, bad = present_fields({"day": int})
    assert fields == {} and bad is None


def test_lift_schema_casts_all_columns(client, app):
    data = {"name": "Squat", "mode": "sbs", "day": "1", "sets": "5",
            "max": "135.5", "intensity": "0.7", "reps": "5", "repout": "10",
            "start": "100.0", "lift_kind": "main", "bodyweight_pct": "0.0"}
    with app.test_request_context("/", method="POST", data=data):
        fields, bad = present_fields(LIFT_FIELD_CASTS)
    assert bad is None
    assert fields["max"] == 135.5 and fields["reps"] == 5 and fields["name"] == "Squat"
