"""Authenticated management API for durable Decision Profiles.

Global authentication and CSRF middleware in :mod:`app` protects this blueprint.
The responses intentionally contain only model IDs, never model credentials.
"""

from __future__ import annotations

from typing import Any, Mapping

from flask import Blueprint, jsonify, request

from models.db import db
from models.mixins.decision_profiles import DecisionProfileValidationError


decision_profiles_bp = Blueprint("decision_profiles", __name__)


def _error(exc: DecisionProfileValidationError, status: int = 400):
    return jsonify({
        "success": False,
        "error": {
            "code": exc.code,
            "path": exc.path,
            "message": str(exc),
        },
    }), status


def _payload() -> Mapping[str, Any] | None:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@decision_profiles_bp.route("/api/admin/decision-profiles", methods=["GET"])
def list_decision_profiles():
    """List profiles, including disabled profiles unless ``enabled_only=1``."""
    enabled_only = request.args.get("enabled_only") in {"1", "true", "True"}
    return jsonify({"profiles": db.list_decision_profiles(include_disabled=not enabled_only)})


@decision_profiles_bp.route("/api/admin/decision-profiles", methods=["POST"])
def create_decision_profile():
    """Create a profile with a stable, never-renamed key."""
    data = _payload()
    if data is None:
        return jsonify({"success": False, "error": {"code": "invalid_payload", "path": "$", "message": "must be a JSON object"}}), 400
    try:
        profile = db.create_decision_profile(data)
    except DecisionProfileValidationError as exc:
        return _error(exc, 409 if exc.code == "already_exists" else 400)
    return jsonify({"success": True, "profile": profile}), 201


@decision_profiles_bp.route("/api/admin/decision-profiles/<path:profile_key>", methods=["GET"])
def get_decision_profile(profile_key: str):
    profile = db.get_decision_profile(profile_key)
    if not profile:
        return jsonify({"success": False, "error": {"code": "not_found", "path": "profile_key", "message": "profile not found"}}), 404
    return jsonify({"profile": profile})


@decision_profiles_bp.route("/api/admin/decision-profiles/<path:profile_key>", methods=["PUT"])
def update_decision_profile(profile_key: str):
    """Replace/update a profile using its current revision for conflict detection."""
    data = _payload()
    if data is None:
        return jsonify({"success": False, "error": {"code": "invalid_payload", "path": "$", "message": "must be a JSON object"}}), 400
    revision = data.pop("revision", None)
    try:
        profile = db.update_decision_profile(profile_key, data, revision)
    except DecisionProfileValidationError as exc:
        return _error(exc, 409 if exc.code == "conflict" else 400)
    if not profile:
        return jsonify({"success": False, "error": {"code": "not_found", "path": "profile_key", "message": "profile not found"}}), 404
    return jsonify({"success": True, "profile": profile})


@decision_profiles_bp.route("/api/admin/decision-profiles/<path:profile_key>", methods=["DELETE"])
def delete_decision_profile(profile_key: str):
    """Delete non-built-in profiles; built-ins are safely deactivated by PUT."""
    try:
        deleted = db.delete_decision_profile(profile_key)
    except DecisionProfileValidationError as exc:
        return _error(exc, 409)
    if not deleted:
        return jsonify({"success": False, "error": {"code": "not_found", "path": "profile_key", "message": "profile not found"}}), 404
    return jsonify({"success": True})
