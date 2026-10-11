"""DMSS Decision Profile bridge regression coverage (no command execution)."""
from types import SimpleNamespace

from backend.dmss_decision_profile import SafetyCommandOutcome
from backend.tools.lib.safety_pipeline import SafetyPipeline


class Checker:
    def __init__(self, score=0):
        self.score = score

    def check(self, *_args):
        return {"score": self.score, "reasons": [], "blocked_patterns": [], "matched_patterns": []}


class ProfilePipeline(SafetyPipeline):
    def __init__(self, outcome):
        super().__init__(register_defaults=False)
        self.register(Checker())
        self.outcome = outcome

    def _safety_command_profile(self):
        return {"profile_key": "safety.command"}

    def _run_safety_command_profile(self, *_args):
        return self.outcome


def test_shadow_profile_never_changes_hmads_verdict():
    pipeline = ProfilePipeline(SafetyCommandOutcome(True, mode="shadow", decision="block", confidence=.99))
    result = pipeline.check("echo safe", "bash", {})
    assert result["level"] == "safe"
    assert result["decision_source"] == "deterministic_shadow"


def test_enforce_profile_cannot_weaken_hmads_block():
    pipeline = ProfilePipeline(SafetyCommandOutcome(True, mode="enforce", decision="allow", confidence=.99))
    pipeline._checkers = [Checker(15)]
    result = pipeline.check("synthetic", "bash", {})
    assert result["level"] == "dangerous"
    assert result["decim_safety"]["final_reason"] == "hmads_floor"


def test_profile_failure_uses_exact_deterministic_fallback():
    pipeline = ProfilePipeline(SafetyCommandOutcome(True, mode="enforce", fallback_reason="low_confidence"))
    expected = pipeline.check_deterministic("synthetic", "bash", {})
    result = pipeline.check("synthetic", "bash", {})
    assert result["level"] == expected["level"]
    assert result["decision_source"] == "deterministic_fallback"
    assert result["decim_safety"]["fallback_reason"] == "low_confidence"


def test_profile_enforce_maps_review_without_executing_command():
    pipeline = ProfilePipeline(SafetyCommandOutcome(True, mode="enforce", decision="review", confidence=.99))
    result = pipeline.check("synthetic", "bash", {})
    assert result["level"] == "requires_approval"
    assert result["requires_approval"] is True
