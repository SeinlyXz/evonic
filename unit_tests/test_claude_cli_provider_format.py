"""A provider created or edited through the API keeps api_format=claude_cli."""

from unittest.mock import patch


def _client():
    from app import app

    client = app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True
    return client


def test_claude_cli_format_survives_create_and_update():
    from models.db import db

    pid = db.create_provider({"id": "cli-format-test", "name": "Claude Code (CLI)", "api_format": "claude_cli"})
    assert db.get_provider(pid)["api_format"] == "claude_cli"

    db.update_provider(pid, {"name": "Claude CLI renamed"})
    assert db.get_provider(pid)["api_format"] == "claude_cli"

    db.update_provider(pid, {"api_format": "claude_cli", "enabled": 1})
    assert db.get_provider(pid)["api_format"] == "claude_cli"


def test_fetch_models_for_api_created_claude_cli_provider():
    from models.db import db

    pid = db.create_provider({"id": "cli-fetch-test", "name": "Claude Code (CLI)", "api_format": "claude_cli"})
    with patch("backend.provider.claude_cli.get_status", return_value={"logged_in": True, "version": "x", "error": None}):
        result = _client().post(f"/api/providers/{pid}/fetch-models")

    assert result.status_code == 200
    assert result.get_json()["success"] is True
