"""Shared provider abstraction for Phase 17 AI services (Stage 2).

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

Phase 17 providers (liveness, face-match, review NLP) should extend
``BaseProvider`` and register via ``Registry.register``. Existing providers
(migration from the 7 independent implementations) are NOT changed in
Stage 2 — they adopt this base incrementally in later stages.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


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
    """

    success: bool
    provider: str
    confidence: float = 0.0
    data: dict = field(default_factory=dict)
    reason: str = ""
    failure_type: FailureType | None = None

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
    ) -> ProviderResult:
        return cls(
            success=True,
            provider=provider,
            confidence=confidence,
            data=data or {},
            reason=reason,
        )

    @classmethod
    def fail(
        cls,
        provider: str,
        reason: str,
        failure_type: FailureType = FailureType.PROVIDER_FAILURE,
    ) -> ProviderResult:
        from .privacy import sanitize_reason

        return cls(
            success=False,
            provider=provider,
            reason=sanitize_reason(reason),
            failure_type=failure_type,
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
