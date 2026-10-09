"""HTTP-surface tests for the consolidated Safety page (task #836).

Pins the navigation-consolidation contract:

* ``/system/safety`` renders the page shell with accessible tab semantics
  (General / HMADS / DMSS) and embeds the HMADS rules UI plus the DMSS
  dashboard,
* the legacy ``/system/decim-safety`` dashboard route still resolves via a
  redirect to the DMSS tab of the Safety page,
* the settings console links to Safety and no longer carries its own HMADS
  section (the old ``#hmads`` hash is migrated client-side).
"""

from app import app


def _client():
    client = app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True
    return client


# ---------------------------------------------------------------------------
# Safety page shell
# ---------------------------------------------------------------------------

def test_safety_page_renders_with_accessible_tabs():
    client = _client()
    resp = client.get("/system/safety")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # ARIA tab semantics
    assert 'role="tablist"' in html
    assert html.count('role="tab"') >= 3
    assert html.count('role="tabpanel"') >= 3

    # All three tabs and their panels are wired
    for tab in ("general", "hmads", "dmss"):
        assert f'data-tab="{tab}"' in html
        assert f'id="safety-panel-{tab}"' in html
        assert f'aria-controls="safety-panel-{tab}"' in html


def test_safety_page_embeds_hmads_and_dmss_surfaces():
    client = _client()
    html = client.get("/system/safety").get_data(as_text=True)

    # HMADS rules CRUD (from partials/hmads.html)
    assert "hmads-rules-body" in html
    assert "hmads-modal" in html

    # DMSS dashboard (migrated from the legacy Decim Safety page)
    assert "tbl-events-body" in html
    assert "dmss-state-badge" in html
    assert "kpi-fallback" in html

    # Static assets are wired
    assert "css/safety.css" in html
    assert "js/safety.js" in html


def test_safety_general_tab_explains_policy_choice_and_fallback():
    client = _client()
    html = client.get("/system/safety").get_data(as_text=True)

    # The General tab must explain both policy options…
    assert "HMADS only" in html
    assert "DMSS enabled" in html
    # …and the deterministic HMADS fallback guarantee.
    assert "fallback" in html.lower()
    assert "request_timeout_ms" in html
    assert "minimum_confidence" in html


# ---------------------------------------------------------------------------
# Legacy route preservation
# ---------------------------------------------------------------------------

def test_legacy_decim_safety_route_redirects_to_safety_dmss_tab():
    client = _client()
    resp = client.get("/system/decim-safety")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/system/safety#dmss"


def test_settings_console_links_to_safety_and_drops_hmads_section():
    client = _client()
    resp = client.get("/system")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # The nav rail now points at the consolidated Safety page…
    assert 'href="/system/safety"' in html
    # …and the old HMADS section is gone from the settings console.
    assert 'id="section-hmads"' not in html
    assert 'data-section="hmads"' not in html
    assert "partials/hmads.html" not in html
