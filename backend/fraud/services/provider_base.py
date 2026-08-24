"""Shared provider abstraction for Phase 17+ AI services.

All AI providers in Rentora follow the same pattern:

1. A ``*_PROVIDER`` setting selects the active provider name.
2. A local/default provider class handles the basic case (free, no network).
3. An optional HTTP gateway provider handles production-grade services.
4. Provider failures are classified (USER_FAILURE vs PROVIDER_FAILURE vs
   SYSTEM_FAILURE) so callers can handle them appropriately.

This module provides:

- ``ProviderResult``: the standard dataclass every provider returns.
- ``ProviderFailure``: typed exception for provider errors.
- ``BaseProvider``: abstract base class for all providers.
- ``Registry``: provider registry that resolves ``*_PROVIDER`` settings.
- ``TelemetryMixin``: optional mixin for automatic execution logging.
- ``timed_execution``: context manager for latency tracking.

Phase 17 providers (liveness, face-match, review NLP) should extend
``BaseProvider`` and register via ``Registry.register``. Phase 18 adds
optional telemetry via ``TelemetryMixin`` — providers that inherit from
``TelemetryProvider`` get automatic execution logging without code changes.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# Telemetry settings (imported lazily to avoid circular imports)
_telemetry_enabled = None


def _is_telemetry_enabled() -> bool:
    """Check if AI telemetry is enabled (lazy import)."""
    global _telemetry_enabled
    if _telemetry_enabled is None:
        try:
            from django.conf import settings

            _telemetry_enabled = getattr(settings, "AI_TELEMETRY_ENABLED", True)
        except Exception:
            _telemetry_enabled = False
    return _telemetry_enabled


class FailureType(StrEnum):
    """Classification of provider failures for callers."""

    USER_FAILURE = "user_failure"
    PROVIDER_FAILURE = "provider_failure"
    SYSTEM_FAILURE = "system_failure"


@dataclass
class ProviderResult:
    """Standard result from any AI provider.

    Attributes
    ----------
    success : bool
        Whether the provider completed successfully.
    provider : str
        Name of the provider that produced this result.
    confidence : float
        Confidence in the result, 0.0 to 1.0.
    data : dict
        Provider-specific result data.
    reason : str
        Human-readable explanation of the result.
    failure_type : FailureType | None
        If ``success`` is False, the classification of the failure.
    latency_ms : int
        Execution latency in milliseconds (0 if not measured).
    input_tokens : int
        Input tokens consumed (0 if not applicable).
    output_tokens : int
        Output tokens produced (0 if not applicable).
    model_name : str
        AI model name if applicable.
    model_version : str
        AI model version if applicable.
    metadata : dict
        Additional telemetry data (provider-specific).
    """

    success: bool
    provider: str
    confidence: float = 0.0
    data: dict = field(default_factory=dict)
    reason: str = ""
    failure_type: FailureType | None = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_name: str = ""
    model_version: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def is_user_failure(self) -> bool:
        return self.failure_type == FailureType.USER_FAILURE

    @property
    def is_provider_failure(self) -> bool:
        return self.failure_type == FailureType.PROVIDER_FAILURE

    @property
    def is_system_failure(self) -> bool:
        return self.failure_type == FailureType.SYSTEM_FAILURE

    @classmethod
    def ok(
        cls,
        provider: str,
        data: dict | None = None,
        confidence: float = 1.0,
        reason: str = "",
        latency_ms: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_name: str = "",
        model_version: str = "",
        metadata: dict | None = None,
    ) -> ProviderResult:
        return cls(
            success=True,
            provider=provider,
            confidence=confidence,
            data=data or {},
            reason=reason,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            model_version=model_version,
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        provider: str,
        reason: str,
        failure_type: FailureType = FailureType.PROVIDER_FAILURE,
        latency_ms: int = 0,
        metadata: dict | None = None,
    ) -> ProviderResult:
        from .privacy import sanitize_reason

        return cls(
            success=False,
            provider=provider,
            reason=sanitize_reason(reason),
            failure_type=failure_type,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )


class ProviderFailure(Exception):
    """Typed exception for provider errors.

    Carries a ``FailureType`` so callers can distinguish user errors from
    infrastructure problems without string-matching.
    """

    def __init__(
        self,
        message: str,
        failure_type: FailureType = FailureType.SYSTEM_FAILURE,
    ):
        super().__init__(message)
        self.failure_type = failure_type


class BaseProvider(ABC):
    """Abstract base for all AI providers.

    Subclasses implement ``_run`` with their provider-specific logic.
    The base class handles error classification and logging.

    Usage::

        class MyProvider(BaseProvider):
            name = "my_provider"

            def _run(self, **kwargs) -> ProviderResult:
                return ProviderResult.ok(self.name, data={...})

        provider = MyProvider()
        result = provider.run(image_bytes=b"...", user=user)
    """

    name: str = "base"

    @abstractmethod
    def _run(self, **kwargs: Any) -> ProviderResult:
        """Provider-specific implementation. Must return a ProviderResult."""

    def run(self, **kwargs: Any) -> ProviderResult:
        """Run the provider with error handling and classification.

        Wraps ``_run`` in a try/except that classifies failures and logs
        them without raising. Callers always get a ProviderResult.
        """
        from .privacy import sanitize_reason

        try:
            return self._run(**kwargs)
        except ProviderFailure as exc:
            logger.warning(
                "Provider %s failed: type=%s",
                self.name,
                exc.failure_type.value,
            )
            return ProviderResult.fail(
                provider=self.name,
                reason=str(exc),
                failure_type=exc.failure_type,
            )
        except Exception as exc:
            logger.exception("Provider %s raised unexpected error", self.name)
            return ProviderResult.fail(
                provider=self.name,
                reason=sanitize_reason(f"Unexpected error: {exc}"),
                failure_type=FailureType.SYSTEM_FAILURE,
            )


class Registry:
    """Provider registry that resolves ``*_PROVIDER`` settings to classes.

    Usage::

        Registry.register("liveness", "rules", RulesLivenessProvider)
        Registry.register("liveness", "http", HttpLivenessProvider)

        provider_cls = Registry.resolve("liveness", setting="KYC_LIVENESS_PROVIDER")
        provider = provider_cls()
        result = provider.run(...)
    """

    _providers: dict[str, dict[str, type[BaseProvider]]] = {}

    @classmethod
    def register(cls, feature: str, name: str, provider_cls: type[BaseProvider]) -> None:
        """Register a provider class under a feature + name."""
        if feature not in cls._providers:
            cls._providers[feature] = {}
        cls._providers[feature][name] = provider_cls

    @classmethod
    def resolve(cls, feature: str, setting: str) -> type[BaseProvider] | None:
        """Resolve the active provider class from a Django setting.

        Returns None when the setting is empty or the provider is not found.
        """
        from django.conf import settings

        name = (getattr(settings, setting, "") or "").strip().lower()
        if not name:
            return None
        providers = cls._providers.get(feature, {})
        provider_cls = providers.get(name)
        if provider_cls is None:
            logger.warning(
                "Provider %r not found for feature %r (available: %s)",
                name,
                feature,
                ", ".join(providers) or "none",
            )
        return provider_cls

    @classmethod
    def available(cls, feature: str) -> list[str]:
        """List registered provider names for a feature."""
        return list(cls._providers.get(feature, {}).keys())


@contextmanager
def timed_execution():
    """Context manager for measuring execution latency.

    Usage::

        with timed_execution() as timer:
            # do work
            pass
        print(f"Elapsed: {timer.elapsed_ms}ms")
    """

    class Timer:
        def __init__(self):
            self.start_time = 0
            self.elapsed_ms = 0

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = time.perf_counter() - self.start_time
            self.elapsed_ms = int(elapsed * 1000)
            return False

    yield Timer()


class TelemetryMixin:
    """Optional mixin for BaseProvider subclasses to enable automatic telemetry.

    When mixed in, the provider's ``run`` method automatically logs execution
    telemetry to the AIExecutionLog model. The mixin is non-blocking — if
    telemetry logging fails, the provider execution continues.

    Usage::

        class MyProvider(TelemetryMixin, BaseProvider):
            name = "my_provider"
            feature_id = "my_feature"  # required for telemetry

            def _run(self, **kwargs) -> ProviderResult:
                return ProviderResult.ok(self.name, data={...})

    The ``feature_id`` class attribute is required for telemetry logging.
    If not set, telemetry is silently skipped.
    """

    feature_id: str = ""

    def run(self, **kwargs: Any) -> ProviderResult:
        """Run with automatic telemetry logging."""
        if not self.feature_id or not _is_telemetry_enabled():
            return super().run(**kwargs)  # type: ignore[misc]

        execution_id = uuid.uuid4()
        request_id = kwargs.pop("request_id", "")
        user = kwargs.pop("user", None)

        with timed_execution() as timer:
            result = super().run(**kwargs)  # type: ignore[misc]

        # Add telemetry data to result
        result.latency_ms = timer.elapsed_ms
        result.metadata["execution_id"] = str(execution_id)
        result.metadata["request_id"] = request_id

        # Log telemetry (non-blocking)
        try:
            _log_execution(
                execution_id=execution_id,
                feature_id=self.feature_id,
                provider=self.name,
                user=user,
                request_id=request_id,
                result=result,
            )
        except Exception:
            logger.debug("Telemetry logging failed for %s", self.name, exc_info=True)

        return result


def _log_execution(
    execution_id: uuid.UUID,
    feature_id: str,
    provider: str,
    user: Any,
    request_id: str,
    result: ProviderResult,
) -> None:
    """Log AI execution to the database (called asynchronously when possible)."""
    try:
        from ai_intelligence.models import AIExecutionLog

        AIExecutionLog.objects.create(
            execution_id=execution_id,
            feature_key=feature_id,
            provider=provider,
            user=user if user and user.is_authenticated else None,
            request_id=request_id,
            status="success" if result.success else "failure",
            failure_type=result.failure_type.value if result.failure_type else "none",
            error_message=result.reason if not result.success else "",
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
            confidence=result.confidence,
            model_name=result.model_name,
            model_version=result.model_version,
            metadata=result.metadata,
        )
    except Exception:
        # Telemetry must never block or crash the provider
        logger.debug("Failed to log AI execution", exc_info=True)
