"""Broker domain services: deterministic pre-screen + referral resolution.

The pre-screen mirrors ``users.kyc_auto`` style: explainable scoring that
*recommends* a decision to the admin queue, never deciding alone.
"""

from __future__ import annotations

from .models import BrokerProfile, BrokerVerification

APPROVE_SCORE = 70


def _prior_rejections(profile: BrokerProfile) -> int:
    return BrokerVerification.objects.filter(
        profile=profile, status=BrokerVerification.Status.REJECTED
    ).count()


def screen_broker(verification: BrokerVerification) -> dict:
    """Score one broker verification submission (100 - penalties)."""
    profile = verification.profile
    user = profile.user
    reasons: list[str] = []
    score = 100
    hard_fail = False

    if not profile.license_number:
        reasons.append("no license number provided")
        score -= 35
        hard_fail = True
    if profile.years_experience < 2:
        reasons.append("less than 2 years of experience")
        score -= 15
    if not profile.specialization:
        reasons.append("no specialization declared")
        score -= 10
    if not profile.areas:
        reasons.append("no service areas declared")
        score -= 10
    if not (user.phone and (user.first_name or user.last_name)):
        reasons.append("profile is missing phone/name")
        score -= 10
    if len(verification.documents or []) == 0:
        reasons.append("no documents uploaded")
        score -= 20
        hard_fail = True

    prior = _prior_rejections(profile)
    if prior > 0:
        reasons.append(f"{prior} prior rejected submissions")
        score -= 15 * prior

    score = max(0, min(100, score))
    result = "recommend_approve" if score >= APPROVE_SCORE and not hard_fail else "recommend_review"
    return {"score": score, "result": result, "reasons": reasons}


def get_or_create_profile(user) -> BrokerProfile:
    profile, _ = BrokerProfile.objects.get_or_create(user=user)
    return profile


def resolve_referral(code: str) -> BrokerProfile | None:
    """Resolve a referral code to a *verified* broker profile, else None."""
    if not code:
        return None
    profile = BrokerProfile.objects.filter(
        referral_code=code, status=BrokerProfile.Status.VERIFIED
    ).first()
    return profile
