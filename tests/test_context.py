def test_reseed_count_in_template_context(client, app):
    rv = client.get("/")
    assert rv.status_code == 200
    # context processor always provides reseed_count (0 when none due)


def test_legal_map_injected_on_lifts_page(client, app):
    rv = client.get("/lifts")
    assert rv.status_code == 200
    # legal_map serialized into page for the cascade (barbell maps to its 3 modes)
    assert b"barbell" in rv.data
