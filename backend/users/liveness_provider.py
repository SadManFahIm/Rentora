"""KYC liveness-detection provider (Stage 4).

Provider contract:
- ``verify(user, challenge_type, selfie_bytes) -> ProviderResult``
- Returns ``success=True`` with a confidence score when liveness is detected.
- Returns ``success=False`` with a ``FailureType`` classification on error.

Two bundled providers:
- ``RulesLivenessProvider``: deterministic mock that always passes (for
  development/testing when no real liveness service is available).
- ``HttpLivenessProvider``: posts the selfie to a configurable HTTP gateway
  (``KYC_LIVENESS_GATEWAY_URL``) and parses the response.

Usage::

    from fraud.services.provider_base import Registry
    Registry.register("liveness", "rules", RulesLivenessProvider)
    Registry.register("liveness", "http", HttpLivenessProvider)

The active provider is selected via the ``KYC_LIVENESS_PROVIDER`` setting.
"""

from __future__ import annotations

import logging

from django.conf import settings

from fraud.services.provider_base import (
    BaseProvider,
    FailureType,
    ProviderFailure,
    ProviderResult,
    Registry,
)

logger = logging.getLogger(__name__)

LIVENESS_MIN_SCORE = 70  # minimum provider_score (0-100) to pass


class RulesLivenessProvider(BaseProvider):
    """Deterministic mock liveness provider (bundled, free).

    Always passes with a fixed confidence score. For development and
    testing when no real liveness service is available.
    """

    name = "rules"

    def _run(self, **kwargs) -> ProviderResult:
        selfie_bytes = kwargs.get("selfie_bytes")
        if not selfie_bytes:
            raise ProviderFailure(
                "No selfie image provided.",
                failure_type=FailureType.USER_FAILURE,
            )
        if len(selfie_bytes) < 100:
            raise ProviderFailure(
                "Selfie image too small or corrupt.",
                failure_type=FailureType.USER_FAILURE,
            )
        return ProviderResult.ok(
            provider=self.name,
            data={"liveness": True, "challenge_completed": True},
            confidence=0.85,
            reason="Rules liveness provider: selfie provided, challenge passed.",
        )


class HttpLivenessProvider(BaseProvider):
    """HTTP gateway liveness provider.

    Posts the selfie image to ``KYC_LIVENESS_GATEWAY_URL`` as multipart
    with a ``selfie`` field. Expects ``{"passed": bool, "score": float, ...}``.
    """

    name = "http"
    _TIMEOUT_SECONDS = 30

    def _run(self, **kwargs) -> ProviderResult:
        selfie_bytes = kwargs.get("selfie_bytes")
        challenge_type = kwargs.get("challenge_type", "blink")

        if not selfie_bytes:
            raise ProviderFailure(
                "No selfie image provided.",
                failure_type=FailureType.USER_FAILURE,
            )

        url = getattr(settings, "KYC_LIVENESS_GATEWAY_URL", "")
        if not url:
            raise ProviderFailure(
                "KYC_LIVENESS_GATEWAY_URL is not configured.",
                failure_type=FailureType.SYSTEM_FAILURE,
            )

        import requests

        headers = {}
        api_key = getattr(settings, "KYC_LIVENESS_GATEWAY_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.post(
                url,
                files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
                data={"challenge_type": challenge_type},
                headers=headers,
                timeout=self._TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise ProviderFailure(
                "Liveness gateway timed out.",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc
        except requests.ConnectionError as exc:
            raise ProviderFailure(
                "Could not connect to liveness gateway.",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc
        except Exception as exc:
            raise ProviderFailure(
                f"Liveness gateway error: {exc}",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc

        passed = data.get("passed", False)
        score = int(data.get("score", 0))

        if not passed:
            raise ProviderFailure(
                data.get("reason", "Liveness check failed."),
                failure_type=FailureType.USER_FAILURE,
            )

        confidence = max(0.0, min(1.0, score / 100.0))
        return ProviderResult.ok(
            provider=self.name,
            data={"liveness": True, "raw_score": score, **data},
            confidence=confidence,
            reason=f"Liveness passed (score={score}).",
        )


# Register both providers
Registry.register("liveness", "rules", RulesLivenessProvider)
Registry.register("liveness", "http", HttpLivenessProvider)


def get_liveness_provider() -> type[BaseProvider] | None:
    """Resolve the active liveness provider from settings."""
    return Registry.resolve("liveness", setting="KYC_LIVENESS_PROVIDER")


def run_liveness_check(user, challenge_type: str, selfie_bytes: bytes) -> ProviderResult:
    """Run the configured liveness provider for one user.

    Returns a ProviderResult. Callers should check ``result.success`` and
    update the LivenessChallenge accordingly.
    """
    provider_cls = get_liveness_provider()
    if provider_cls is None:
        return ProviderResult.fail(
            provider="none",
            reason="No liveness provider configured.",
            failure_type=FailureType.SYSTEM_FAILURE,
        )
    provider = provider_cls()
    return provider.run(
        user=user,
        challenge_type=challenge_type,
        selfie_bytes=selfie_bytes,
    )
