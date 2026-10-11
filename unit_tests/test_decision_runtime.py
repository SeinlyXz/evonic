"""Tests for bounded, provider-neutral DecisionRuntime orchestration."""
from dataclasses import dataclass

import pytest

from backend.tools.lib.decision_models import (
    DecisionCancellation, DecisionError, DecisionErrorCode, DecisionFieldResult,
    DecisionResult, ProviderMetadata, TimingMetadata,
)
from backend.tools.lib.decision_runtime import (
    DecisionRuntime, DecisionRuntimeError, DecisionRuntimeErrorCode,
    FixedWindowRateLimiter, RuntimeRequest,
)


def _model(model_id):
    return {
        "id": model_id, "provider": "test", "model_name": model_id,
        "enabled": True, "api_format": "openai", "timeout": 30,
        "capabilities": {"decision": {"structured_output": True,
            "schema_primitives": ["boolean"]}},
    }


def _profile(**overrides):
    profile = {
        "profile_key": "application.example", "enabled": True, "mode": "enforce",
        "policy_version": "1", "schema_version": "decision-schema/v1",
        "schema": {"version": "decision-schema/v1", "fields": [
            {"key": "approved", "kind": "boolean", "description": "Approval"},
        ]},
        "primary_model_id": "primary", "fallback_model_id": "fallback",
        "timeout_ms": 1000, "retry_limit": 1, "minimum_confidence": 0.5,
    }
    profile.update(overrides)
    return profile


class FakeDB:
    def __init__(self, profile=None, models=None):
        self.profile = profile or _profile()
        self.models = models or {"primary": _model("primary"), "fallback": _model("fallback")}

    def get_decision_profile(self, key):
        return self.profile if key == self.profile["profile_key"] else None

    def validate_decision_profile(self, data, *, existing=None):
        return data

    def get_model_by_id(self, model_id):
        return self.models.get(model_id)


@dataclass
class FakeAdapter:
    result: DecisionResult
    calls: int = 0
    key: str = "fake"

    def decide(self, invocation):
        self.calls += 1
        return self.result


def _result(invocation, *, error=None, confidence=0.9, text=None):
    fields = () if error else (DecisionFieldResult("approved", True, confidence),)
    if text:
        fields = (DecisionFieldResult("approved", True, confidence),)
    return DecisionResult(invocation.profile, invocation.schema.version, fields,
        ProviderMetadata("test", "model"), TimingMetadata(1, 1), 1, error=error)


def _runtime(db, adapters, **kwargs):
    def factory(model):
        return adapters.pop(0)
    return DecisionRuntime(db, adapter_factory=factory, **kwargs)


def _request(**overrides):
    request = RuntimeRequest("application.example", "1", {"subject": "sample"})
    return type(request)(**{**request.__dict__, **overrides})


def test_normal_result_is_validated_and_contains_only_normalized_metadata():
    adapter = FakeAdapter(None)
    runtime = _runtime(FakeDB(), [adapter])
    # The adapter needs the runtime-created invocation; return it through a closure.
    class DynamicAdapter:
        key = "fake"
        def decide(self, invocation):
            return _result(invocation)
    runtime = _runtime(FakeDB(), [DynamicAdapter()])
    result = runtime.invoke(_request())
    assert result.error is None
    assert result.fields[0].value is True
    assert result.provider.model_id == "model"
    assert result.attempts == 1


def test_provider_failure_uses_fallback_deterministically():
    class Failure:
        key = "failure"
        def decide(self, invocation):
            return _result(invocation, error=DecisionError(DecisionErrorCode.PROVIDER_UNAVAILABLE, "internal provider text", True))
    class Success:
        key = "success"
        def decide(self, invocation): return _result(invocation)
    result = _runtime(FakeDB(), [Failure(), Success()]).invoke(_request())
    assert result.error is None
    assert result.attempts == 2
    assert result.fallback.used is True


def test_timeout_uses_fallback_and_returns_safe_result():
    class Timeout:
        key = "timeout"
        def decide(self, invocation): raise TimeoutError("provider endpoint detail")
    class Success:
        key = "success"
        def decide(self, invocation): return _result(invocation)
    result = _runtime(FakeDB(), [Timeout(), Success()]).invoke(_request())
    assert result.error is None and result.fallback.used


def test_cancellation_is_terminal_and_does_not_invoke_adapter():
    adapter = FakeAdapter(None)
    result = _runtime(FakeDB(), [adapter]).invoke(_request(cancellation=DecisionCancellation(cancelled=True)))
    assert result.error.code is DecisionErrorCode.CANCELLED
    assert adapter.calls == 0


def test_malformed_output_falls_back():
    class Invalid:
        key = "invalid"
        def decide(self, invocation):
            return DecisionResult(invocation.profile, invocation.schema.version,
                (DecisionFieldResult("approved", "not-a-bool", 0.9),), None, TimingMetadata(1), 1)
    class Success:
        key = "success"
        def decide(self, invocation): return _result(invocation)
    result = _runtime(FakeDB(), [Invalid(), Success()]).invoke(_request())
    assert result.error is None and result.attempts == 2


def test_low_confidence_falls_back():
    class Low:
        key = "low"
        def decide(self, invocation): return _result(invocation, confidence=0.1)
    class Success:
        key = "success"
        def decide(self, invocation): return _result(invocation)
    result = _runtime(FakeDB(), [Low(), Success()]).invoke(_request())
    assert result.error is None and result.attempts == 2


def test_rate_limit_is_enforced_before_invocation():
    runtime = _runtime(FakeDB(), [], rate_limiter=FixedWindowRateLimiter(limit=0))
    with pytest.raises(DecisionRuntimeError) as exc:
        runtime.invoke(_request())
    assert exc.value.code is DecisionRuntimeErrorCode.RATE_LIMITED


def test_secret_like_context_is_rejected_without_echoing_value():
    runtime = _runtime(FakeDB(), [])
    with pytest.raises(DecisionRuntimeError) as exc:
        runtime.invoke(_request(input_context={"authorization": "Bearer dont-return-this"}))
    assert exc.value.code is DecisionRuntimeErrorCode.SECRET_DETECTED
    assert "dont-return-this" not in str(exc.value)
