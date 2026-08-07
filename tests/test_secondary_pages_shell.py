import re

import pytest

from tests.v1_helpers import mirror_legacy_lift
from webapp import repo


SECONDARY_PAGES = (
    ("/lifts", "Lift 管理"),
    ("/schedule", "21 周 Schedule"),
    ("/reseed", "Reseed"),
    ("/settings", "Settings"),
)


@pytest.mark.parametrize(("path", "current_label"), SECONDARY_PAGES)
def test_secondary_pages_share_sidebar_and_highlight_current_page(
    client, path, current_label
):
    response = client.get(path)
    html = " ".join(response.get_data(as_text=True).split())

    assert response.status_code == 200
    assert '<nav class="sidebar">' in html
    assert all(group in html for group in ("训练", "动作", "配置"))
    assert all(
        f'>{label}</a>' in html
        for label in ("Week Workspace", "21 周 Schedule", "Lift 管理", "Settings")
    )
    assert ">Reseed</a>" in html
    assert html.count('class="active"') == 1
    assert f'class="active">{current_label}</a>' in html


@pytest.mark.parametrize(
    ("path", "terms"),
    (
        (
            "/lifts",
            (
                "Lift 管理",
                "Progression Mode",
                "Training Max",
                "Working Weight",
                "Added weight",
            ),
        ),
        (
            "/schedule",
            (
                "21 周 Schedule",
                "Schedule week",
                "Main",
                "Aux",
                "Intensity",
                "Reps",
                "Rep-out",
            ),
        ),
        (
            "/settings",
            (
                "Settings",
                "Rounding quantum",
                "Progression step",
                "Bodyweight",
                "Progression Mode",
            ),
        ),
    ),
)
def test_secondary_pages_use_shared_domain_terms(client, path, terms):
    response = client.get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert all(term in html for term in terms)
    assert all(
        workspace_term not in html
        for workspace_term in ("Week Ledger", "聚焦检查器", "最终复核")
    )


def test_reseed_page_uses_cycle_skip_language(client, app):
    with app.app_context():
        from webapp.db import connect

        conn = connect(app.config["DB_PATH"])
        repo.set_week(conn, 22)
        lift_id = repo.create_lift(
            conn,
            name="Squat",
            load_model="barbell",
            mode="sbs",
            day=1,
            sort_order=0,
            sets=5,
            max=100.0,
            intensity=None,
            reps=None,
            repout=None,
            start=None,
            lift_kind="main",
        )
        mirror_legacy_lift(conn, lift_id)
        conn.close()

    response = client.get("/reseed")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert all(
        term in html
        for term in (
            "周期 2 · Reseed",
            "当前 Training Max",
            "新 Training Max",
            "应用 Reseed",
            "跳过本次 Reseed",
        )
    )
    assert "本周跳过" not in html


def test_lift_management_rows_and_edit_forms_use_glossary(client, make_lift):
    lift_id = make_lift(
        name="Squat",
        mode="sbs",
        sets=5,
        max=100.0,
        lift_kind="main",
        start=None,
    )
    bodyweight_lift_id = make_lift(
        name="Weighted Pull-up",
        load_model="bodyweight",
        mode="linear_t3",
        sets=3,
        max=None,
        start=10.0,
        bodyweight_pct=1.0,
    )
    barbell_lift_id = make_lift(
        name="Rows",
        load_model="barbell",
        mode="linear_t3",
        sets=3,
        max=None,
        start=40.0,
    )

    page_html = client.get("/lifts").get_data(as_text=True)
    edit_html = client.get(f"/lifts/{lift_id}/edit").get_data(as_text=True)
    barbell_edit_html = client.get(f"/lifts/{barbell_lift_id}/edit").get_data(
        as_text=True
    )
    bodyweight_edit_html = client.get(
        f"/lifts/{bodyweight_lift_id}/edit"
    ).get_data(as_text=True)

    assert all(
        term in page_html
        for term in (
            "Day 1",
            "5 Sets",
            "Training Max seed",
            "起始 Working Weight 40.0",
            "起始 Added weight 10.0",
            "编辑 Lift",
        )
    )
    assert "data-linear-field hidden" in page_html
    assert all(
        term in edit_html
        for term in (
            "Lift 名称",
            "Load Model",
            "Progression Mode",
            "Training Max seed",
            "保存 Lift",
            "删除 Lift",
        )
    )
    assert 'name="start"' not in edit_html
    assert "起始 Working Weight" in barbell_edit_html
    assert "起始 Added weight" in bodyweight_edit_html


def _assert_action_level(html, label, level):
    assert re.search(
        rf'<(?:button|a)\b[^>]*class="[^"]*\b{level}\b[^"]*"[^>]*>'
        rf"\s*{re.escape(label)}\s*</(?:button|a)>",
        html,
    )


def test_secondary_pages_render_consistent_action_hierarchy(
    client, make_lift, db_conn
):
    lift_id = make_lift(
        name="Bench",
        mode="sbs",
        sets=5,
        max=100.0,
        lift_kind="main",
        start=None,
    )
    repo.set_week(db_conn, 22)
    db_conn.commit()

    lifts_html = client.get("/lifts").get_data(as_text=True)
    edit_html = client.get(f"/lifts/{lift_id}/edit").get_data(as_text=True)
    schedule_html = client.get("/schedule").get_data(as_text=True)
    reseed_html = client.get("/reseed").get_data(as_text=True)
    settings_html = client.get("/settings").get_data(as_text=True)

    _assert_action_level(lifts_html, "新增 Lift", "btn-primary")
    _assert_action_level(edit_html, "保存 Lift", "btn-primary")
    _assert_action_level(edit_html, "取消", "btn-ghost")
    _assert_action_level(edit_html, "删除 Lift", "btn-danger")
    _assert_action_level(schedule_html, "保存 Schedule", "btn-primary")
    _assert_action_level(schedule_html, "恢复默认 Schedule", "btn-danger")
    _assert_action_level(reseed_html, "应用 Reseed", "btn-primary")
    _assert_action_level(reseed_html, "跳过本次 Reseed", "btn-ghost")
    _assert_action_level(settings_html, "保存 Settings", "btn-primary")
    _assert_action_level(settings_html, "↺ 默认", "btn-ghost")
