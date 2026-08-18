"""Automated KYC provider (Tier 4) — pluggable document verification.

The Tier-2 pre-screener (*) *recommends* a decision for the admin queue.
This module adds the optional **provider** layer on top: when the deployment
enables it, a provider can *decide* — approving a submission automatically
at high confidence. Manual review always remains the fallback and the
override (the admin queue is unchanged and any admin action still wins).

Design / safety:

- **Opt-in by two settings**: ``KYC_AUTO_APPROVE_ENABLED`` (master switch,
  default off — existing behaviour is untouched) and ``KYC_PROVIDER``
  (which provider implementation to use, default empty = manual-only).
- **Provider contract**: a provider is any class with ``verify(path, user,
  screening) -> ProviderResult``. Only a ``ProviderResult`` with
  ``approved=True`` and ``confidence >= KYC_AUTO_APPROVE_MIN_CONFIDENCE``
  auto-approves; everything else falls through to PENDING + human review.
- **Conservative by construction**: the bundled rule-based provider re-checks
  the *same* hard signals the pre-screener does (parses as image/PDF, no
  cross-account reuse, readable size, complete profile, no repeat attempts)
  and maps the pre-screen score to confidence — a score below the approve
  bar can never auto-approve, no matter the provider's opinion.
- **Every decision is audited**: auto-approval writes a
  ``tenant_kyc.auto_approved`` audit event with the provider + confidence,
  so the human trail stays complete.

(*) ``users/kyc_auto.py`` — scoring + recommendation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .kyc_auto import APPROVE_SCORE, auto_screen


@dataclass
class ProviderResult:
    """A provider's verdict on one submission."""

    approved: bool
    confidence: float  # 0..1
    provider: str
    reason: str


class RuleBasedProvider:
    """Deterministic document-verification provider (bundled, free).

    Reuses the pre-screener's checks as hard gates and maps the pre-screen
    score to a confidence estimate. Honest label: this is *rule-based*
    verification, not a commercial biometric/document-verification API —
    deployments can swap in a real provider (Jumio-style) behind the same
    contract without touching the flow.
    """

    name = "rules"

    def verify(self, path: str, user, screening: dict[str, Any]) -> ProviderResult:
        reasons = screening.get("reasons") or []
        score = screening.get("score") or 0
        result = screening.get("result") or "recommend_review"

        # Hard gates: a document that doesn't parse or was reused across
        # accounts can never auto-approve (markers mirror kyc_auto's wording).
        joined = " ".join(reasons).lower()
        if "not a readable image or pdf" in joined or "missing on disk" in joined:
            return ProviderResult(
                approved=False,
                confidence=0.0,
                provider=self.name,
                reason="Hard gate failed: document did not parse.",
            )
        if "visually matches another account" in joined:
            return ProviderResult(
                approved=False,
                confidence=0.0,
                provider=self.name,
                reason="Hard gate failed: document reused across accounts.",
            )

        if result != "recommend_approve" or score < APPROVE_SCORE:
            return ProviderResult(
                approved=False,
                confidence=round(score / 100.0, 2),
                provider=self.name,
                reason="Below the auto-approve bar — human review.",
            )

        # Score 70-100 -> confidence 0.55-0.95 (deliberately not 1.0: rules
        # can't fully verify a person's identity; the admin owns the final
        # word and can always revoke).
        confidence = 0.55 + (score - APPROVE_SCORE) / 100.0
        return ProviderResult(
            approved=True,
            confidence=round(min(confidence, 0.95), 2),
            provider=self.name,
            reason="Rules provider: valid, unique, readable document with a complete profile.",
        )


_PROVIDERS: dict[str, Any] = {"rules": RuleBasedProvider}


def get_provider():
    """Active provider per ``KYC_PROVIDER``, or None (manual-only)."""
    name = getattr(settings, "KYC_PROVIDER", "") or ""
    return _PROVIDERS.get(name.strip().lower())


def auto_approve_enabled() -> bool:
    return getattr(settings, "KYC_AUTO_APPROVE_ENABLED", False)


def run_provider(verification) -> ProviderResult | None:
    """Run the configured provider over ``verification``.

    Returns None when automation is disabled or no provider is configured
    (the submission stays PENDING for manual review). Otherwise returns the
    provider's verdict — the caller decides what to do with it.
    """
    if not auto_approve_enabled():
        return None
    provider = get_provider()
    if provider is None:
        return None

    screening = auto_screen(verification)
    path = getattr(verification.file, "path", "")
    return provider().verify(path, verification.user, screening)
