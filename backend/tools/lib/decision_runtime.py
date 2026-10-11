"""Secure, domain-neutral Decision Runtime orchestration.

This module owns invocation boundaries, profile/model selection and deterministic
retry/fallback behaviour.  It deliberately does *not* interpret a decision's
fields; consumers retain all domain policy.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from enum import Enum
import json
import logging
import re
import time
from typing import Any, Callable, Mapping, Protocol

from backend.tools.lib.decision_adapters import DecisionCompatibilityError, OpenAIStructuredDecisionAdapter, validate_decision_compatibility
from backend.tools.lib.decision_models import (
    CONTRACT_VERSION, SCHEMA_VERSION, ContractValidationError, DecisionAdapter,
    DecisionCancellation, DecisionError, DecisionErrorCode, DecisionInvocation,
    DecisionProfileRef, DecisionResult, FallbackMetadata, TimingMetadata,
    validate_invocation, validate_result,
)

MAX_PAYLOAD_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_FIELDS = 32
MAX_CHOICES_PER_FIELD = 32
MAX_DESCRIPTION_CHARS = 2_000
MAX_ATTEMPTS = 3
MAX_TIMEOUT_MS = 120_000
_SECRET_PATTERN = re.compile(r"(?i)(?:api[_-]?key|authorization|password|secret|token)\s*[:=]\s*(?:bearer\s+)?[^\s,]+")


class DecisionRuntimeErrorCode(str, Enum):
    PROFILE_NOT_FOUND = "profile_not_found"
    PROFILE_DISABLED = "profile_disabled"
    PROFILE_INVALID = "profile_invalid"
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    SECRET_DETECTED = "secret_detected"
    LOW_CONFIDENCE = "low_confidence"
    RESPONSE_TOO_LARGE = "response_too_large"


class DecisionRuntimeError(ValueError):
    """Safe, typed runtime failure; messages must not contain request data."""
    def __init__(self, code: DecisionRuntimeErrorCode, message: str):
        self.code = code
        super().__init__(message)


class MetricsSink(Protocol):
    def increment(self, name: str, *, tags: Mapping[str, str] | None = None) -> None: ...
    def observe(self, name: str, value: float, *, tags: Mapping[str, str] | None = None) -> None: ...


@dataclass(frozen=True)
class RuntimeRequest:
    profile_key: str
    profile_version: str
    input_context: Mapping[str, Any]
    policy_metadata: Mapping[str, Any] | None = None
    correlation_id: str | None = None
    cancellation: DecisionCancellation | None = None
    channel: str = "internal"
    rate_limit_key: str = "default"


class FixedWindowRateLimiter:
    """Small in-process limiter suitable for internal runtime channels."""
    def __init__(self, limit: int = 60, window_seconds: float = 60.0) -> None:
        self.limit, self.window_seconds = limit, window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        calls = self._calls[key]
        while calls and calls[0] <= now - self.window_seconds:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(now)
        return True


def _safe_json_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _has_secret(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_SECRET_PATTERN.search(value))
    if isinstance(value, Mapping):
        for key, item in value.items():
            # Keys alone are not secrets, but are a reliable indicator that their
            # value must not cross the generic provider boundary.
            if isinstance(key, str) and re.search(r"(?i)(?:api[_-]?key|authorization|password|secret|token)", key):
                return True
            if _has_secret(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_has_secret(item) for item in value)
    return False


def _safe_error(code: DecisionErrorCode, message: str, retryable: bool = False) -> DecisionError:
    return DecisionError(code, message, retryable)


class DecisionRuntime:
    """Resolve profiles and execute bounded, validated decisions.

    ``adapter_factory`` is injected to permit provider-free tests. It receives the
    resolved model mapping, whose credentials are never returned or logged.
    """
    def __init__(self, db: Any, *, adapter_factory: Callable[[Mapping[str, Any]], DecisionAdapter] | None = None,
                 rate_limiter: FixedWindowRateLimiter | None = None, metrics: MetricsSink | None = None,
                 logger: logging.Logger | None = None) -> None:
        self.db = db
        self.adapter_factory = adapter_factory or OpenAIStructuredDecisionAdapter
        self.rate_limiter = rate_limiter or FixedWindowRateLimiter()
        self.metrics, self.logger = metrics, logger or logging.getLogger(__name__)

    def _metric(self, name: str, value: float | None = None, **tags: str) -> None:
        if not self.metrics:
            return
        if value is None:
            self.metrics.increment(name, tags=tags)
        else:
            self.metrics.observe(name, value, tags=tags)

    def _profile(self, request: RuntimeRequest) -> Mapping[str, Any]:
        profile = self.db.get_decision_profile(request.profile_key)
        if not profile:
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PROFILE_NOT_FOUND, "Decision profile was not found.")
        if not profile.get("enabled") or profile.get("mode") == "off":
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PROFILE_DISABLED, "Decision profile is not enabled.")
        if profile.get("policy_version") != request.profile_version:
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PROFILE_INVALID, "Decision profile version does not match.")
        try:
            # Revalidate persisted configuration and schema at invocation time.
            self.db.validate_decision_profile(profile, existing=profile)
        except (ValueError, ContractValidationError) as exc:
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PROFILE_INVALID, "Decision profile configuration is invalid.") from exc
        return profile

    def _invocation(self, request: RuntimeRequest, profile: Mapping[str, Any]) -> DecisionInvocation:
        raw = {"contract_version": CONTRACT_VERSION, "profile": {"key": request.profile_key, "version": request.profile_version},
               "schema": profile["schema"], "input_context": request.input_context,
               "policy_metadata": request.policy_metadata or {}, "correlation_id": request.correlation_id,
               "cancellation": None if request.cancellation is None else {"deadline_unix_ms": request.cancellation.deadline_unix_ms, "cancelled": request.cancellation.cancelled}}
        if _safe_json_bytes(raw) > MAX_PAYLOAD_BYTES:
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PAYLOAD_TOO_LARGE, "Decision request exceeds the payload limit.")
        if _has_secret(raw):
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.SECRET_DETECTED, "Decision request contains a secret-like value.")
        invocation = validate_invocation(raw)
        if len(invocation.schema.fields) > MAX_FIELDS or any(len(field.choices) > MAX_CHOICES_PER_FIELD or len(field.description) > MAX_DESCRIPTION_CHARS for field in invocation.schema.fields):
            raise DecisionRuntimeError(DecisionRuntimeErrorCode.PROFILE_INVALID, "Decision schema exceeds runtime limits.")
        return invocation

    def invoke(self, request: RuntimeRequest) -> DecisionResult:
        """Run primary then fallback deterministically; never emit raw provider data."""
        started = time.monotonic()
        try:
            if not self.rate_limiter.allow(f"{request.channel}:{request.rate_limit_key}"):
                raise DecisionRuntimeError(DecisionRuntimeErrorCode.RATE_LIMITED, "Decision request rate limit exceeded.")
            profile = self._profile(request)
            invocation = self._invocation(request, profile)
            if invocation.cancellation and invocation.cancellation.cancelled:
                return self._failure(invocation, DecisionErrorCode.CANCELLED, "Decision was cancelled.", started)
            model_ids = [profile["primary_model_id"]] + ([profile["fallback_model_id"]] if profile.get("fallback_model_id") else [])
            max_attempts = min(MAX_ATTEMPTS, int(profile["retry_limit"]) + 1)
            last: DecisionResult | None = None
            for attempt in range(max_attempts):
                model_id = model_ids[min(attempt, len(model_ids) - 1)]
                fallback = attempt > 0
                model = self.db.get_model_by_id(model_id)
                try:
                    validate_decision_compatibility(model, invocation)
                    bounded_model = dict(model)
                    bounded_model["timeout"] = min(MAX_TIMEOUT_MS / 1000, float(profile["timeout_ms"]) / 1000)
                    result = self.adapter_factory(bounded_model).decide(invocation)
                    result = replace(result, attempts=attempt + 1, fallback=FallbackMetadata(fallback, "previous_attempt_failed" if fallback else None) if fallback else None)
                    if result.error and result.error.code is DecisionErrorCode.CANCELLED:
                        # Cancellation is terminal: never retry or invoke fallback.
                        return replace(result, timing=TimingMetadata(int((time.monotonic() - started) * 1000), result.timing.provider_ms))
                    if _safe_json_bytes(result.to_dict()) > MAX_RESPONSE_BYTES:
                        raise DecisionRuntimeError(DecisionRuntimeErrorCode.RESPONSE_TOO_LARGE, "Decision response exceeds the response limit.")
                    if result.error is None:
                        result = validate_result(invocation.schema, result)
                        confidences = [field.confidence for field in result.fields if field.confidence is not None]
                        if confidences and min(confidences) < float(profile["minimum_confidence"]):
                            self._metric("decision_runtime.low_confidence", profile=request.profile_key)
                            last = replace(result, error=_safe_error(DecisionErrorCode.PROVIDER_RESPONSE_INVALID, "Decision confidence was below the configured threshold."))
                        else:
                            self._success(result, request, started, fallback)
                            return result
                    else:
                        last = result
                except (DecisionCompatibilityError, ContractValidationError, ValueError, TimeoutError) as exc:
                    code = DecisionErrorCode.DEADLINE_EXCEEDED if isinstance(exc, TimeoutError) else DecisionErrorCode.NO_COMPATIBLE_MODEL if isinstance(exc, DecisionCompatibilityError) else DecisionErrorCode.PROVIDER_RESPONSE_INVALID
                    last = self._failure(invocation, code, "Decision provider returned an invalid response." if code is DecisionErrorCode.PROVIDER_RESPONSE_INVALID else "No compatible decision model is available." if code is DecisionErrorCode.NO_COMPATIBLE_MODEL else "Decision provider timed out.", started, attempt + 1, fallback)
                if fallback:
                    self._metric("decision_runtime.fallback", profile=request.profile_key)
            assert last is not None
            self._metric("decision_runtime.failure", profile=request.profile_key, error=last.error.code.value if last.error else "unknown")
            return replace(last, timing=TimingMetadata(int((time.monotonic() - started) * 1000), last.timing.provider_ms))
        except DecisionRuntimeError:
            self._metric("decision_runtime.failure", profile=request.profile_key, error="boundary")
            raise

    def _failure(self, invocation: DecisionInvocation, code: DecisionErrorCode, message: str, started: float, attempts: int = 0, fallback: bool = False) -> DecisionResult:
        return DecisionResult(invocation.profile, SCHEMA_VERSION, (), None, TimingMetadata(int((time.monotonic() - started) * 1000)), attempts, (), FallbackMetadata(True, "previous_attempt_failed") if fallback else None, _safe_error(code, message, code is DecisionErrorCode.PROVIDER_UNAVAILABLE))

    def _success(self, result: DecisionResult, request: RuntimeRequest, started: float, fallback: bool) -> None:
        self._metric("decision_runtime.success", profile=request.profile_key)
        if fallback:
            self._metric("decision_runtime.fallback", profile=request.profile_key)
        self._metric("decision_runtime.latency_ms", (time.monotonic() - started) * 1000, profile=request.profile_key)
        # Deliberately logs only identifiers/metadata, never contexts or results.
        self.logger.info("decision_runtime.completed profile=%s attempts=%d fallback=%s", request.profile_key, result.attempts, fallback)
