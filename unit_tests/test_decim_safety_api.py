"""HTTP-surface tests for Decim Safety settings and the admin telemetry API."""

from unittest.mock import patch

import pytest

from app import app
from models.db import db


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    db.invalidate_settings_cache()
    yield
    db.invalidate_settings_cache()


def _client():
    client = app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True
    return client


# ---------------------------------------------------------------------------
# Settings surface
# ---------------------------------------------------------------------------

def test_settings_default_to_off_and_provider_neutral():
    client = _client()
    body = client.get("/api/settings/decim-safety").get_json()["settings"]
    assert body["enabled"] is False
    assert body["mode"] == "off"
    assert body["provider"] == "systemone"
    # No endpoint/credential fields may leak through the public surface.
    assert "endpoint" not in body
    assert "model_allowlist" not in body


def test_settings_round_trip_writes_and_reads_back():
    client = _client()
    response = client.put("/api/settings/decim-safety", json={
        "enabled": True,
        "mode": "shadow",
        "provider": "systemone",
        "request_timeout_ms": 2000,
        "minimum_confidence": 0.95,
        "max_payload_chars": 8000,
        "circuit_breaker_failures": 4,
        "circuit_breaker_cooldown_seconds": 120,
        "record_enforce_events": True,
        "retention_days": 14,
    })
    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] is True
    assert result["settings"]["enabled"] is True
    assert result["settings"]["mode"] == "shadow"
    assert result["settings"]["minimum_confidence"] == 0.95

    assert db.get_setting("decim_safety.mode") == "shadow"
    assert db.get_setting("decim_safety.enabled") == "1"
    assert client.get("/api/settings/decim-safety").get_json()["settings"]["mode"] == "shadow"


def test_settings_reject_invalid_mode():
    client = _client()
    response = client.put("/api/settings/decim-safety", json={"mode": "turbo"})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_settings_reject_unregistered_provider():
    client = _client()
    response = client.put("/api/settings/decim-safety", json={"provider": "vendor-x"})
    assert response.status_code == 400


def test_settings_reject_out_of_range_confidence():
    client = _client()
    response = client.put("/api/settings/decim-safety", json={"minimum_confidence": 1.5})
    assert response.status_code == 400


def test_settings_change_is_audited():
    client = _client()
    with patch("routes.settings.audit.log_setting_change") as logger:
        client.put("/api/settings/decim-safety", json={"mode": "enforce"})
    logger.assert_called_once()


# ---------------------------------------------------------------------------
# Admin telemetry API
# ---------------------------------------------------------------------------

def test_health_is_provider_neutral():
    client = _client()
    body = client.get("/api/admin/decim-safety/health").get_json()
    assert body["mode"] == "off"
    assert body["enabled"] is False
    assert "endpoint" not in body
    assert body["circuit_state"] in ("closed", "open", "half-open", "unknown")


def test_summary_and_events_start_empty():
    client = _client()
    summary = client.get("/api/admin/decim-safety/summary").get_json()
    assert summary["total_comparisons"] == 0
    events = client.get("/api/admin/decim-safety/events").get_json()
    assert events["events"] == []
    assert events["total"] == 0


def test_events_ignore_invalid_filters():
    """Invalid filter values are ignored server-side (never a 500 or injection)."""
    client = _client()
    response = client.get("/api/admin/decim-safety/events?mode=bogus&tool_type=java&final_level=nope")
    assert response.status_code == 200
    assert response.get_json()["events"] == []


def test_clear_telemetry_is_audited_and_rolls_epoch():
    from backend.services import decim_safety_telemetry

    client = _client()
    before = decim_safety_telemetry.get_state()["telemetry_epoch"]
    response = client.post("/api/admin/decim-safety/telemetry/clear")
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    after = decim_safety_telemetry.get_state()["telemetry_epoch"]
    assert after == before + 1


def test_event_detail_404_for_unknown_id():
    client = _client()
    assert client.get("/api/admin/decim-safety/events/does-not-exist").status_code == 404
