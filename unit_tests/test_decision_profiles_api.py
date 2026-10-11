"""Focused persistence and HTTP tests for Decision Profile management."""

import sqlite3

import pytest

from app import app
from models.db import db


@pytest.fixture
def client():
    client = app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True
    return client


def _model(model_id="test/profile-primary"):
    return db.create_model({
        "id": model_id,
        "name": model_id,
        "type": "remote",
        "provider": "test",
        "model_name": model_id.rsplit("/", 1)[-1],
        "capabilities": {"decision": {"enabled": True, "schema_versions": ["decision-schema/v1"]}},
    })


def _payload(key="application.example", **overrides):
    data = {
        "profile_key": key,
        "display_name": "Example decision",
        "description": "A managed test profile.",
        "enabled": True,
        "mode": "enforce",
        "schema_version": "decision-schema/v1",
        "policy_version": "policy/v1",
        "schema": {"version": "decision-schema/v1", "fields": [
            {"key": "approved", "kind": "boolean"},
        ]},
        "primary_model_id": "test/profile-primary",
        "fallback_model_id": None,
        "timeout_ms": 1200,
        "retry_limit": 1,
        "minimum_confidence": 0.75,
    }
    data.update(overrides)
    return data


def test_schema_is_created_idempotently_and_profile_round_trips():
    _model()
    db._init_tables()
    created = db.create_decision_profile(_payload())
    assert created["profile_key"] == "application.example"
    assert created["schema"]["fields"] == [{
        "key": "approved", "kind": "boolean", "description": "",
        "required": True, "nullable": False,
    }]
    assert created["revision"] == 1

    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM decision_profiles").fetchone()[0] == 1


def test_api_crud_disable_conflict_and_secret_free_model_reference(client):
    _model()
    created = client.post("/api/admin/decision-profiles", json=_payload())
    assert created.status_code == 201
    profile = created.get_json()["profile"]
    assert profile["primary_model_id"] == "test/profile-primary"
    assert "api_key" not in profile

    read = client.get("/api/admin/decision-profiles/application.example")
    assert read.status_code == 200
    assert read.get_json()["profile"]["schema"] == profile["schema"]

    update = _payload(enabled=False, mode="off", revision=profile["revision"])
    disabled = client.put("/api/admin/decision-profiles/application.example", json=update)
    assert disabled.status_code == 200
    assert disabled.get_json()["profile"]["enabled"] is False
    assert disabled.get_json()["profile"]["revision"] == 2

    stale = client.put("/api/admin/decision-profiles/application.example", json=update)
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "conflict"
    assert client.get("/api/admin/decision-profiles?enabled_only=1").get_json()["profiles"] == []


def test_api_rejects_invalid_values_and_unknown_model_with_actionable_errors(client):
    _model()
    response = client.post("/api/admin/decision-profiles", json=_payload(
        key="badkey", timeout_ms=0, primary_model_id="missing/model",
    ))
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "invalid_key"
    assert error["path"] == "profile_key"

    response = client.post("/api/admin/decision-profiles", json=_payload(
        key="application.unknown_model", primary_model_id="missing/model",
    ))
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "unknown_model",
        "path": "primary_model_id",
        "message": "does not reference a configured model",
    }

    response = client.post("/api/admin/decision-profiles", json=_payload(
        key="application.invalid_schema", schema={"version": "decision-schema/v1", "fields": []},
    ))
    assert response.status_code == 400
    assert response.get_json()["error"]["path"].startswith("schema.")


def test_builtin_profile_cannot_be_deleted_but_can_be_deactivated(client):
    _model()
    create = client.post("/api/admin/decision-profiles", json=_payload("safety.command"))
    profile = create.get_json()["profile"]

    deleted = client.delete("/api/admin/decision-profiles/safety.command")
    assert deleted.status_code == 409
    assert deleted.get_json()["error"]["code"] == "builtin_profile"

    disabled = client.put("/api/admin/decision-profiles/safety.command", json=_payload(
        "safety.command", enabled=False, mode="off", revision=profile["revision"],
    ))
    assert disabled.status_code == 200
    assert disabled.get_json()["profile"]["enabled"] is False


def test_non_builtin_can_be_deleted_and_routes_require_authentication(client):
    _model()
    assert client.post("/api/admin/decision-profiles", json=_payload()).status_code == 201
    assert client.delete("/api/admin/decision-profiles/application.example").status_code == 200
    assert client.get("/api/admin/decision-profiles/application.example").status_code == 404

    anonymous = app.test_client()
    assert anonymous.get("/api/admin/decision-profiles").status_code == 401


def test_api_rejects_models_without_decision_capability(client):
    db.create_model({
        "id": "test/not-decision",
        "name": "not decision",
        "type": "remote",
        "provider": "test",
        "model_name": "not-decision",
    })
    response = client.post("/api/admin/decision-profiles", json=_payload(
        key="application.incompatible", primary_model_id="test/not-decision",
    ))
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "incompatible_model",
        "path": "primary_model_id",
        "message": "must reference a model enabled for Decision Models",
    }
