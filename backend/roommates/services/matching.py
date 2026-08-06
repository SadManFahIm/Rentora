"""Roommate matching algorithm.

Scoring is transparent and explainable — each candidate's total is the
weighted sum of five independently-computed compatibility signals, and the
reasons list records exactly which signals matched (and which didn't) so the
frontend can show "why did I match with this person".

Signals and weights
-------------------
- budget overlap  (35%) — how much of the two budget ranges intersect
- area            (25%) — same preferred area
- room type       (15%) — same room-type preference
- gender pref     (15%) — gender preferences are compatible (either both
                          "any", or each side's pref matches the other)
- lifestyle       (10%) — Jaccard overlap of lifestyle tags

A candidate must share the *area* to be eligible at all: budget can be
negotiated and lifestyle can be lived with, but nobody in Mirpur is going to
share a room with someone who insists on Dhanmondi.
"""

from __future__ import annotations

from dataclasses import dataclass

from roommates.models import RoommateProfile

BUDGET_WEIGHT = 0.35
AREA_WEIGHT = 0.25
ROOM_TYPE_WEIGHT = 0.15
GENDER_WEIGHT = 0.15
LIFESTYLE_WEIGHT = 0.10

MIN_MATCH_SCORE = 20


@dataclass
class MatchResult:
    """One scored candidate."""

    profile: RoommateProfile
    score: int  # 0-100
    reasons: list[str]  # human-readable "why" lines


def _budget_overlap(a: RoommateProfile, b: RoommateProfile) -> float:
    """Fraction of the combined range that both can afford, 0..1."""
    a_min, a_max = float(a.budget_min), float(a.budget_max)
    b_min, b_max = float(b.budget_min), float(b.budget_max)
    if a_max <= a_min or b_max <= b_min:
        return 0.0
    overlap = min(a_max, b_max) - max(a_min, b_min)
    if overlap <= 0:
        return 0.0
    union = max(a_max, b_max) - min(a_min, b_min)
    return overlap / union if union > 0 else 0.0


def _lifestyle_jaccard(a: RoommateProfile, b: RoommateProfile) -> float:
    """Jaccard similarity of two lifestyle tag sets, 0..1."""
    tags_a, tags_b = set(a.lifestyle or []), set(b.lifestyle or [])
    if not tags_a and not tags_b:
        return 0.0
    union = tags_a | tags_b
    if not union:
        return 0.0
    return len(tags_a & tags_b) / len(union)


def _gender_compatible(a: RoommateProfile, b: RoommateProfile) -> bool:
    """True if neither side's preference rules the other out.

    ``any`` is compatible with everything. A concrete preference (male/female)
    must be *reciprocal*: if A wants female and B is male, they don't match —
    even though B might be fine with A — because A has stated a preference.
    """
    if a.gender_pref == "any" and b.gender_pref == "any":
        return True
    a_user_gender = a.user.gender or "any"
    b_user_gender = b.user.gender or "any"

    incompatible_a = a.gender_pref != "any" and a.gender_pref != b_user_gender
    incompatible_b = b.gender_pref != "any" and b.gender_pref != a_user_gender
    return not (incompatible_a or incompatible_b)


def _score_pair(a: RoommateProfile, b: RoommateProfile) -> MatchResult | None:
    """Score profile ``a`` against candidate ``b`` (directional reasons)."""
    reasons: list[str] = []

    if a.preferred_area != b.preferred_area:
        # Hard gate: no shared area, no match.
        return None

    if not _gender_compatible(a, b):
        # Hard gate: a stated gender preference that isn't reciprocated rules
        # the pair out — e.g. a woman who prefers a female roommate should
        # never be shown a male candidate, even if everything else matches.
        return None

    budget = _budget_overlap(a, b)
    if budget >= 0.5:
        reasons.append("Budgets overlap well")
    elif budget > 0:
        reasons.append("Budgets partly overlap")

    area = 1.0
    reasons.append("Same preferred area")

    room_type = 1.0 if a.room_type_pref == b.room_type_pref else 0.0
    if room_type:
        reasons.append("Same room-type preference")

    gender = 1.0

    lifestyle = _lifestyle_jaccard(a, b)
    if lifestyle >= 0.5:
        reasons.append("Similar lifestyle")
    elif lifestyle > 0:
        reasons.append("Some shared lifestyle tags")

    score = (
        budget * BUDGET_WEIGHT
        + area * AREA_WEIGHT
        + room_type * ROOM_TYPE_WEIGHT
        + gender * GENDER_WEIGHT
        + lifestyle * LIFESTYLE_WEIGHT
    )
    return MatchResult(profile=b, score=round(score * 100), reasons=reasons)


def find_matches(
    profile: RoommateProfile,
    *,
    exclude_users: set[int] | None = None,
) -> list[MatchResult]:
    """Rank all eligible candidates against ``profile``, best first.

    ``exclude_users`` lets callers skip the user themself plus anyone they've
    already sent a request to (see views).
    """
    exclude = exclude_users or set()
    exclude.add(profile.user_id)

    candidates = (
        RoommateProfile.objects.select_related("user")
        .filter(is_looking=True)
        .exclude(user_id__in=exclude)
    )

    results: list[MatchResult] = []
    for candidate in candidates:
        match = _score_pair(profile, candidate)
        if match is not None and match.score >= MIN_MATCH_SCORE:
            results.append(match)

    results.sort(key=lambda m: m.score, reverse=True)
    return results
