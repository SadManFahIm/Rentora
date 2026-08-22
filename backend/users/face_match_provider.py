"""KYC face-match provider (Stage 4).

Provider contract:
- ``verify(user, document_path, selfie_bytes) -> ProviderResult``
- Compares the face in the selfie against the uploaded KYC document.
- Returns ``success=True`` with a confidence score when faces match.
- Returns ``success=False`` with a ``FailureType`` classification on error.

Two bundled providers:
- ``RulesFaceMatchProvider``: deterministic mock that always passes (for
  development/testing when no real face-match service is available).
- ``HttpFaceMatchProvider``: posts the document + selfie to a configurable
  HTTP gateway (``KYC_FACE_MATCH_GATEWAY_URL``).

The active provider is selected via the ``KYC_FACE_MATCH_PROVIDER`` setting.
"""

from __future__ import annotations

import logging
import os

from django.conf import settings

from fraud.services.provider_base import (
    BaseProvider,
    FailureType,
    ProviderFailure,
    ProviderResult,
    Registry,
)

logger = logging.getLogger(__name__)

FACE_MATCH_MIN_SCORE = 60  # minimum provider_score (0-100) to pass


class RulesFaceMatchProvider(BaseProvider):
    """Deterministic mock face-match provider (bundled, free).

    Always passes with a fixed confidence score. For development and
    testing when no real face-match service is available.
    """

    name = "rules"

    def _run(self, **kwargs) -> ProviderResult:
        document_path = kwargs.get("document_path", "")
        selfie_bytes = kwargs.get("selfie_bytes")

        if not selfie_bytes:
            raise ProviderFailure(
                "No selfie image provided for face match.",
                failure_type=FailureType.USER_FAILURE,
            )
        if document_path and not os.path.exists(document_path):
            raise ProviderFailure(
                "KYC document file not found on disk.",
                failure_type=FailureType.USER_FAILURE,
            )

        return ProviderResult.ok(
            provider=self.name,
            data={"face_match": True, "similarity": 0.82},
            confidence=0.82,
            reason="Rules face-match provider: document and selfie provided, match assumed.",
        )


class HttpFaceMatchProvider(BaseProvider):
    """HTTP gateway face-match provider.

    Posts the document image and selfie to ``KYC_FACE_MATCH_GATEWAY_URL``
    as multipart fields ``document`` and ``selfie``.
    Expects ``{"match": bool, "score": float, ...}``.
    """

    name = "http"
    _TIMEOUT_SECONDS = 30

    def _run(self, **kwargs) -> ProviderResult:
        document_path = kwargs.get("document_path", "")
        selfie_bytes = kwargs.get("selfie_bytes")

        if not selfie_bytes:
            raise ProviderFailure(
                "No selfie image provided for face match.",
                failure_type=FailureType.USER_FAILURE,
            )

        url = getattr(settings, "KYC_FACE_MATCH_GATEWAY_URL", "")
        if not url:
            raise ProviderFailure(
                "KYC_FACE_MATCH_GATEWAY_URL is not configured.",
                failure_type=FailureType.SYSTEM_FAILURE,
            )

        import requests

        headers = {}
        api_key = getattr(settings, "KYC_FACE_MATCH_GATEWAY_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        files = {}
        doc_handle = None
        if document_path and os.path.exists(document_path):
            doc_handle = open(document_path, "rb")  # noqa: SIM115
            files["document"] = (
                os.path.basename(document_path),
                doc_handle,
                "image/jpeg",
            )

        try:
            response = requests.post(
                url,
                files={**files, "selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
                headers=headers,
                timeout=self._TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise ProviderFailure(
                "Face-match gateway timed out.",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc
        except requests.ConnectionError as exc:
            raise ProviderFailure(
                "Could not connect to face-match gateway.",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc
        except Exception as exc:
            raise ProviderFailure(
                f"Face-match gateway error: {exc}",
                failure_type=FailureType.PROVIDER_FAILURE,
            ) from exc
        finally:
            if doc_handle is not None:
                doc_handle.close()

        matched = data.get("match", False)
        score = int(data.get("score", 0))

        if not matched:
            raise ProviderFailure(
                data.get("reason", "Face match failed: faces do not match."),
                failure_type=FailureType.USER_FAILURE,
            )

        confidence = max(0.0, min(1.0, score / 100.0))
        return ProviderResult.ok(
            provider=self.name,
            data={"face_match": True, "raw_score": score, **data},
            confidence=confidence,
            reason=f"Face match passed (similarity={score}%).",
        )


# Register both providers
Registry.register("face_match", "rules", RulesFaceMatchProvider)
Registry.register("face_match", "http", HttpFaceMatchProvider)


def get_face_match_provider() -> type[BaseProvider] | None:
    """Resolve the active face-match provider from settings."""
    return Registry.resolve("face_match", setting="KYC_FACE_MATCH_PROVIDER")


def run_face_match(user, document_path: str, selfie_bytes: bytes) -> ProviderResult:
    """Run the configured face-match provider for one user.

    Compares the KYC document image against the liveness selfie.
    Returns a ProviderResult. Callers should check ``result.success``.
    """
    provider_cls = get_face_match_provider()
    if provider_cls is None:
        return ProviderResult.fail(
            provider="none",
            reason="No face-match provider configured.",
            failure_type=FailureType.SYSTEM_FAILURE,
        )
    provider = provider_cls()
    return provider.run(
        user=user,
        document_path=document_path,
        selfie_bytes=selfie_bytes,
    )
